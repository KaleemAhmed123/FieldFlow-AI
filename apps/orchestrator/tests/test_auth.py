"""AI-SEC-01: the API-key gate.

Blank key → gate OFF (dev/test). Set key → 401 without the header, 200 with the right one, 401 with
a wrong one; the monitor allowlist + CORS preflight stay open. Tested over the middleware + a stub
route in isolation (no DB/broker), so it stays fast and offline.
"""

from __future__ import annotations

from app.auth import ApiKeyMiddleware
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(api_key: str) -> TestClient:
    app = FastAPI()
    app.add_middleware(ApiKeyMiddleware, api_key=api_key)

    @app.get("/cases")
    def cases() -> dict:
        return {"ok": True}

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return TestClient(app)


def test_blank_key_leaves_the_gate_off() -> None:
    assert _client("").get("/cases").status_code == 200


def test_protected_route_requires_the_key() -> None:
    c = _client("secret123")
    assert c.get("/cases").status_code == 401                                    # no header
    assert c.get("/cases", headers={"X-API-Key": "wrong"}).status_code == 401    # wrong key
    assert c.get("/cases", headers={"X-API-Key": "secret123"}).status_code == 200  # right key


def test_allowlist_and_preflight_stay_open() -> None:
    c = _client("secret123")
    assert c.get("/health").status_code == 200          # monitor allowlist — no key needed
    assert c.options("/cases").status_code != 401       # CORS preflight passes the gate
