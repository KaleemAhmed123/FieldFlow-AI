"""Build step 12 Task 4 — the Hosted-MCP client, proven offline.

The MCP wire session is the gated-live bit (needs the `mcp` SDK + the activated server). What we can
and do test offline: the OAuth refresh-token -> access-token exchange (httpx.MockTransport), token
caching, the token-url derivation, and the build_mcp_client arming gate. No SDK, no network.
"""

from __future__ import annotations

import httpx
from app.config import Settings
from app.mcp.client import SalesforceMcpClient, _default_token_url, build_mcp_client

SERVER = "https://inst.my.salesforce.com/mcp/abc"
TOKEN_PATH = "/services/oauth2/token"


def _client(handler) -> SalesforceMcpClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return SalesforceMcpClient(server_url=SERVER, client_id="id", client_secret="sec",
                               refresh_token="rt-1", http=http)


def test_token_url_derived_from_server_host() -> None:
    assert _default_token_url(SERVER) == "https://inst.my.salesforce.com/services/oauth2/token"


def test_refresh_token_exchanged_for_access_token() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == TOKEN_PATH
        body = dict(httpx.QueryParams(req.content.decode()))
        assert body["grant_type"] == "refresh_token" and body["refresh_token"] == "rt-1"
        return httpx.Response(200, json={"access_token": "ac-1", "expires_in": 7200})

    assert _client(handler).access_token() == "ac-1"


def test_access_token_cached_until_expiry() -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"access_token": "ac-1", "expires_in": 7200})

    c = _client(handler)
    c.access_token()
    c.access_token()
    assert calls["n"] == 1  # second call used the cache


def test_build_is_none_when_unarmed() -> None:
    # Ids set but no refresh token → still off (the one-time login hasn't run).
    s = Settings(sf_mcp_server_url=SERVER, sf_mcp_client_id="id", sf_mcp_client_secret="sec")
    assert build_mcp_client(s) is None


def test_build_is_client_when_fully_armed() -> None:
    s = Settings(sf_mcp_server_url=SERVER, sf_mcp_client_id="id", sf_mcp_client_secret="sec",
                 sf_mcp_refresh_token="rt-1")
    assert isinstance(build_mcp_client(s), SalesforceMcpClient)
