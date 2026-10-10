"""A thin MCP client over a Salesforce Hosted MCP server (build step 12 Task 4).

The copilot asks this client "what tools are there?" and "run this tool" — the LLM picks; the client
just carries the call. Two layers, split so the fiddly auth is unit-testable offline and the MCP
wire call is the one gated-live bit:

  - TOKEN (testable offline): Hosted MCP auth is OAuth2 + PKCE, so there is no headless client-
    credentials grant. The admin runs `python -m app.mcp.login` ONCE to mint a refresh token; this
    client swaps that refresh token for a short-lived access token (cached, refetched on expiry)
    with a plain httpx POST. That exchange is covered by tests via httpx.MockTransport.
  - SESSION (gated live): open a Streamable HTTP MCP session to the server url with the access token
    as a bearer, then list/call tools through the `mcp` SDK. Lazy-imported so offline imports/tests
    never need the SDK or the network — verified live against the org, like the Apex reads were.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from app.logging import get_logger

if TYPE_CHECKING:
    import httpx

log = get_logger("mcp")

# Refresh a bit early so a token never expires mid-call.
_EXPIRY_SKEW_S = 30.0


def _default_token_url(server_url: str) -> str:
    """The org's OAuth token endpoint, derived from the MCP server url's host."""
    parts = urlsplit(server_url)
    return f"{parts.scheme}://{parts.netloc}/services/oauth2/token"


class SalesforceMcpClient:
    def __init__(
        self, *, server_url: str, client_id: str, client_secret: str, refresh_token: str,
        token_url: str = "", timeout: float = 30.0, http: httpx.Client | None = None,
    ) -> None:
        self._server_url = server_url
        self._client_id, self._client_secret = client_id, client_secret
        self._refresh_token = refresh_token
        self._token_url = token_url or _default_token_url(server_url)
        self._timeout = timeout
        self._http = http  # injectable for tests
        self._access_token: str | None = None
        self._expires_at: float = 0.0

    def _client(self) -> httpx.Client:
        if self._http is None:
            import httpx

            self._http = httpx.Client(timeout=self._timeout)
        return self._http

    def access_token(self) -> str:
        """Refresh-token -> access-token, cached until about to expire (OAuth2 refresh grant)."""
        if self._access_token and time.time() < self._expires_at - _EXPIRY_SKEW_S:
            return self._access_token
        resp = self._client().post(self._token_url, data={
            "grant_type": "refresh_token", "refresh_token": self._refresh_token,
            "client_id": self._client_id, "client_secret": self._client_secret,
        })
        if resp.status_code >= 400:
            log.error("mcp.token_refresh_failed", status=resp.status_code, body=resp.text)
        resp.raise_for_status()
        body = resp.json()
        self._access_token = body["access_token"]
        # Salesforce refresh-grant responses omit expires_in; assume ~2h and lean on the 401 path.
        self._expires_at = time.time() + float(body.get("expires_in", 7200))
        log.info("mcp.access_token_refreshed")
        return self._access_token

    async def _session(self):  # noqa: ANN202 — context manager, mcp types are lazy
        """Open a Streamable HTTP MCP session with the bearer token. GATED LIVE: needs the `mcp` SDK
        + the activated Hosted MCP server. Returns an async context manager yielding a session."""
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        token = self.access_token()

        class _Ctx:
            async def __aenter__(_self):  # noqa: N805
                _self._http = httpx.AsyncClient(
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=httpx.Timeout(self._timeout, read=300.0),
                )
                _self._transport = streamablehttp_client(self._server_url, http_client=_self._http)
                read, write, _ = await _self._transport.__aenter__()
                _self._session = ClientSession(read, write)
                await _self._session.__aenter__()
                await _self._session.initialize()
                return _self._session

            async def __aexit__(_self, *exc):  # noqa: N805
                await _self._session.__aexit__(*exc)
                await _self._transport.__aexit__(*exc)
                await _self._http.aclose()

        return _Ctx()

    async def list_tools(self) -> list[dict[str, str]]:
        """The tools the server exposes — name + description (what the copilot LLM routes on)."""
        async with await self._session() as session:
            result = await session.list_tools()
            return [{"name": t.name, "description": t.description or ""} for t in result.tools]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Run one named tool and return its content (the copilot decides name + arguments)."""
        async with await self._session() as session:
            result = await session.call_tool(name, arguments)
            return result.content


def build_mcp_client(settings: Any) -> SalesforceMcpClient | None:
    """The one swap line: a live MCP client when the Hosted-MCP creds + refresh token are armed,
    else None (offline default — every test, a keyless boot). See hosted-mcp-setup.md."""
    if not settings.sf_mcp_armed:
        return None
    log.info("mcp.live", server_url=settings.sf_mcp_server_url)
    return SalesforceMcpClient(
        server_url=settings.sf_mcp_server_url, client_id=settings.sf_mcp_client_id,
        client_secret=settings.sf_mcp_client_secret, refresh_token=settings.sf_mcp_refresh_token,
        token_url=settings.sf_mcp_token_url,
    )
