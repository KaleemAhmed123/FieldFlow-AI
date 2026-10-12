"""The decision core end to end: human approval gating (NFR-4), the inventory race (NFR-5),
and stale replies (NFR-6). In-memory SQLite + fakes, no infra."""

from __future__ import annotations

from app.db.models import Case
from app.services import case_service
from fieldflow_contract import make_event
from sqlalchemy import select


async def _case(sessionmaker, cid: str) -> Case:
    async with sessionmaker() as s:
        return (await s.execute(select(Case).where(Case.correlation_id == cid))).scalar_one()


# NFR-4 — low confidence routes to human approval and does NOT execute until approved.
async def test_low_confidence_gates_on_human_approval(sessionmaker, vonage, graph):
    event = make_event(work_order_id="WO-NFR4", reason="asset_complex")  # confidence 0.5 < 0.7

    async with sessionmaker() as s:
        await case_service.handle_event(s, event, graph=graph)

    case = await _case(sessionmaker, "WO-NFR4")
    assert case.status == "AWAITING_APPROVAL"
    assert vonage.sent == []                       # nothing offered to the customer yet

    async with sessionmaker() as s:
        await case_service.resume_case(s, "WO-NFR4", {"approved": True}, graph=graph)

    case = await _case(sessionmaker, "WO-NFR4")
    assert case.status == "OPTIONS_SENT"           # only now is the card sent
    assert len(vonage.sent) == 1


async def test_rejected_approval_closes_without_offering(sessionmaker, vonage, graph):
    event = make_event(work_order_id="WO-NFR4R", reason="asset_complex")
    async with sessionmaker() as s:
        await case_service.handle_event(s, event, graph=graph)
    async with sessionmaker() as s:
        await case_service.resume_case(s, "WO-NFR4R", {"approved": False}, graph=graph)

    case = await _case(sessionmaker, "WO-NFR4R")
    assert case.status == "REJECTED"
    assert vonage.sent == []


# NFR-5 — part is taken between offer and reply: atomic reserve fails, graph recomputes + re-offers.
async def test_inventory_race_recomputes_and_reoffers(sessionmaker, vonage, inventory, graph):
    event = make_event(work_order_id="WO-NFR5", reason="part_missing")

    async with sessionmaker() as s:
        await case_service.handle_event(s, event, graph=graph)
    case = await _case(sessionmaker, "WO-NFR5")
    assert case.status == "OPTIONS_SENT" and case.version == 1
    assert len(case.sent_card["card"]["options"]) == 2        # part slot + loaner slot

    inventory.set_stock("CAP-492", 0)                          # another case grabbed the part

    async with sessionmaker() as s:
        await case_service.resume_case(
            s, "WO-NFR5", {"slotId": "t-part-1", "version": 1}, graph=graph
        )

    case = await _case(sessionmaker, "WO-NFR5")
    assert case.status == "OPTIONS_SENT"                       # re-offered, not executed
    assert case.version == 2
    assert len(vonage.sent) == 2
    assert len(case.sent_card["card"]["options"]) == 1         # part slot removed by policy
    assert case.sent_card["card"]["options"][0]["slotId"] == "t-swap-1"


# NFR-6 — a reply tagged with a stale version is rejected and the current options are re-sent.
async def test_stale_reply_is_rejected_and_reoffered(sessionmaker, vonage, graph):
    event = make_event(work_order_id="WO-NFR6", reason="technician_delay")

    async with sessionmaker() as s:
        await case_service.handle_event(s, event, graph=graph)
    assert (await _case(sessionmaker, "WO-NFR6")).version == 1

    async with sessionmaker() as s:
        await case_service.resume_case(
            s, "WO-NFR6", {"slotId": "t-today-1", "version": 0}, graph=graph  # stale: shown v1
        )

    case = await _case(sessionmaker, "WO-NFR6")
    assert case.status == "OPTIONS_SENT"           # re-offered, not EXECUTED
    assert case.version == 2                        # options re-sent with a fresh version
    assert len(vonage.sent) == 2


# A cosmetic reason inherits its archetype's behaviour: safety_risk → complex → human approval.
async def test_cosmetic_reason_maps_to_complex_archetype(sessionmaker, vonage, graph):
    event = make_event(work_order_id="WO-SAFETY", reason="safety_risk")
    async with sessionmaker() as s:
        await case_service.handle_event(s, event, graph=graph)

    case = await _case(sessionmaker, "WO-SAFETY")
    assert case.status == "AWAITING_APPROVAL"   # routed to a human like asset_complex
    assert vonage.sent == []


# wrong_part_shipped → parts archetype → the part+loaner carousel (two options).
async def test_cosmetic_reason_maps_to_parts_archetype(sessionmaker, vonage, graph):
    event = make_event(work_order_id="WO-WRONGPART", reason="wrong_part_shipped")
    async with sessionmaker() as s:
        await case_service.handle_event(s, event, graph=graph)

    case = await _case(sessionmaker, "WO-WRONGPART")
    assert case.status == "OPTIONS_SENT"
    assert len(case.sent_card["card"]["options"]) == 2
    # slice 5: a parts offer invites a photo of the unit label (the inbound-image primitive).
    assert "photo" in {a["type"] for a in case.sent_card["card"]["actions"]}


async def test_happy_path_executes_to_closed(sessionmaker, vonage, graph):
    event = make_event(work_order_id="WO-OK", reason="technician_delay")

    async with sessionmaker() as s:
        await case_service.handle_event(s, event, graph=graph)
    async with sessionmaker() as s:
        await case_service.resume_case(
            s, "WO-OK", {"slotId": "t-today-1", "version": 1}, graph=graph
        )

    case = await _case(sessionmaker, "WO-OK")
    assert case.status == "CLOSED"
    # slice 3: the journey ends on a confirmation card with Add-to-Calendar + Call actions.
    confirmation = case.sent_card["card"]
    assert confirmation["kind"] == "confirmation" and confirmation["body"]
    action_types = {a["type"] for a in confirmation["actions"]}
    assert "calendar" in action_types and "dial" in action_types
    # slice 6: a service-report PDF rides on the confirmation + the trace.
    assert "pdf" in action_types
    assert case.decision_trace["serviceReport"]["url"].endswith(".pdf")


async def test_photo_records_simulated_ocr_on_the_trace(sessionmaker, vonage, graph):
    # slice 5: the customer sends a label photo → simulated OCR confirms the model on the trace.
    event = make_event(work_order_id="WO-PHOTO", reason="part_missing")
    async with sessionmaker() as s:
        await case_service.handle_event(s, event, graph=graph)
    async with sessionmaker() as s:
        res = await case_service.record_photo(s, "WO-PHOTO")

    assert res["ok"] and res["matchesAsset"]
    case = await _case(sessionmaker, "WO-PHOTO")
    assert case.decision_trace["photoVerified"]["model"]          # the asset's model, read by OCR
    assert "simulated" in case.decision_trace["photoVerified"]["source"].lower()
