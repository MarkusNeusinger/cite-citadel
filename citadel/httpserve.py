"""The opt-in **Streamable HTTP** transport for the MCP server (``citadel serve --http``).

``citadel serve`` speaks stdio: the client spawns the process, owns its lifetime, and nothing
listens on a socket. That is the right default and stays the default. What it cannot do is be
reached by a client that does not run on this machine — a hosted assistant, a phone — which is
what MCP's Streamable HTTP transport is for. This module is that transport, and nothing else:
the tool/prompt/resource surface is :mod:`citadel.server`'s, unchanged and shared.

Binding a port turns a local-only tool into a network service, so the posture here is
deliberately strict rather than convenient:

* **A bearer token is mandatory.** :func:`serve` refuses to start without
  ``CITADEL_HTTP_TOKEN`` (and refuses a trivially short one) — there is no "just for a minute"
  unauthenticated mode. Every request must carry ``Authorization: Bearer <token>``; the compare
  is constant-time, and a failure is a plain 401 that never reaches the MCP layer, so an
  unauthenticated caller cannot even open a session.
* **Loopback by default.** ``CITADEL_HTTP_HOST`` defaults to 127.0.0.1. A non-loopback bind is
  allowed — it is the user's machine — but warns, because this transport is plain HTTP: the
  intended remote path is a tunnel (cloudflared / tailscale / ``ssh -R``) that terminates TLS,
  not a raw port on the internet.
* **DNS-rebinding protection on.** A request's ``Host`` must be one this server accepts — derived
  from the bind address (a loopback bind also answers to its aliases), or named explicitly in
  ``CITADEL_HTTP_ALLOWED_HOSTS`` for the deployments where the client addresses something else
  entirely: a tunnel forwards its own hostname, a wildcard bind (``0.0.0.0``) is a name nobody
  sends. That last case cannot be derived at all, so it is a start-up REFUSAL naming the knob
  rather than a server that rejects every request it gets. Separately, a request carrying a browser
  ``Origin`` is refused unless ``CITADEL_HTTP_ALLOWED_ORIGINS`` admits it — the MCP clients this
  serves are not browsers, so an Origin means a web page is driving the server.
* **Optional read-only mode.** ``--read-only`` / ``CITADEL_HTTP_READ_ONLY=1`` switches the two
  mutating tools off for the process (:func:`citadel.server.set_read_only`), leaving the eleven
  readers — the "share my wiki, not my agent CLI" setup.

No new dependency: ``starlette``/``uvicorn`` already ship with ``mcp``, and the token check is a
~30-line ASGI wrapper rather than an OAuth resource server (citadel has no user model — the token
IS the user). :func:`build_app` returns the wrapped ASGI app for tests to drive in-process; only
:func:`serve` binds a port.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
from ipaddress import ip_address

from . import config, server


# The shortest token :func:`serve` will start with. A shared secret guarding a wiki + the local
# coding-agent CLI should be generated, not thought up; 16 chars rejects "password"-class values
# while accepting anything `secrets.token_urlsafe(12)` and up produces.
MIN_TOKEN_CHARS = 16

# Hostnames that mean "this machine" — used for the bind warning and for the Host/Origin allowlist.
# Stored in BIND form (bare, no URL brackets); format_host renders the URL/Host-header spelling.
_LOOPBACK_NAMES = ("localhost", "127.0.0.1", "::1")


# Default marker for build_app's allowlist arguments: `None` is a REAL value there ("accept any"),
# so "not passed, resolve from config" needs its own sentinel.
_FROM_CONFIG: object = object()


class HttpServeError(RuntimeError):
    """A refusal to start the HTTP server (no token / too-short token). Carries the operator-facing
    explanation; the CLI prints it and exits non-zero."""


def normalize_host(host: str) -> str:
    """The BIND spelling of a host. An IPv6 literal written the way a URL wants it (``[::1]``) is a
    URL spelling, not a bind address — uvicorn (and the socket layer under it) wants the bare
    ``::1`` and refuses the bracketed form, so an operator who copies the address out of the banner
    back into ``CITADEL_HTTP_HOST`` must not meet a confusing start-up failure."""
    value = host.strip()
    if value.startswith("[") and value.endswith("]"):
        return value[1:-1]
    return value


def format_host(host: str) -> str:
    """The URL / ``Host``-header spelling of a host: an IPv6 literal needs brackets
    (``http://[::1]:8765/mcp``), everything else is itself. The inverse of :func:`normalize_host`."""
    value = normalize_host(host)
    return f"[{value}]" if ":" in value else value


def is_loopback(host: str) -> bool:
    """True when ``host`` binds only this machine. Names are matched literally (no DNS lookup —
    resolving at config time would be a surprising network call); anything that parses as an IP is
    judged by the stdlib. Both host spellings are accepted (``::1`` and ``[::1]``)."""
    value = normalize_host(host).lower()
    if value in ("localhost", ""):
        return True
    try:
        return ip_address(value).is_loopback
    except ValueError:
        return False


def host_name(value: str) -> str:
    """The comparable NAME in a ``Host``-header-shaped string: lower-cased, port dropped, IPv6
    brackets dropped (``[::1]:8765`` -> ``::1``, ``Wiki.Example.com:443`` -> ``wiki.example.com``).
    Ports carry no rebinding signal — the NAME is what an attacker would have to control — so the
    allowlist is matched on names only, and a tunnel that rewrites the port still reaches the
    server."""
    text = value.strip().lower()
    if text.startswith("["):  # bracketed IPv6, optionally :port after the bracket
        end = text.find("]")
        return text[1:end] if end != -1 else text[1:]
    # A bare IPv6 literal has several colons; only a single trailing colon is a port separator.
    if text.count(":") == 1:
        text = text.split(":", 1)[0]
    return text


def allowed_host_names(host: str, configured: list[str] | None = None) -> list[str] | None:
    """The ``Host`` names this server accepts, or ``None`` for "accept any" (``*``).

    ``configured`` (``CITADEL_HTTP_ALLOWED_HOSTS``) wins whenever it is set — it is the answer for
    every deployment where the client does NOT address the bind address directly: a tunnel forwards
    its own hostname, a reverse proxy forwards the site name. With nothing configured the list is
    DERIVED from the bind address: a loopback bind also accepts its usual aliases (a client may say
    ``localhost`` where uvicorn bound ``127.0.0.1``), and any other concrete address accepts itself.

    A WILDCARD bind (``0.0.0.0``/``::``) derives to an empty list on purpose: "0.0.0.0" is a name no
    client ever sends, so there is nothing honest to derive — :func:`serve` turns that into a refusal
    naming this knob, rather than a server that rejects every request it receives."""
    configured = config.HTTP_ALLOWED_HOSTS if configured is None else configured
    if configured:
        return None if "*" in configured else [host_name(name) for name in configured]
    if is_wildcard_bind(host):
        return []
    names = [host_name(host)]
    if is_loopback(host):
        names.extend(host_name(name) for name in _LOOPBACK_NAMES)
    return list(dict.fromkeys(names))


def allowed_origins(configured: list[str] | None = None) -> list[str] | None:
    """The browser ``Origin`` values accepted, or ``None`` for "accept any" (``*``).

    Defaults to the EMPTY list — i.e. a request carrying any ``Origin`` at all is refused. The
    clients this transport serves are not browsers, so an Origin header means a web page is driving
    the server, which is the attack this check exists for. A browser-based MCP client is admitted
    only by naming its origin (``CITADEL_HTTP_ALLOWED_ORIGINS=https://claude.ai``)."""
    configured = config.HTTP_ALLOWED_ORIGINS if configured is None else configured
    if "*" in configured:
        return None
    return [origin.strip().lower().rstrip("/") for origin in configured]


def is_wildcard_bind(host: str) -> bool:
    """True for a bind-ALL address (``0.0.0.0`` / ``::``): it names an interface set, never a host
    a client can address, so no ``Host`` allowlist can be derived from it."""
    value = normalize_host(host)
    try:
        return ip_address(value).is_unspecified
    except ValueError:
        return False


def _error_response(status: int, message: str, *, challenge: bool = False):
    """A refusal body + headers: a JSON-RPC-shaped error (the caller speaks MCP, so it can read it)
    and, for a 401, the ``WWW-Authenticate`` challenge the HTTP spec requires. Deliberately terse —
    an auth refusal never says whether a token was present, wrong length, or close."""
    body = json.dumps({"jsonrpc": "2.0", "error": {"code": -32001, "message": message}, "id": None}).encode("utf-8")
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("ascii"))]
    if challenge:
        headers.append((b"www-authenticate", b'Bearer realm="citadel"'))
    return status, body, headers


