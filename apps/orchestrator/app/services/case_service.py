"""Drive the recovery graph and persist what it produces.

Two entry points, both the same shape (idempotency/decide-via-graph/persist/audit):
  handle_event  — a new at-risk event starts a case; the graph runs until it pauses (customer or
                  human) or finishes.
  resume_case   — a human approval or a customer reply resumes the paused case on its checkpoint.

The graph owns the deciding and the mockable side effects (send card, reserve, reschedule). This
layer owns durable state: the Case row, the append-only audit trail and the decision trace. Nodes
never touch the DB, so they stay pure and unit-testable.
"""

from __future__ import annotations

from typing import Any

from fieldflow_contract import AppointmentAtRisk
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import telemetry
from app.db.models import AiDecision, AuditLog, Case, IdempotencyKey
from app.logging import correlation_id, get_logger

log = get_logger("case")

# Case status while paused on an interrupt, keyed by the interrupt payload's "type".
_PAUSED_STATUS = {"approval_request": "AWAITING_APPROVAL", "await_reply": "OPTIONS_SENT"}
# Statuses that represent a fresh decision worth an audit row + a decision-trace row.
_DECISION_STATUS = {"AWAITING_APPROVAL", "OPTIONS_SENT"}
_AUDIT_KIND = {"AWAITING_APPROVAL": "approval_requested", "OPTIONS_SENT": "options_sent"}


def _case_status(result: dict) -> str:
    """Why the graph stopped: the pending interrupt's type, or the terminal status."""
    interrupts = result.get("__interrupt__")
    if interrupts:
        return _PAUSED_STATUS.get(interrupts[0].value.get("type"), "PAUSED")
    return result.get("status", "CLOSED")


async def _persist(session: AsyncSession, cid: str, result: dict) -> str:
    """Upsert the Case from the graph's current state; add audit + decision-trace rows."""
    status = _case_status(result)

    case = (
        await session.execute(select(Case).where(Case.correlation_id == cid))
    ).scalar_one_or_none()
    if case is None:
        case = Case(correlation_id=cid)
        session.add(case)

    case.status = status
    if "context" in result:
        case.context = result["context"]
    if "decision" in result:
        case.decision_trace = result["decision"]
    if "sent" in result:
        case.sent_card = result["sent"]
    if "version" in result:
        case.version = result["version"]

    if status in _DECISION_STATUS and "decision" in result:
        session.add(AuditLog(correlation_id=cid, kind=_AUDIT_KIND[status],
                             payload=result["decision"]))
        session.add(AiDecision(correlation_id=cid, decision=result["decision"]))
        if status == "OPTIONS_SENT":
            telemetry.cards_sent.inc()
    else:
        session.add(AuditLog(correlation_id=cid, kind=status.lower(),
                             payload=result.get("executed", {})))
    return status


async def handle_event(session: AsyncSession, event: AppointmentAtRisk, *, graph) -> dict:
    correlation_id.set(event.correlationId)

    # Idempotency — effect-once even if the event arrives twice (NFR-2).
    if await session.get(IdempotencyKey, event.eventId):
        telemetry.events_duplicate.inc()
        log.info("event.duplicate", eventId=event.eventId)
        return {"status": "duplicate", "correlationId": event.correlationId}
    session.add(IdempotencyKey(key=event.eventId))

    config = {"configurable": {"thread_id": event.correlationId}}
    result = await graph.ainvoke({"event": event.model_dump(mode="json")}, config)

    status = await _persist(session, event.correlationId, result)
    await session.commit()
    telemetry.events_processed.inc()
    log.info("event.processed", status=status)
    return {"status": "ok", "case": status, "correlationId": event.correlationId}


async def resume_case(
    session: AsyncSession, correlation_id_: str, payload: dict[str, Any], *, graph
) -> dict:
    """Resume a paused case with a human approval or a customer reply."""
    correlation_id.set(correlation_id_)
    config = {"configurable": {"thread_id": correlation_id_}}
    result = await graph.ainvoke(Command(resume=payload), config)

    status = await _persist(session, correlation_id_, result)
    await session.commit()
    log.info("case.resumed", status=status)
    return {"status": "ok", "case": status, "correlationId": correlation_id_}
