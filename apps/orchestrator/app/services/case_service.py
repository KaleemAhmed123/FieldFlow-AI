"""Handle one at-risk event: idempotency -> graph -> send card -> persist case + audit.

This is the spine's heart and the thing the self-check tests exercise. It is intentionally the
same shape every mutation will follow: check idempotency, decide, act, persist, audit.
"""

from __future__ import annotations

from fieldflow_contract import AppointmentAtRisk, Card
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import telemetry
from app.db.models import AuditLog, Case, IdempotencyKey
from app.graph.build import build_graph
from app.logging import correlation_id, get_logger
from app.tools.salesforce import SalesforceTools
from app.tools.vonage import VonageClient

log = get_logger("case")


async def handle_event(
    session: AsyncSession,
    event: AppointmentAtRisk,
    *,
    vonage: VonageClient,
    salesforce: SalesforceTools,
) -> dict:
    correlation_id.set(event.correlationId)

    # 1. Idempotency — effect-once even if the event arrives twice (NFR-2).
    if await session.get(IdempotencyKey, event.eventId):
        telemetry.events_duplicate.inc()
        log.info("event.duplicate", eventId=event.eventId)
        return {"status": "duplicate", "correlationId": event.correlationId}
    session.add(IdempotencyKey(key=event.eventId))

    # 2. Decide — run the graph (AI/orchestration proposes; policy validates inside).
    graph = build_graph(salesforce)
    result = await graph.ainvoke({"event": event.model_dump(mode="json")})
    card = Card(**result["card"])
    decision = result["decision"]
    context = result["context"]

    # 3. Act — send the card (FakeVonage records it in the spine).
    sent = vonage.send_card(event.correlationId, card)
    telemetry.cards_sent.inc()

    # 4. Persist the case (upsert on correlationId) + an audit row.
    case = (
        await session.execute(select(Case).where(Case.correlation_id == event.correlationId))
    ).scalar_one_or_none()
    if case is None:
        case = Case(correlation_id=event.correlationId)
        session.add(case)
    case.status = "OPTIONS_SENT"
    case.context = context
    case.decision_trace = decision
    case.sent_card = sent
    session.add(
        AuditLog(correlation_id=event.correlationId, kind="options_sent", payload=decision)
    )

    await session.commit()
    telemetry.events_processed.inc()
    log.info("event.processed", status="OPTIONS_SENT")
    return {"status": "ok", "correlationId": event.correlationId}