def bearer_guard(app, token: str, *, hosts: list[str] | None = None, origins: list[str] | None = None):
    """Wrap an ASGI ``app`` with this server's whole request-admission policy, ahead of MCP.

    Three checks, in order, none of which can be reached by a tool, a session, or the wiki:

    1. **Host** — the ``Host`` name must be in ``hosts`` (``None`` = accept any), which is the
       anti-DNS-rebinding check: a page in the user's browser can force a request to this port, but
       not the ``Host`` name it carries. Refused with 421, like the SDK's own middleware.
    2. **Origin** — a request carrying a browser ``Origin`` is refused with 403 unless that origin
       is in ``origins`` (``None`` = accept any). No Origin at all is the normal case: the MCP
       clients this serves are not browsers.
    3. **Token** — ``Authorization: Bearer <token>``, else 401. Both sides are SHA-256'd before
       :func:`hmac.compare_digest`: that function is only constant-time for equal-length inputs, so
       hashing to a fixed 32 bytes keeps the presented token's LENGTH out of the timing too (a
       timing oracle on a shared secret is a real, if slow, attack).

    The Host/Origin policy lives HERE rather than in the SDK's transport-security middleware because
    that middleware couples the two checks to one flag and can express neither "any host" (needed
    when a proxy already filters it) nor "this one browser origin" — the two configurations real
    deployments need. The SDK middleware stays enabled for its POST ``Content-Type`` check.

    Non-HTTP scopes (``lifespan``, which starts the MCP session manager) pass straight through."""
    expected = hashlib.sha256(token.encode("utf-8")).digest()

    async def guarded(scope, receive, send):
        if scope.get("type") != "http":
            await app(scope, receive, send)
            return
        headers = {name.lower(): value for name, value in scope.get("headers", ())}

        if hosts is not None:
            presented_host = host_name(headers.get(b"host", b"").decode("latin-1"))
            if presented_host not in hosts:
                await _refuse(send, *_error_response(421, "invalid Host header"))
                return

        origin = headers.get(b"origin", b"").decode("latin-1").strip().lower().rstrip("/")
        if origin and origins is not None and origin not in origins:
            await _refuse(send, *_error_response(403, "invalid Origin header"))
            return

        presented = headers.get(b"authorization", b"").strip()
        prefix = b"bearer "
        ok = presented[: len(prefix)].lower() == prefix and hmac.compare_digest(
            hashlib.sha256(presented[len(prefix) :]).digest(), expected
        )
        if not ok:
            await _refuse(send, *_error_response(401, "unauthorized: a valid bearer token is required", challenge=True))
            return
        await app(scope, receive, send)

    return guarded


