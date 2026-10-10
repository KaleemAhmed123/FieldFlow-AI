"""Read API for the control panel + health/metrics."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import select

from app.config import settings
from app.db.models import Case
from app.db.session import get_sessionmaker
from app.health import check_deps
from app.reconcile import find_lingering

router = APIRouter(tags=["api"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict:
    return {"status": "ready"}


@router.get("/health/deps")
async def health_deps(request: Request, deep: bool = False) -> dict:
    """Deep dependency health (build step 10): one call, every external dep's state. Cheap by
    default (DB + queue only, zero third-party calls); `?deep=1` adds the real vendor pings
    (groq/gemini models.list, jina reachability). Cached ~30s; never throws, never leaks keys."""
    return await check_deps(
        sessionmaker=get_sessionmaker(),
        broker=request.app.state.broker,
        vonage=request.app.state.vonage,
        razorpay=request.app.state.razorpay,
        settings=settings,
        deep=deep,
        ttl=settings.health_deps_cache_ttl_s,
    )


@router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/reconcile")
async def reconcile(older_than_minutes: int = 30) -> dict:
    """Reconciliation sweep (Step 12): non-terminal cases not updated for a while — stuck/lingering,
    worth an operator's eye. Read-only; no auto-heal (the ponytail ceiling)."""
    async with get_sessionmaker()() as session:
        lingering = await find_lingering(session, older_than_minutes)
    return {"olderThanMinutes": older_than_minutes, "count": len(lingering), "lingering": lingering}


@router.get("/tools")
async def list_tools(request: Request) -> dict:
    """The controlled MCP-shaped surface the graph is allowed to touch.

    Grouped by kind so the panel can show it plainly: reads are safe lookups the model may call
    freely; actions are validated functions that run the authority ladder and may refuse — the
    model calls them but never decides the result.
    """
    tools = request.app.state.toolbox.describe()
    return {
        "reads": [t for t in tools if t["kind"] == "read"],
        "actions": [t for t in tools if t["kind"] == "action"],
        "note": "Read = safe lookup. Action = validated; the function decides, may refuse.",
    }


@router.get("/copilot/tools")
async def copilot_tools(request: Request) -> dict:
    """The LIVE Salesforce Hosted MCP tools the copilot can discover (build step 12 Task 4 — the
    agentic path, distinct from /tools above which is our deterministic surface). Needs the SF_MCP_*
    creds + the one-time refresh token (`python -m app.mcp.login`), else returns unavailable."""
    client = request.app.state.mcp
    if client is None:
        return {"available": False,
                "detail": "MCP not armed — set SF_MCP_* + run `python -m app.mcp.login` "
                          "(docs/specs/field-service-recovery/hosted-mcp-setup.md)."}
    return {"available": True, "tools": await client.list_tools()}


@router.get("/dlq")
async def dlq(request: Request) -> dict:
    """Read-only peek at the dead-letter queue (Step 7b): how many messages are parked + their
    bodies. A failed event (e.g. Salesforce down) lands here instead of being lost; /sim/dlq/replay
    requeues them after recovery. Needs RabbitMQ — returns unavailable if the broker is down."""
    broker = request.app.state.broker
    if broker is None:
        return {"available": False, "detail": "RabbitMQ unavailable — run `make up` first."}
    stats = await broker.dlq_stats()
    return {"available": True, **stats, "messages": await broker.peek_dlq()}


def _view(c: Case) -> dict:
    return {
        "correlationId": c.correlation_id,
        "status": c.status,
        "version": c.version,
        "context": c.context,
        "decisionTrace": c.decision_trace,
        "sentCard": (c.sent_card or {}).get("card") if c.sent_card else None,
        "updatedAt": c.updated_at.isoformat(),
    }


@router.get("/cases")
async def list_cases() -> list[dict]:
    async with get_sessionmaker()() as session:
        rows = (await session.execute(select(Case).order_by(Case.updated_at.desc()))).scalars()
        return [_view(c) for c in rows]


@router.get("/cases/{correlation_id}")
async def get_case(correlation_id: str) -> dict:
    async with get_sessionmaker()() as session:
        c = (
            await session.execute(select(Case).where(Case.correlation_id == correlation_id))
        ).scalar_one_or_none()
        return _view(c) if c else {"error": "not found", "correlationId": correlation_id}
