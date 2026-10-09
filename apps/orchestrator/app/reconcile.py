"""Reconciliation — a simple sweep that surfaces cases stuck mid-flight (build step 12).

ponytail: read-only. It finds non-terminal cases that haven't moved in a while (lingering) and lists
them for an operator — it does NOT auto-heal. That's the deliberate ceiling; add re-drive/repair
when volume justifies it. The honest minimal version of the "reconciliation" reliability layer.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Case
from app.policy import TERMINAL_STATES


async def find_lingering(session: AsyncSession, older_than_minutes: int = 30) -> list[dict]:
    """Non-terminal cases not updated for `older_than_minutes` — stuck/waiting too long."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=older_than_minutes)
    rows = (
        await session.execute(select(Case).where(Case.status.not_in(TERMINAL_STATES)))
    ).scalars()
    out: list[dict] = []
    for c in rows:
        updated = c.updated_at
        if updated.tzinfo is None:  # SQLite returns naive datetimes
            updated = updated.replace(tzinfo=UTC)
        if updated < cutoff:
            out.append(
                {
                    "correlationId": c.correlation_id,
                    "status": c.status,
                    "ageMinutes": round((now - updated).total_seconds() / 60, 1),
                }
            )
    out.sort(key=lambda r: r["ageMinutes"], reverse=True)  # most-stuck first
    return out
