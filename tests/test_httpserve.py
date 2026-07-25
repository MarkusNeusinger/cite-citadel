"""Offline tests for the opt-in Streamable HTTP transport (``citadel/httpserve.py``).

Nothing here binds a port: the guarded ASGI app is driven IN-PROCESS through starlette's
TestClient (httpx ships with ``mcp``), and :func:`httpserve.serve` is exercised with ``uvicorn.run``
monkeypatched, so the whole surface — the mandatory token, the 401 path, the loopback warning, the
read-only switch, and the CLI wiring — is covered without a socket.
"""

from __future__ import annotations

import pytest

from citadel import cli, config, httpserve, server


starlette_testclient = pytest.importorskip("starlette.testclient")
TestClient = starlette_testclient.TestClient

TOKEN = "test-token-with-enough-entropy"
# The app is built for this bind address, and DNS-rebinding protection checks the Host header
# against it — so the test client must speak as that host (TestClient's default is "testserver",
# which the protection correctly rejects; test_dns_rebinding_protection_is_enabled pins that).
BASE_URL = "http://127.0.0.1:8765"


@pytest.fixture
def app(tmp_citadel):
    """The token-guarded ASGI app on a temp workspace, on a fixed host/port so the Host allowlist
    is deterministic."""
    return httpserve.build_app(TOKEN, host="127.0.0.1", port=8765, path="/mcp")


@pytest.fixture(autouse=True)
def _restore_read_only():
    """Read-only mode is process-global (like the config it mirrors) — never leak it into another
    test's server surface."""
    yield
    server.set_read_only(False)


# --- the token gate ---------------------------------------------------------------------------


def test_request_without_a_token_is_401(app):
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.post("/mcp", json={"jsonrpc": "2.0", "method": "ping", "id": 1})
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Bearer")
    assert "unauthorized" in response.json()["error"]["message"]


@pytest.mark.parametrize(
    "header",
    [
        "Bearer wrong-token-entirely-different",
        f"Bearer {TOKEN}x",  # a prefix of the real token must not pass
        f"Bearer {TOKEN[:-1]}",
        TOKEN,  # no scheme
        "Basic " + TOKEN,
        "",
    ],
)
def test_bad_authorization_headers_are_401(app, header):
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.post(
            "/mcp", json={"jsonrpc": "2.0", "method": "ping", "id": 1}, headers={"Authorization": header}
        )
    assert response.status_code == 401


def test_bearer_scheme_is_case_insensitive_and_the_valid_token_reaches_mcp(app):
    """A correct token gets PAST the guard: the MCP layer then answers on its own terms (a
    session-less POST is a 4xx/2xx from the transport, never the guard's 401)."""
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "ping", "id": 1},
            headers={"Authorization": f"bearer {TOKEN}", "Accept": "application/json, text/event-stream"},
        )
    assert response.status_code != 401


def test_a_valid_token_can_initialize_a_session_and_list_tools(app):
    """End-to-end through the real transport: initialize, then tools/list — the whole tool surface
    is reachable over HTTP exactly as over stdio."""
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    with TestClient(app, base_url=BASE_URL) as client:
        init = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            },
        )
        assert init.status_code == 200, init.text
        assert "citadel" in init.text
        session = init.headers.get("mcp-session-id")
        assert session
        session_headers = {**headers, "mcp-session-id": session}
        client.post("/mcp", headers=session_headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        listed = client.post("/mcp", headers=session_headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert listed.status_code == 200, listed.text
    assert "wiki_search" in listed.text and "wiki_ingest" in listed.text


def test_the_compare_is_length_blind(app):
    """Both sides are hashed before hmac.compare_digest, which is only constant-time for
    equal-length inputs — so a token of a DIFFERENT length is refused by the same code path as a
    same-length wrong one, with nothing about the length in the comparison."""
    with TestClient(app, base_url=BASE_URL) as client:
        for candidate in ("x", TOKEN * 3, TOKEN[:4]):
            response = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "ping", "id": 1},
                headers={"Authorization": f"Bearer {candidate}"},
            )
            assert response.status_code == 401


def test_lifespan_scope_is_not_token_guarded():
    """Only HTTP scopes are checked — the lifespan startup that boots the MCP session manager must
    pass through, or the server could never start."""
    seen = []

    async def inner(scope, receive, send):
        seen.append(scope["type"])

    guarded = httpserve.bearer_guard(inner, TOKEN)
    import asyncio

    asyncio.run(guarded({"type": "lifespan"}, None, None))
    assert seen == ["lifespan"]


# --- the refusal to serve unauthenticated -----------------------------------------------------