async def _refuse(send, status: int, body: bytes, headers: list[tuple[bytes, bytes]]) -> None:
    """Send one complete refusal response — the single exit for every check in :func:`bearer_guard`."""
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


def build_app(
    token: str,
    *,
    host: str | None = None,
    port: int | None = None,
    path: str | None = None,
    hosts: list[str] | None | object = _FROM_CONFIG,
    origins: list[str] | None | object = _FROM_CONFIG,
):
    """The guarded ASGI app serving :mod:`citadel.server`'s MCP surface over Streamable HTTP.

    Settings are stamped onto the shared FastMCP instance first (endpoint path, bind address), then
    :meth:`FastMCP.streamable_http_app` builds the Starlette app and :func:`bearer_guard` wraps it
    with the Host/Origin/token policy. Omitting ``hosts``/``origins`` resolves them from the
    ``CITADEL_HTTP_ALLOWED_*`` knobs via :func:`allowed_host_names` / :func:`allowed_origins`
    (passing them explicitly is for tests and for :func:`serve`, which resolves them first; ``None``
    accepts any name, ``[]`` accepts none). Exposed
    separately from :func:`serve` so tests can drive the whole stack in-process without binding a
    port."""
    from mcp.server.transport_security import TransportSecuritySettings

    host = normalize_host(config.HTTP_HOST if host is None else host)
    port = config.HTTP_PORT if port is None else port
    path = normalize_path(config.HTTP_PATH if path is None else path)

    server.mcp.settings.host = host
    server.mcp.settings.port = port
    server.mcp.settings.streamable_http_path = path
    # The SDK's own Host/Origin checking stays OFF: bearer_guard implements that policy (see its
    # docstring for why), and this middleware would otherwise reject the very deployments the
    # allowlist knobs exist for. Its POST Content-Type check runs regardless of the flag, which is
    # the reason the middleware is still configured at all.
    server.mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    # FastMCP caches its StreamableHTTP session manager on the first build, and that manager's
    # run() is single-use — so a SECOND build in the same process (a retried start, a test) would
    # hand out an app whose lifespan raises. Dropping the cached one makes build_app repeatable;
    # the attribute is private, so this stays a best-effort reset rather than a hard requirement.
    if hasattr(server.mcp, "_session_manager"):
        server.mcp._session_manager = None
    return bearer_guard(
        server.mcp.streamable_http_app(),
        token,
        hosts=allowed_host_names(host) if hosts is _FROM_CONFIG else hosts,
        origins=allowed_origins() if origins is _FROM_CONFIG else origins,
    )


