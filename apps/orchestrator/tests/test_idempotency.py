"""The spine's load-bearing check: the same event twice = one case, one card (NFR-2)."""

from __future__ import annotations

from app.db.models import Case
from app.services import case_service
from fieldflow_contract import make_event
from sqlalchemy import func, select


async def test_duplicate_event_is_processed_once(sessionmaker, vonage, graph):
    event = make_event()  # fixed eventId within this object → we reuse the same one twice

    async with sessionmaker() as s:
        first = await case_service.handle_event(s, event, graph=graph)
    async with sessionmaker() as s:
        second = await case_service.handle_event(s, event, graph=graph)

    assert first["status"] == "ok"
    assert second["status"] == "duplicate"

    # exactly one case, and FakeVonage sent exactly one card
    async with sessionmaker() as s:
        count = (await s.execute(select(func.count()).select_from(Case))).scalar_one()
    assert count == 1
    assert len(vonage.sent) == 1
