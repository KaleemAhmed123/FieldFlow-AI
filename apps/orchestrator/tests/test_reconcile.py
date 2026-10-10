"""Step 12 — the reconciliation sweep finds only lingering non-terminal cases."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.models import Case
from app.reconcile import find_lingering


async def test_finds_only_lingering_nonterminal(sessionmaker) -> None:
    old = datetime.now(UTC) - timedelta(minutes=120)
    async with sessionmaker() as s:
        s.add_all(
            [
                Case(correlation_id="WO-STUCK", status="OPTIONS_SENT", created_at=old, updated_at=old),  # noqa: E501
                Case(correlation_id="WO-DONE", status="CLOSED", created_at=old, updated_at=old),
                Case(correlation_id="WO-FRESH", status="OPTIONS_SENT"),  # updated now
            ]
        )
        await s.commit()
    async with sessionmaker() as s:
        lingering = await find_lingering(s, older_than_minutes=30)
    assert {r["correlationId"] for r in lingering} == {"WO-STUCK"}  # terminal + fresh excluded