def check_token(token: str) -> str:
    """Return the token to serve with, or raise :class:`HttpServeError` explaining the refusal.
    The one place the "no unauthenticated HTTP server" rule lives."""
    token = (token or "").strip()
    if not token:
        raise HttpServeError(
            "refusing to serve over HTTP without a token: set CITADEL_HTTP_TOKEN in your "
            'workspace .env (generate one with: python -c "import secrets; '
            'print(secrets.token_urlsafe(32))"). The HTTP surface exposes your whole wiki — and, '
            "unless --read-only, the tools that write it and spawn your coding-agent CLI."
        )
    if len(token) < MIN_TOKEN_CHARS:
        raise HttpServeError(
            f"refusing to serve over HTTP with a {len(token)}-character token: use at least "
            f'{MIN_TOKEN_CHARS} random characters (python -c "import secrets; '
            'print(secrets.token_urlsafe(32))").'
        )
    return token


def check_hosts(host: str, configured: list[str] | None = None) -> list[str] | None:
    """Return the ``Host`` allowlist to serve with, or raise :class:`HttpServeError` when none can
    be derived — the twin of :func:`check_token` for the rebinding guard.

    The one case that cannot be derived is a WILDCARD bind (``0.0.0.0``/``::``) with nothing
    configured: clients address such a server by some OTHER name (the machine's LAN address, a
    DNS name, a tunnel hostname), and accepting every ``Host`` silently would drop the rebinding
    protection exactly where the server is most exposed. Refusing at start-up — naming the knob —
    beats a server that binds happily and then rejects every request it receives."""
    resolved = allowed_host_names(host, configured)
    if resolved is not None and not resolved:
        raise HttpServeError(
            f"refusing to serve on the wildcard bind {format_host(host)}: no Host allowlist can be "
            "derived from it (a client never sends that as its Host), so DNS-rebinding protection "
            "would reject every request. Name the host(s) clients will use — "
            "CITADEL_HTTP_ALLOWED_HOSTS=wiki.example.com,192.168.1.10 — or set it to * if a proxy "
            "in front already filters Host. A loopback bind behind a tunnel needs no wildcard bind "
            "at all: keep 127.0.0.1 and name the tunnel's hostname in that same knob."
        )
    return resolved


def serve(
    *,
    host: str | None = None,
    port: int | None = None,
    path: str | None = None,
    read_only: bool | None = None,
    token: str | None = None,
) -> None:
    """Run the MCP server over Streamable HTTP until interrupted.

    Refuses to start without a usable token (:func:`check_token`) or with a bind whose ``Host``
    allowlist cannot be derived (:func:`check_hosts`), warns on a non-loopback bind, applies
    read-only mode when asked, opts into the page-snapshot cache exactly like the stdio server (this
    is the same long-lived reader), and hands the guarded app to uvicorn. Every argument defaults to
    its ``CITADEL_HTTP_*`` config value, read at call time."""
    from . import pagecache

    # Normalized to the BIND spelling up front: everything downstream (the warning, the app, the
    # banner, uvicorn) works from one form, so a bracketed IPv6 literal cannot reach the socket
    # layer that rejects it.
    host = normalize_host(config.HTTP_HOST if host is None else host)
    port = config.HTTP_PORT if port is None else port
    path = config.HTTP_PATH if path is None else path
    read_only = config.HTTP_READ_ONLY if read_only is None else read_only
    resolved = check_token(config.HTTP_TOKEN if token is None else token)
    hosts = check_hosts(host)

    if not is_loopback(host):
        print(
            f"WARNING: binding {format_host(host)}:{port} exposes citadel beyond this machine over PLAIN HTTP. "
            "Prefer a loopback bind behind a tunnel that terminates TLS (cloudflared, tailscale, "
            "ssh -R); the bearer token is the only thing between the network and your wiki.",
            file=sys.stderr,
        )

    server.set_read_only(bool(read_only))
    pagecache.enable()
    app = build_app(resolved, host=host, port=port, path=path, hosts=hosts)

    import uvicorn

    mode = "read-only" if read_only else "read+write"
    accepted = "any Host" if hosts is None else f"Host: {', '.join(hosts)}"
    print(
        f"citadel MCP (Streamable HTTP, {mode}) on http://{format_host(host)}:{port}{normalize_path(path)} "
        f"[accepts {accepted}] - clients must send: Authorization: Bearer <CITADEL_HTTP_TOKEN>",
        file=sys.stderr,
    )
    uvicorn.run(app, host=host, port=port, log_level="warning")


def normalize_path(path: str) -> str:
    """The endpoint path as SERVED (leading slash guaranteed) — `CITADEL_HTTP_PATH=mcp` and
    `=/mcp` mean the same endpoint. The one place that rule lives, so the banner, ``doctor``, and
    the app itself can never disagree about where the server answers."""
    return path if path.startswith("/") else "/" + path
