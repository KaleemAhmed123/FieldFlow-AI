"""Deep dependency-health check for `GET /health/deps` (build step 10).

One call reports every external dep's state. The design rules that matter:

- **Never throws.** Each check is wrapped so a timeout or error returns a `down`/`skipped` dict; the
  gather can't blow up the route — a dead dep still yields a 200 body.
- **Never leaks secrets.** Failure `detail` is always generic (`"unreachable"`), never `str(exc)` —
  a DB/driver error can carry the connection URL *with the password*. Keys never enter the body.
- **Cost guard.** The cheap default makes ZERO third-party calls (only our own DB + queue). The real
  vendor pings (groq/gemini `models.list`, jina HEAD) are gated behind `deep=True`, and the whole
  result is cached (keyed by the `deep` flag) so a ~5s panel poll can't hammer or spend credit.
"""

from __future__ import annotations

import asyncio
from time import monotonic, perf_counter

import httpx
from sqlalchemy import text

# Overall = worst-of REQUIRED; OPTIONAL can only knock ok -> degraded; the rest are info-only.
REQUIRED = ("postgres", "rabbitmq")
OPTIONAL = ("groq", "gemini", "jina", "logfire")
_PG_TIMEOUT = 2.0
_PING_TIMEOUT = 4.0

# Per-process, in-memory cache: {deep_flag: (monotonic_ts, body)}. A probe, not a source of truth.
_CACHE: dict[bool, tuple[float, dict]] = {}


def reset_cache() -> None:
    """Clear the cache (tests call this to stay independent)."""
    _CACHE.clear()


def _ms(start: float) -> float:
    return round((perf_counter() - start) * 1000, 1)


async def _check_postgres(sessionmaker) -> dict:
    start = perf_counter()
    try:
        async with asyncio.timeout(_PG_TIMEOUT):
            async with sessionmaker() as session:
                await session.execute(text("SELECT 1"))
        return {"status": "ok", "latencyMs": _ms(start)}
    except Exception:  # noqa: BLE001 — generic detail only; a DB error can contain the password URL
        return {"status": "down", "latencyMs": _ms(start), "detail": "unreachable"}


async def _check_rabbitmq(broker) -> dict:
    if broker is None:
        return {"status": "down", "detail": "broker unavailable"}
    start = perf_counter()
    try:
        ok = broker.is_open
        return {"status": "ok" if ok else "down", "latencyMs": _ms(start)}
    except Exception:  # noqa: BLE001
        return {"status": "down", "detail": "check failed"}


def _groq_models_list(key: str) -> None:
    from groq import Groq

    Groq(api_key=key).models.list()  # free metadata call — proves the key, costs no tokens


def _gemini_models_list(key: str) -> None:
    from google import genai

    list(genai.Client(api_key=key).models.list())  # iterate to force the request


async def _check_llm(key: str, deep: bool, lister) -> dict:
    if not key:
        return {"status": "skipped", "detail": "not configured"}
    if not deep:
        return {"status": "skipped", "detail": "key set; deep check only"}
    start = perf_counter()
    try:
        async with asyncio.timeout(_PING_TIMEOUT):
            await asyncio.to_thread(lister, key)
        return {"status": "ok", "latencyMs": _ms(start)}
    except Exception:  # noqa: BLE001
        return {"status": "down", "latencyMs": _ms(start), "detail": "models.list failed"}


async def _check_jina(key: str, deep: bool) -> dict:
    if not key:
        return {"status": "skipped", "detail": "not configured"}
    if not deep:
        return {"status": "skipped", "detail": "key set; not pinged (billable)"}
    start = perf_counter()
    try:
        # Unauthenticated HEAD — reachability only. Never send the key, never embed (billable).
        async with asyncio.timeout(_PING_TIMEOUT):
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.head("https://api.jina.ai/")
        return {"status": "ok", "latencyMs": _ms(start), "detail": "reachable (not embedded)"}
    except Exception:  # noqa: BLE001
        return {"status": "down", "latencyMs": _ms(start), "detail": "unreachable"}


def _check_logfire(token: str) -> dict:
    # Config-present only; never touches the network.
    return {"status": "ok", "detail": "configured"} if token else {
        "status": "skipped", "detail": "not configured"}


def _check_vonage(vonage) -> dict:
    from app.tools.vonage import FakeVonage

    if isinstance(vonage, FakeVonage):
        return {"status": "fake", "detail": "not armed"}
    return {"status": "armed"}


def _check_razorpay(razorpay) -> dict:
    from app.commerce.razorpay import FakeRazorpay

    if isinstance(razorpay, FakeRazorpay):
        return {"status": "fake", "detail": "not armed"}
    return {"status": "test-mode"}


def _overall(checks: dict) -> str:
    overall = "ok"
    if any(checks[n]["status"] == "down" for n in OPTIONAL):
        overall = "degraded"
    if any(checks[n]["status"] != "ok" for n in REQUIRED):  # required wins — forces down
        overall = "down"
    return overall


async def check_deps(
    *, sessionmaker, broker, vonage, razorpay, settings, deep: bool = False,
    ttl: float = 30.0, use_cache: bool = True,
) -> dict:
    """Run every dep check concurrently and return the health body. Pure (all deps injected) so the
    route wires `app.state` in and the test wires fakes in. Never raises."""
    now = monotonic()
    if use_cache and deep in _CACHE and now - _CACHE[deep][0] < ttl:
        return {**_CACHE[deep][1], "cached": True}

    pg, rmq, groq, gemini, jina = await asyncio.gather(
        _check_postgres(sessionmaker),
        _check_rabbitmq(broker),
        _check_llm(settings.groq_api_key, deep, _groq_models_list),
        _check_llm(settings.gemini_api_key, deep, _gemini_models_list),
        _check_jina(settings.jina_api_key, deep),
    )
    checks = {
        "postgres": pg, "rabbitmq": rmq, "groq": groq, "gemini": gemini, "jina": jina,
        "logfire": _check_logfire(settings.logfire_token),  # sync, instant — no network
        "vonage": _check_vonage(vonage),
        "razorpay": _check_razorpay(razorpay),
    }
    body = {"status": _overall(checks), "deep": deep, "checks": checks}
    _CACHE[deep] = (now, body)
    return body
