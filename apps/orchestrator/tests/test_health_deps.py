"""Build step 10: a down dep must give overall down/degraded, still return a body (200), and never
leak a secret. All offline — every dep is a fake, no keys, no network."""

from __future__ import annotations

import json

from app.commerce.razorpay import FakeRazorpay
from app.config import settings
from app.health import check_deps, reset_cache
from app.tools.vonage import FakeVonage

SECRET = "SUPERSECRET_TOKEN_123"


class _BoomSession:
    """A session whose SELECT 1 raises — and the error carries a password-bearing URL, exactly the
    kind of string the health body must never echo."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def execute(self, *a, **k):
        raise RuntimeError(f"connect failed: postgresql://postgres:{SECRET}@db:5432/postgres")


def _boom_sessionmaker() -> _BoomSession:
    return _BoomSession()


class _OpenBroker:
    is_open = True


async def test_down_dep_still_returns_body_and_leaks_no_secret(monkeypatch):
    reset_cache()
    # Plant the secret in every key-bearing setting: the body must not echo any of them.
    monkeypatch.setattr(settings, "groq_api_key", SECRET, raising=False)
    monkeypatch.setattr(settings, "gemini_api_key", SECRET, raising=False)
    monkeypatch.setattr(settings, "jina_api_key", SECRET, raising=False)
    monkeypatch.setattr(settings, "logfire_token", SECRET, raising=False)

    body = await check_deps(
        sessionmaker=_boom_sessionmaker,
        broker=_OpenBroker(),
        vonage=FakeVonage(),
        razorpay=FakeRazorpay(),
        settings=settings,
        deep=False,
        use_cache=False,
    )

    # Postgres (REQUIRED) is down -> overall down; the route returns a plain dict -> FastAPI 200.
    assert isinstance(body, dict)
    assert body["status"] == "down"
    assert body["checks"]["postgres"]["status"] == "down"
    assert body["checks"]["rabbitmq"]["status"] == "ok"
    # Cheap default makes no third-party calls: keyed deps are skipped, not pinged.
    assert body["checks"]["groq"]["status"] == "skipped"
    assert body["checks"]["jina"]["status"] == "skipped"
    # Armed-or-fake is informational and reflects the built client type.
    assert body["checks"]["vonage"]["status"] == "fake"
    assert body["checks"]["razorpay"]["status"] == "fake"
    # The one that matters: no key/secret (nor the password-bearing DB URL) anywhere in the body.
    assert SECRET not in json.dumps(body)


async def test_broker_none_is_down_even_with_healthy_db(sessionmaker):
    reset_cache()
    # Real in-memory DB (conftest fixture) -> postgres ok; only the queue is missing.
    body = await check_deps(
        sessionmaker=sessionmaker, broker=None,
        vonage=FakeVonage(), razorpay=FakeRazorpay(), settings=settings,
        deep=False, use_cache=False,
    )
    assert body["checks"]["postgres"]["status"] == "ok"
    assert body["checks"]["rabbitmq"]["status"] == "down"  # broker None -> required down
    assert body["status"] == "down"
