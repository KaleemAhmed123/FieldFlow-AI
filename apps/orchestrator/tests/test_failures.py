"""Step 7 — graceful degradation, offline:
  7a RCS→SMS fallback: a failed delivery on an awaiting case resends the options as SMS (and only
     then — a 'delivered' status, or a case not awaiting, sends nothing).
  7b Salesforce-down: a down backend makes handle_event raise, which is what dead-letters the
     message to events.dlq at runtime (the broker nack path). The toggle flips reads on and off.
  7c RAG-down: a knowledge-store failure must degrade to empty knowledgeSources and still produce
     OPTIONS_SENT — the decision pipeline must not break when the vector store is unavailable.
The actual DLQ land+replay needs RabbitMQ and is a manual demo (playbook §3f)."""

from __future__ import annotations

import pytest
from app.db.models import AuditLog, Case
from app.graph.build import build_graph
from app.graph.checkpointer import make_checkpointer
from app.rag.store import FakeKnowledgeStore
from app.services import case_service
from app.tools.salesforce import FakeSalesforce
from app.tools.vonage import FakeVonage
from fieldflow_contract import make_event
from sqlalchemy import func, select


async def _case(sessionmaker, cid: str) -> Case:
    async with sessionmaker() as s:
        return (await s.execute(select(Case).where(Case.correlation_id == cid))).scalar_one()


async def _options_sent_case(sessionmaker, graph, cid="WO-7A") -> str:
    """Drive a case to OPTIONS_SENT and stamp a known messageUuid on its sent card (the real send
    returns one; FakeVonage doesn't, so we set it so the status callback can find the case)."""
    async with sessionmaker() as s:
        await case_service.handle_event(s, make_event(work_order_id=cid), graph=graph)
    async with sessionmaker() as s:
        case = (await s.execute(select(Case).where(Case.correlation_id == cid))).scalar_one()
        card = dict(case.sent_card)
        card["messageUuid"] = "msg-7a"
        case.sent_card = card
        await s.commit()
    return cid


# --- 7a: a failed delivery on an awaiting case → SMS with the same options -----------------------
async def test_failed_delivery_triggers_sms_fallback(sessionmaker, graph):
    cid = await _options_sent_case(sessionmaker, graph)
    vonage = FakeVonage()
    async with sessionmaker() as s:
        await case_service.record_delivery_status(
            s, vonage, message_uuid="msg-7a", status="failed", to="+919000000000")
    assert len(vonage.sms) == 1                      # the fallback SMS went out
    assert "Reply with" in vonage.sms[0]["sms"]
    assert cid in vonage.sms[0]["to"]
    async with sessionmaker() as s:
        n = (await s.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.kind == "sms_fallback")
        )).scalar_one()
    assert n == 1


# --- 7a: a successful delivery sends NO SMS ------------------------------------------------------
async def test_delivered_status_sends_no_sms(sessionmaker, graph):
    await _options_sent_case(sessionmaker, graph, cid="WO-7A-OK")
    vonage = FakeVonage()
    async with sessionmaker() as s:
        await case_service.record_delivery_status(
            s, vonage, message_uuid="msg-7a", status="delivered", to="+919000000000")
    assert vonage.sms == []


# --- 7a: a failed status with no matching case (unknown uuid) sends no SMS, still records ---------
async def test_failed_status_unknown_message_records_but_no_sms(sessionmaker):
    vonage = FakeVonage()
    async with sessionmaker() as s:
        await case_service.record_delivery_status(
            s, vonage, message_uuid="nope", status="failed", to="+1")
    assert vonage.sms == []


# --- 7b: Salesforce down → handle_event raises (this is what dead-letters the message) -----------
async def test_salesforce_down_persists_failed_and_raises(sessionmaker, salesforce, graph):
    salesforce.down = True
    with pytest.raises(RuntimeError, match="salesforce unavailable"):
        async with sessionmaker() as s:
            await case_service.handle_event(s, make_event(work_order_id="WO-7B"), graph=graph)
    # The failure is now VISIBLE as a FAILED case AND still re-raised → the message still
    # dead-letters for replay (the raise parks it). A replay upserts this case to its real status.
    async with sessionmaker() as s:
        case = (await s.execute(
            select(Case).where(Case.correlation_id == "WO-7B")
        )).scalar_one()
    assert case.status == "FAILED"
    assert "salesforce unavailable" in (case.decision_trace or {}).get("error", "")


# --- 7b: the toggle flips reads off and back on --------------------------------------------------
def test_fault_toggle_flips_reads():
    sf = FakeSalesforce()
    assert sf.get_appointment("SA-19281") is not None  # healthy
    sf.down = True
    with pytest.raises(RuntimeError):
        sf.get_appointment("SA-19281")
    sf.down = False
    assert sf.get_appointment("SA-19281") is not None  # recovered


# --- 7c: RAG / vector-store down → decision continues with empty knowledgeSources ----------------

class _BrokenKnowledgeStore(FakeKnowledgeStore):
    """A knowledge store that always raises — simulates the vector DB being unavailable."""

    def retrieve(self, query: str, k: int) -> list:
        raise RuntimeError("vector store down")


async def test_rag_failure_degrades_gracefully(sessionmaker, toolbox, vonage):
    """If retrieve_knowledge raises, the graph must still reach OPTIONS_SENT.

    The RAG node is wrapped in a bare `except Exception` (graph/build.py:207) that degrades to
    knowledgeSources=[].  This test exercises that path end-to-end so a regression — e.g. someone
    accidentally removing the try/except — is caught immediately.
    """
    broken_knowledge = _BrokenKnowledgeStore()
    broken_graph = build_graph(toolbox, vonage, broken_knowledge, checkpointer=make_checkpointer())

    event = make_event(work_order_id="WO-RAG-DOWN", reason="technician_delay")
    async with sessionmaker() as s:
        await case_service.handle_event(s, event, graph=broken_graph)

    async with sessionmaker() as s:
        case = (await s.execute(
            select(Case).where(Case.correlation_id == "WO-RAG-DOWN")
        )).scalar_one()

    # Pipeline must complete — OPTIONS_SENT — even with no knowledge sources.
    assert case.status == "OPTIONS_SENT"
    # The degraded node returns [] so the trace key is present but empty (not missing).
    assert case.decision_trace.get("knowledgeSources") == []
