"""MCP clients over Streamable HTTP — the AGENTIC path for the admin copilot.

Two sources, one wire protocol:
  - Salesforce Hosted MCP (OAuth2 + PKCE). No headless client-credentials grant, so the admin runs
    `python -m app.mcp.login` ONCE to mint a refresh token; this client swaps that refresh token for
    short-lived access tokens (cached, refetched on expiry) with a plain httpx POST. That
    exchange is covered by tests via httpx.MockTransport.
  - E-com Hosted MCP (`/api/mcp`, no auth — a POC admin service). Same Streamable-HTTP session, no
    bearer.

The session layer (list/call tools) is shared via `_McpReach`; only the auth headers differ. It is
lazy-imported so offline imports/tests never need the `mcp` SDK or the network — the wire call is
the one gated-live bit, verified live against each server.
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


def _open_session(server_url: str, headers: dict[str, str]):  # noqa: ANN202 — lazy mcp types
    """Async context manager yielding an initialized MCP ClientSession over Streamable HTTP.

    GATED LIVE: needs the `mcp` SDK + a reachable server. `headers` carries auth (a Bearer for
    Salesforce, empty for the open e-com server). SDK 2.3.0: `streamable_http_client` (underscored)
    returns a 2-tuple (read, write); build the http client with the SDK helper so its own httpx fork
    + MCP timeouts are used.
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

    class _Ctx:
        async def __aenter__(_self):  # noqa: N805
            _self._http = create_mcp_http_client(headers=headers or None)
            _self._transport = streamable_http_client(server_url, http_client=_self._http)
            read, write = await _self._transport.__aenter__()
            _self._session = ClientSession(read, write)
            await _self._session.__aenter__()
            await _self._session.initialize()
            return _self._session

        async def __aexit__(_self, *exc):  # noqa: N805
            await _self._session.__aexit__(*exc)
            await _self._transport.__aexit__(*exc)
            await _self._http.aclose()

    return _Ctx()


class _McpReach:
    """Shared read/call surface over Streamable-HTTP MCP. Subclasses supply `_headers()`."""

    _server_url: str

    def _headers(self) -> dict[str, str]:
        return {}

    async def list_tools(self) -> list[dict[str, Any]]:
        """Tools the server exposes — name, description (what the LLM routes on), and the
        JSON-Schema the LLM must fill to call them (inputSchema)."""
        async with _open_session(self._server_url, self._headers()) as session:
            result = await session.list_tools()
            # SDK 2.3.0 renamed the attribute to `input_schema` (wire alias `inputSchema`); keep the
            # old name as a fallback so an SDK up/downgrade can't silently blank the schema again.
            return [{"name": t.name, "description": t.description or "",
                     "inputSchema": getattr(t, "input_schema", None)
                     or getattr(t, "inputSchema", None) or {}} for t in result.tools]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Run one named tool and return its content blocks (copilot decides name + arguments)."""
        async with _open_session(self._server_url, self._headers()) as session:
            result = await session.call_tool(name, arguments)
            return result.content


class SalesforceMcpClient(_McpReach):
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
        self._rt_dirty = False  # set when a refresh rotated the token → the route persists it

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
        # Some ECAs ROTATE the refresh token: each refresh invalidates the prior one and returns a
        # new one. Keep it AND flag it dirty so the route persists it to the DB — else a restart
        # reads the now-stale env copy and the SF copilot dies (see app/db/secrets.py).
        if (new_rt := body.get("refresh_token")) and new_rt != self._refresh_token:
            self._refresh_token = new_rt
            self._rt_dirty = True
        # Salesforce refresh-grant responses omit expires_in; assume ~2h and lean on the 401 path.
        self._expires_at = time.time() + float(body.get("expires_in", 7200))
        log.info("mcp.access_token_refreshed")
        return self._access_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token()}"}

    @property
    def refresh_token(self) -> str:
        return self._refresh_token

    def set_refresh_token(self, token: str) -> None:
        """Seed the client from a persisted token on boot (no dirty flag — it's already saved)."""
        self._refresh_token = token

    def pop_rotated_token(self) -> str | None:
        """The new refresh token if a rotation happened since last checked, else None. Clears the
        flag — the caller is expected to persist what it returns."""
        if not self._rt_dirty:
            return None
        self._rt_dirty = False
        return self._refresh_token


class EcomMcpClient(_McpReach):
    """The e-com inventory MCP server (`/api/mcp`). Open (no auth) — POC admin service."""

    def __init__(self, server_url: str) -> None:
        self._server_url = server_url


def build_mcp_client(settings: Any) -> SalesforceMcpClient | None:
    """The one swap line: a live Salesforce MCP client when the Hosted-MCP creds + refresh token are
    armed, else None (offline default — every test, a keyless boot). See hosted-mcp-setup.md."""
    if not settings.sf_mcp_armed:
        return None
    log.info("mcp.live", server_url=settings.sf_mcp_server_url)
    return SalesforceMcpClient(
        server_url=settings.sf_mcp_server_url, client_id=settings.sf_mcp_client_id,
        client_secret=settings.sf_mcp_client_secret, refresh_token=settings.sf_mcp_refresh_token,
        token_url=settings.sf_mcp_token_url,
    )


def build_ecom_mcp_client(settings: Any) -> EcomMcpClient | None:
    """E-com MCP client. Explicit `ECOM_MCP_URL` wins; else derived from `ECOM_API_URL` + `/api/mcp`
    (so it arms automatically wherever the e-com service is already wired). Blank both → None."""
    url = getattr(settings, "ecom_mcp_url", "") or (
        f"{settings.ecom_api_url.rstrip('/')}/api/mcp" if settings.ecom_api_url else "")
    if not url:
        return None
    log.info("mcp.ecom.live", server_url=url)
    return EcomMcpClient(url)
