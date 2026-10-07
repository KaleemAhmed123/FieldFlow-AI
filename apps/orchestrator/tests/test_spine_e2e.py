"""One event travels the spine and produces a case with a carousel card + decision trace."""

from __future__ import annotations

from app.db.models import AuditLog, Case
from app.services import case_service
from fieldflow_contract import make_event
from sqlalchemy import select


async def test_event_produces_case_with_card_and_trace(sessionmaker, vonage, salesforce):
    event = make_event(work_order_id="WO-TEST-1")

    async with sessionmaker() as s:
        result = await case_service.handle_event(s, event, vonage=vonage, salesforce=salesforce)
    assert result["status"] == "ok"

    async with sessionmaker() as s:
        case = (
            await s.execute(select(Case).where(Case.correlation_id == "WO-TEST-1"))
        ).scalar_one()
        audits = (await s.execute(select(AuditLog))).scalars().all()

    assert case.status == "OPTIONS_SENT"
    assert case.sent_card["card"]["kind"] == "carousel"
    assert len(case.sent_card["card"]["options"]) == 2        # policy-validated slots
    assert case.decision_trace["policyResult"] == "APPROVED"
    assert case.decision_trace["decision"] == "OFFER_RESCHEDULE"
    assert len(audits) == 1 and audits[0].kind == "options_sent"
