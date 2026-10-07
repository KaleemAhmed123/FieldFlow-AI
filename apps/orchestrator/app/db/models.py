"""Our small store — only what Salesforce shouldn't own: the case, idempotency, audit.

Uses generic JSON (not JSONB) so the same models run on Postgres (dev) and SQLite (tests).
Tables are created with metadata.create_all for the spine; alembic migrations come once the
schema settles.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Case(Base):
    """One recovery case, keyed by correlationId (the one tenancy key)."""

    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    correlation_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    status: Mapped[str] = mapped_column(String, default="NEW")
    version: Mapped[int] = mapped_column(Integer, default=0)  # bumped each time options are sent
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    decision_trace: Mapped[dict] = mapped_column(JSON, default=dict)
    sent_card: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class IdempotencyKey(Base):
    """Seen event/message UUIDs. A duplicate is ignored — processed once, effect-once."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditLog(Base):
    """Append-only trail. Every mutation/decision lands here."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    correlation_id: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AiDecision(Base):
    """The decision trace — the 'show your work' artifact. One row per decision/offer.

    Holds the full {decision, reason[], knowledgeSources[], toolsUsed[], confidence,
    policyResult, removed[]}. Append-only; Logfire mirrors this into live traces later.
    """

    __tablename__ = "ai_decisions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    correlation_id: Mapped[str] = mapped_column(String, index=True)
    decision: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
