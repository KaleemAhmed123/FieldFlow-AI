"""API-key gate (AI-SEC-01) — the one fix that stops an anonymous caller driving the pipeline.

A single shared secret in the `X-API-Key` header protects every route except a small allowlist the
uptime monitors and Render need, plus CORS preflight (which carries no custom header).

Mock-first convention, same as every other secret: a **blank** key leaves the gate OFF (local/dev,
tests). Set `API_KEY` on the server + `VITE_API_KEY` in the panel to turn it on. Making a blank key
fatal in production is P0-6 (a separate boot validator), kept out of here so this stays one concern.
"""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Open to everyone: liveness/readiness, the deep-deps probe, the version check.
# These are what UptimeRobot/Render hit and carry no sensitive data.
OPEN_PATHS = frozenset({"/health", "/ready", "/health/deps", "/version"})


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Reject any non-allowlisted request without the right `X-API-Key`. Constant-time compare."""

    def __init__(self, app, api_key: str) -> None:
        super().__init__(app)
        self._api_key = api_key

    async def dispatch(self, request: Request, call_next):
        if (
            not self._api_key                      # gate off (blank key — dev/test)
            or request.method == "OPTIONS"         # CORS preflight: no custom header is sent
            or request.url.path in OPEN_PATHS      # monitors
            or request.url.path.startswith("/webhooks/")  # Vonage/SF: external callers that can't
                                                   # send X-API-Key; each webhook authenticates
                                                   # itself (Vonage JWT / SF shared secret)
        ):
            return await call_next(request)
        presented = request.headers.get("x-api-key", "")
        if hmac.compare_digest(presented, self._api_key):
            return await call_next(request)
        return JSONResponse({"detail": "missing or invalid API key"}, status_code=401)
