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

from fastapi import HTTPException
from fieldflow_contract import AppointmentAtRisk
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import telemetry
from app.db.models import AiDecision, AuditLog, Case, IdempotencyKey
from app.logging import correlation_id, get_logger

log = get_logger("case")

# Case status while paused on an interrupt, keyed by the interrupt payload's "type".
_PAUSED_STATUS = {
    "approval_request": "AWAITING_APPROVAL", "await_reply": "OPTIONS_SENT",
    # Commerce pauses (Step 6): the operator's high-value quote gate, and the payment wait.
    "quote_approval": "AWAITING_QUOTE_APPROVAL", "await_payment": "PAYMENT_PENDING",
}
# Statuses that represent a fresh decision worth an audit row + a decision-trace row.
_DECISION_STATUS = {
    "AWAITING_APPROVAL", "OPTIONS_SENT", "AWAITING_QUOTE_APPROVAL", "PAYMENT_PENDING",
}
_AUDIT_KIND = {
    "AWAITING_APPROVAL": "approval_requested", "OPTIONS_SENT": "options_sent",
    "AWAITING_QUOTE_APPROVAL": "quote_approval_requested", "PAYMENT_PENDING": "payment_requested",
}


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
        # On close, prefer the payment receipt in the audit payload (money is the headline effect).
        session.add(AuditLog(correlation_id=cid, kind=status.lower(),
                             payload=result.get("captured") or result.get("executed", {})))
    return status


# A delivery status that means "the RCS card did not reach the customer" → trigger the SMS fallback.
_FAILED_DELIVERY = {"failed", "rejected", "undelivered"}


def _options_sms(card: dict) -> str:
    """Build the plain-SMS version of the reschedule options (Step 7a, OQ2): list each slot with its
    id so the customer can reply with it through the normal reply path. SMS has no carousel."""
    lines = [f"- {o['slotId']}: {o['label']}" for o in card.get("options", [])]
    return ("Your appointment needs rescheduling. Reply with one slot id:\n"
            + "\n".join(lines)) if lines else "Your appointment needs rescheduling."


async def record_delivery_status(
    session: AsyncSession, vonage, *, message_uuid: str | None, status: str | None, to: str | None
) -> None:
    """Record a Vonage delivery-status callback (delivered/read/failed) on the trail, and run the
    RCS→SMS fallback (Step 7a): if the card did NOT deliver and the case is still waiting for the
    customer's tap, resend the same options as a plain SMS so the customer isn't stuck.

    # ponytail: small scan over cases to find the sender; a sent_messages index if volume grows.
    """
    case = None
    if message_uuid:
        cases = (await session.execute(select(Case))).scalars().all()
        case = next((c for c in cases if (c.sent_card or {}).get("messageUuid") == message_uuid),
                    None)
    cid = case.correlation_id if case else (message_uuid or "unknown")
    session.add(AuditLog(correlation_id=cid, kind="delivery_status",
                         payload={"messageUuid": message_uuid, "status": status, "to": to}))

    # Fallback: a failed delivery on a case still awaiting the reply → the same options over SMS.
    if (status in _FAILED_DELIVERY and case is not None and case.status == "OPTIONS_SENT"
            and case.sent_card):
        text = _options_sms(case.sent_card.get("card", {}))
        vonage.send_sms(cid, text)
        session.add(AuditLog(correlation_id=cid, kind="sms_fallback",
                             payload={"reason": status, "text": text}))
        telemetry.sms_fallbacks.inc()
        log.info("case.sms_fallback", correlationId=cid, reason=status)

    await session.commit()
    log.info("case.delivery_status", messageUuid=message_uuid, status=status)


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
    session: AsyncSession,
    correlation_id_: str,
    payload: dict[str, Any],
    *,
    graph,
    idempotency_key: str | None = None,
) -> dict:
    """Resume a paused case with a human approval, a customer reply, or a payment confirmation.

    `idempotency_key` (the payment event's id) is the envelope-level no-double-charge guard: firing
    the same payment twice is dropped before the graph re-runs, so it can't re-send a card or clash
    on an already-closed case. The gateway's idempotent capture is the second, independent guard.
    """
    correlation_id.set(correlation_id_)
    config = {"configurable": {"thread_id": correlation_id_}}

    # Guard every resume path (approve / reply / payment): if no saved state exists for this case,
    # re-running the graph would re-enter load_case with an empty state and crash on state["event"]
    # (the KeyError 500). This happens when the checkpoint was lost (a restart before the durable
    # checkpointer) or pruned/expired. Fail cleanly instead — the case cannot be resumed.
    snapshot = await graph.aget_state(config)
    if not snapshot.values:
        log.info("resume.no_checkpoint", correlationId=correlation_id_)
        raise HTTPException(
            status_code=409,
            detail="Cannot resume: this case's paused state was lost or expired. Start a fresh "
                   "case.",
        )

    if idempotency_key is not None:
        if await session.get(IdempotencyKey, idempotency_key):
            telemetry.events_duplicate.inc()
            log.info("resume.duplicate", key=idempotency_key)  # same payment fired twice → drop
            case = (
                await session.execute(select(Case).where(Case.correlation_id == correlation_id_))
            ).scalar_one_or_none()
            return {"status": "duplicate", "case": case.status if case else None,
                    "correlationId": correlation_id_}
        session.add(IdempotencyKey(key=idempotency_key))

    result = await graph.ainvoke(Command(resume=payload), config)

    status = await _persist(session, correlation_id_, result)
    await session.commit()
    log.info("case.resumed", status=status)
    return {"status": "ok", "case": status, "correlationId": correlation_id_}