@pytest.mark.parametrize("token", ["", "   ", "short", "0123456789abcde"])
def test_check_token_refuses_missing_and_weak_tokens(token):
    with pytest.raises(httpserve.HttpServeError) as excinfo:
        httpserve.check_token(token)
    assert "CITADEL_HTTP_TOKEN" in str(excinfo.value) or "characters" in str(excinfo.value)


def test_check_token_accepts_a_generated_token():
    assert httpserve.check_token("  " + "a" * httpserve.MIN_TOKEN_CHARS + "  ") == "a" * httpserve.MIN_TOKEN_CHARS


def test_serve_refuses_without_a_token(tmp_citadel, monkeypatch):
    monkeypatch.setattr(config, "HTTP_TOKEN", "")
    ran = []
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: ran.append(k))
    with pytest.raises(httpserve.HttpServeError):
        httpserve.serve()
    assert ran == []


# --- bind address / warnings ------------------------------------------------------------------


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "[::1]", "127.0.0.53"])
def test_loopback_hosts_are_recognized(host):
    assert httpserve.is_loopback(host)


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "example.com", "::"])
def test_non_loopback_hosts_are_recognized(host):
    assert not httpserve.is_loopback(host)


def test_serve_warns_on_a_non_loopback_bind(tmp_citadel, monkeypatch, capsys):
    monkeypatch.setattr(config, "HTTP_TOKEN", TOKEN)
    calls = {}
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: calls.update(kwargs))
    httpserve.serve(host="0.0.0.0", port=9001)
    err = capsys.readouterr().err
    assert "WARNING" in err and "0.0.0.0" in err
    assert calls["host"] == "0.0.0.0" and calls["port"] == 9001


def test_serve_does_not_warn_on_loopback(tmp_citadel, monkeypatch, capsys):
    monkeypatch.setattr(config, "HTTP_TOKEN", TOKEN)
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: None)
    httpserve.serve(host="127.0.0.1", port=9002)
    err = capsys.readouterr().err
    assert "WARNING" not in err
    assert "Bearer" in err  # the startup banner still tells the operator how to connect


@pytest.mark.parametrize(
    "given,bind,url",
    [
        ("127.0.0.1", "127.0.0.1", "127.0.0.1"),
        ("  localhost  ", "localhost", "localhost"),
        ("::1", "::1", "[::1]"),
        ("[::1]", "::1", "[::1]"),  # the URL spelling must not reach the socket layer
        ("0.0.0.0", "0.0.0.0", "0.0.0.0"),
    ],
)
def test_host_spellings_round_trip(given, bind, url):
    assert httpserve.normalize_host(given) == bind
    assert httpserve.format_host(given) == url


def test_serve_hands_uvicorn_the_bind_spelling_of_an_ipv6_host(tmp_citadel, monkeypatch, capsys):
    """A bracketed IPv6 literal is a URL spelling — uvicorn rejects it as a bind address, so serve
    normalizes before binding while still printing a copy-pasteable bracketed URL."""
    monkeypatch.setattr(config, "HTTP_TOKEN", TOKEN)
    calls = {}
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: calls.update(kwargs))
    httpserve.serve(host="[::1]", port=9003)
    assert calls["host"] == "::1"
    assert "http://[::1]:9003/mcp" in capsys.readouterr().err


def test_allowed_hosts_of_an_ipv6_bind_are_bracketed():
    """The Host header a client sends for an IPv6 server is bracketed — the allowlist must match
    that spelling or every request would fail the rebinding check."""
    allowed = httpserve._allowed_hosts("::1", 8765)
    assert "[::1]:8765" in allowed
    assert "::1:8765" not in allowed


def test_allowed_hosts_cover_the_loopback_aliases():
    allowed = httpserve._allowed_hosts("127.0.0.1", 8765)
    assert "127.0.0.1:8765" in allowed
    assert "localhost:8765" in allowed
    assert "127.0.0.1:*" in allowed


def test_allowed_hosts_of_a_public_bind_stay_that_host():
    allowed = httpserve._allowed_hosts("0.0.0.0", 8765)
    assert allowed == ["0.0.0.0", "0.0.0.0:8765", "0.0.0.0:*"]


def test_dns_rebinding_protection_is_enabled(app):
    """A request whose Host header is not the bound address is refused by the SDK's transport
    security — a browser on some other page cannot drive this server."""
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "ping", "id": 1},
            headers={"Authorization": f"Bearer {TOKEN}", "Host": "evil.example.com"},
        )
    assert response.status_code == 421


def test_build_app_normalizes_a_pathless_endpoint(tmp_citadel):
    httpserve.build_app(TOKEN, host="127.0.0.1", port=8765, path="mcp")
    assert server.mcp.settings.streamable_http_path == "/mcp"


@pytest.mark.parametrize("given", ["/mcp", "mcp"])
def test_normalize_path_guarantees_the_leading_slash(given):
    assert httpserve.normalize_path(given) == "/mcp"


