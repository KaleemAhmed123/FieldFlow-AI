"""Real availability slots (availability-slots.md): the graph offers genuine Field Service times,
pages the extras behind "See other times", books the exact instant, and falls back to canned slots
when the scheduler returns nothing. Pure-helper check for the label formatter too. Fakes only."""

from __future__ import annotations

from app.db.models import Case
from app.services import case_service
from app.tools.salesforce import format_slot_label
from fieldflow_contract import make_event
from sqlalchemy import select


async def _case(sessionmaker, cid: str) -> Case:
    async with sessionmaker() as s:
        return (await s.execute(select(Case).where(Case.correlation_id == cid))).scalar_one()


def _slots(n: int) -> list[dict]:
    # n real slots on consecutive November days, UTC (the shape Apex /slots returns).
    return [
        {"start": f"2026-11-0{i}T09:00:00.000+0000",
         "end": f"2026-11-0{i}T11:00:00.000+0000", "grade": 90 - i}
        for i in range(1, n + 1)
    ]


def test_format_slot_label_renders_in_business_tz() -> None:
    # 09:00-11:00 UTC → 14:30-16:30 in Asia/Kolkata (+5:30); day is named (real slots span days).
    label = format_slot_label(
        "2026-11-03T09:00:00.000+0000", "2026-11-03T11:00:00.000+0000", "Asia/Kolkata"
    )
    assert "14:30-16:30" in label and "Nov" in label


async def test_real_slots_paginate_and_book(sessionmaker, salesforce, vonage, graph) -> None:
    salesforce._slots = _slots(4)  # 4 real openings → 2 shown + "See other times"
    event = make_event(work_order_id="WO-SLOTS", reason="technician_delay")
    async with sessionmaker() as s:
        await case_service.handle_event(s, event, graph=graph)

    case = await _case(sessionmaker, "WO-SLOTS")
    assert case.status == "OPTIONS_SENT" and case.version == 1
    assert case.decision_trace["slotsAuthority"] == "scheduler"
    opts = case.sent_card["card"]["options"]
    assert [o["slotId"] for o in opts] == ["slot-1", "slot-2", "__more__"]

    # "See other times" → page forward, re-offer the next 2 (no pager on the last page).
    async with sessionmaker() as s:
        await case_service.resume_case(
            s, "WO-SLOTS", {"slotId": "__more__", "version": 1}, graph=graph
        )
    case = await _case(sessionmaker, "WO-SLOTS")
    assert case.status == "OPTIONS_SENT" and case.version == 2
    assert [o["slotId"] for o in case.sent_card["card"]["options"]] == ["slot-3", "slot-4"]

    # Book a real slot from the second page → the appointment reschedules and the case closes.
    async with sessionmaker() as s:
        await case_service.resume_case(
            s, "WO-SLOTS", {"slotId": "slot-3", "version": 2}, graph=graph
        )
    assert (await _case(sessionmaker, "WO-SLOTS")).status == "CLOSED"


async def test_no_real_slots_falls_back_to_canned(sessionmaker, salesforce, vonage, graph) -> None:
    # salesforce._slots stays empty → scheduler returns nothing → canned slots, labelled "fallback".
    event = make_event(work_order_id="WO-FALLBACK", reason="technician_delay")
    async with sessionmaker() as s:
        await case_service.handle_event(s, event, graph=graph)

    case = await _case(sessionmaker, "WO-FALLBACK")
    assert case.status == "OPTIONS_SENT"
    assert case.decision_trace["slotsAuthority"] == "fallback"
    opts = case.sent_card["card"]["options"]
    assert len(opts) == 2 and all(o["slotId"] != "__more__" for o in opts)  # canned, no pager
