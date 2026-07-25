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
* **DNS-rebinding protection on.** The MCP SDK's transport-security middleware is enabled with
  the bound host/port (and its loopback aliases) as the allowed ``Host``/``Origin`` values, so a
  web page the user happens to visit cannot drive this server through their browser.
* **Optional read-only mode.** ``--read-only`` / ``CITADEL_HTTP_READ_ONLY=1`` switches the two
  mutating tools off for the process (:func:`citadel.server.set_read_only`), leaving the eleven
  readers — the "share my wiki, not my agent CLI" setup.

No new dependency: ``starlette``/``uvicorn`` already ship with ``mcp``, and the token check is a
~30-line ASGI wrapper rather than an OAuth resource server (citadel has no user model — the token
IS the user). :func:`build_app` returns the wrapped ASGI app for tests to drive in-process; only
:func:`serve` binds a port.
"""

from __future__ import annotations

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
_LOOPBACK_NAMES = ("localhost", "127.0.0.1", "::1", "[::1]")


class HttpServeError(RuntimeError):
    """A refusal to start the HTTP server (no token / too-short token). Carries the operator-facing
    explanation; the CLI prints it and exits non-zero."""


def is_loopback(host: str) -> bool:
    """True when ``host`` binds only this machine. Names are matched literally (no DNS lookup —
    resolving at config time would be a surprising network call); anything that parses as an IP is
    judged by the stdlib."""
    value = host.strip().strip("[]").lower()
    if value in ("localhost", ""):
        return True
    try:
        return ip_address(value).is_loopback
    except ValueError:
        return False


def _allowed_hosts(host: str, port: int) -> list[str]:
    """The ``Host`` header values this server accepts (DNS-rebinding protection). The configured
    bind address plus, for a loopback bind, its usual aliases — a client may say ``localhost``
    where uvicorn bound ``127.0.0.1``. Each is listed both with the concrete port and with the
    ``:*`` wildcard the SDK's matcher understands, so a tunnel that rewrites the port still
    reaches the server."""
    names = [host]
    if is_loopback(host):
        names.extend(name for name in _LOOPBACK_NAMES if name != host)
    allowed: list[str] = []
    for name in names:
        allowed.extend((name, f"{name}:{port}", f"{name}:*"))
    return allowed


def _unauthorized(detail: str) -> tuple[bytes, list[tuple[bytes, bytes]]]:
    """The 401 body + headers returned to an unauthenticated caller: a JSON-RPC-shaped error (the
    caller speaks MCP, so it can read it) and the ``WWW-Authenticate`` challenge the HTTP spec
    requires. Deliberately says only "unauthorized" — never whether a token was present, wrong
    length, or close."""
    body = json.dumps(
        {"jsonrpc": "2.0", "error": {"code": -32001, "message": f"unauthorized: {detail}"}, "id": None}
    ).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
        (b"www-authenticate", b'Bearer realm="citadel"'),
    ]
    return body, headers


def bearer_guard(app, token: str):
    """Wrap an ASGI ``app`` so every HTTP request must present ``Authorization: Bearer <token>``.

    Runs BEFORE the MCP session layer: an unauthenticated request is answered with 401 and never
    reaches a tool, a session, or the wiki. The comparison is
    :func:`hmac.compare_digest` (constant-time — a timing oracle on a shared secret is a real, if
    slow, attack), and the reply never distinguishes "no header" from "wrong token".
    Non-HTTP scopes (``lifespan``, which starts the MCP session manager) pass straight through."""
    expected = token.encode("utf-8")

    async def guarded(scope, receive, send):
        if scope.get("type") != "http":
            await app(scope, receive, send)
            return
        presented = b""
        for name, value in scope.get("headers", ()):
            if name.lower() == b"authorization":
                presented = value.strip()
                break
        prefix = b"bearer "
        ok = presented[: len(prefix)].lower() == prefix and hmac.compare_digest(presented[len(prefix) :], expected)
        if not ok:
            body, headers = _unauthorized("a valid bearer token is required")
            await send({"type": "http.response.start", "status": 401, "headers": headers})
            await send({"type": "http.response.body", "body": body})
            return
        await app(scope, receive, send)

    return guarded


def build_app(token: str, *, host: str | None = None, port: int | None = None, path: str | None = None):
    """The token-guarded ASGI app serving :mod:`citadel.server`'s MCP surface over Streamable HTTP.

    Settings are stamped onto the shared FastMCP instance first (endpoint path, bind address for
    the SDK's own transport-security check), then :meth:`FastMCP.streamable_http_app` builds the
    Starlette app and :func:`bearer_guard` wraps it. Exposed separately from :func:`serve` so tests
    can drive the whole stack in-process without binding a port."""
    from mcp.server.transport_security import TransportSecuritySettings

    host = config.HTTP_HOST if host is None else host
    port = config.HTTP_PORT if port is None else port
    path = config.HTTP_PATH if path is None else path
    if not path.startswith("/"):
        path = "/" + path

    server.mcp.settings.host = host
    server.mcp.settings.port = port
    server.mcp.settings.streamable_http_path = path
    server.mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_allowed_hosts(host, port),
        allowed_origins=[f"http://{name}" for name in _allowed_hosts(host, port)],
    )
    # FastMCP caches its StreamableHTTP session manager on the first build, and that manager's
    # run() is single-use — so a SECOND build in the same process (a retried start, a test) would
    # hand out an app whose lifespan raises. Dropping the cached one makes build_app repeatable;
    # the attribute is private, so this stays a best-effort reset rather than a hard requirement.
    if hasattr(server.mcp, "_session_manager"):
        server.mcp._session_manager = None
    return bearer_guard(server.mcp.streamable_http_app(), token)


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


def serve(
    *,
    host: str | None = None,
    port: int | None = None,
    path: str | None = None,
    read_only: bool | None = None,
    token: str | None = None,
) -> None:
    """Run the MCP server over Streamable HTTP until interrupted.

    Refuses to start without a usable token (:func:`check_token`), warns on a non-loopback bind,
    applies read-only mode when asked, opts into the page-snapshot cache exactly like the stdio
    server (this is the same long-lived reader), and hands the guarded app to uvicorn. Every
    argument defaults to its ``CITADEL_HTTP_*`` config value, read at call time."""
    from . import pagecache

    host = config.HTTP_HOST if host is None else host
    port = config.HTTP_PORT if port is None else port
    path = config.HTTP_PATH if path is None else path
    read_only = config.HTTP_READ_ONLY if read_only is None else read_only
    resolved = check_token(config.HTTP_TOKEN if token is None else token)

    if not is_loopback(host):
        print(
            f"WARNING: binding {host}:{port} exposes citadel beyond this machine over PLAIN HTTP. "
            "Prefer a loopback bind behind a tunnel that terminates TLS (cloudflared, tailscale, "
            "ssh -R); the bearer token is the only thing between the network and your wiki.",
            file=sys.stderr,
        )

    server.set_read_only(bool(read_only))
    pagecache.enable()
    app = build_app(resolved, host=host, port=port, path=path)

    import uvicorn

    mode = "read-only" if read_only else "read+write"
    print(
        f"citadel MCP (Streamable HTTP, {mode}) on http://{host}:{port}{build_path(path)} "
        "- clients must send: Authorization: Bearer <CITADEL_HTTP_TOKEN>",
        file=sys.stderr,
    )
    uvicorn.run(app, host=host, port=port, log_level="warning")


def build_path(path: str) -> str:
    """The endpoint path as advertised in the startup banner (leading slash guaranteed)."""
    return path if path.startswith("/") else "/" + path