def test_serve_banner_normalizes_a_pathless_endpoint(tmp_citadel, monkeypatch, capsys):
    monkeypatch.setattr(config, "HTTP_TOKEN", TOKEN)
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: None)
    httpserve.serve(host="127.0.0.1", port=9004, path="mcp")
    assert "http://127.0.0.1:9004/mcp" in capsys.readouterr().err


# --- read-only mode ---------------------------------------------------------------------------


def test_read_only_refuses_the_mutating_tools_and_keeps_the_readers(seeded_http_wiki):
    server.set_read_only(True)
    assert server.read_only() is True
    assert "read-only" in server.wiki_ingest()
    assert "read-only" in server.wiki_capture("a durable note", source="Kim, chat 2026-07-25")
    # The eleven readers are untouched.
    assert "Transformer" in server.wiki_index()


def test_read_only_refusal_never_writes_the_capture_log(seeded_http_wiki, tmp_citadel):
    server.set_read_only(True)
    server.wiki_capture("a durable note", source="Kim, chat 2026-07-25")
    assert not (tmp_citadel.raw / "captures").exists()


def test_mutating_tools_are_still_registered_in_read_only_mode():
    """Read-only declines to ACT; it never changes the advertised tool surface, so a client's
    tool list is identical either way."""
    server.set_read_only(True)
    names = {tool.name for tool in _list_tools()}
    assert {"wiki_capture", "wiki_ingest"} <= names


def test_serve_applies_read_only(tmp_citadel, monkeypatch):
    monkeypatch.setattr(config, "HTTP_TOKEN", TOKEN)
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: None)
    httpserve.serve(read_only=True)
    assert server.read_only() is True


def test_serve_defaults_read_only_to_the_config_knob(tmp_citadel, monkeypatch):
    monkeypatch.setattr(config, "HTTP_TOKEN", TOKEN)
    monkeypatch.setattr(config, "HTTP_READ_ONLY", True)
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: None)
    httpserve.serve()
    assert server.read_only() is True


# --- CLI wiring -------------------------------------------------------------------------------


def test_cli_serve_without_http_runs_the_stdio_server(tmp_citadel, monkeypatch):
    ran = []
    monkeypatch.setattr("citadel.server.main", lambda: ran.append("stdio"))
    assert cli.main(["serve"]) == 0
    assert ran == ["stdio"]


def test_cli_serve_http_passes_the_flags_through(tmp_citadel, monkeypatch):
    seen = {}
    monkeypatch.setattr(httpserve, "serve", lambda **kwargs: seen.update(kwargs))
    assert cli.main(["serve", "--http", "--host", "0.0.0.0", "--port", "9100", "--path", "/wiki", "--read-only"]) == 0
    assert seen == {"host": "0.0.0.0", "port": 9100, "path": "/wiki", "read_only": True}


def test_cli_serve_http_defaults_are_none_so_config_decides(tmp_citadel, monkeypatch):
    seen = {}
    monkeypatch.setattr(httpserve, "serve", lambda **kwargs: seen.update(kwargs))
    assert cli.main(["serve", "--http"]) == 0
    assert seen == {"host": None, "port": None, "path": None, "read_only": None}


def test_cli_serve_http_without_a_token_exits_2(tmp_citadel, monkeypatch, capsys):
    monkeypatch.setattr(config, "HTTP_TOKEN", "")
    assert cli.main(["serve", "--http"]) == 2
    assert "CITADEL_HTTP_TOKEN" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["serve", "--port", "9000"],
        ["serve", "--host", "0.0.0.0"],
        ["serve", "--path", "/mcp"],
        ["serve", "--read-only"],
    ],
)
def test_cli_serve_rejects_http_flags_without_http(tmp_citadel, monkeypatch, capsys, argv):
    """An HTTP flag on a stdio run is a usage error, never a silently ignored setting."""
    monkeypatch.setattr("citadel.server.main", lambda: pytest.fail("stdio server must not start"))
    assert cli.main(argv) == 2
    assert "--http only" in capsys.readouterr().err


# --- helpers ----------------------------------------------------------------------------------


def _list_tools():
    import asyncio

    return asyncio.run(server.mcp.list_tools())


@pytest.fixture
def seeded_http_wiki(tmp_citadel, seed_page):
    """A one-page wiki so the read-only tests can prove the readers still answer."""
    (tmp_citadel.raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    seed_page(
        "concepts/transformer.md",
        {
            "type": "Concept",
            "title": "Transformer",
            "description": "Self-attention architecture.",
            "tags": ["ml"],
            "resource": "raw/notes.md",
        },
        "Transformers use self-attention.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/notes.md](../../raw/notes.md) - notes (ingested 2026-06-21)\n",
    )
    from citadel import store

    store.rebuild_indexes()
    return tmp_citadel
