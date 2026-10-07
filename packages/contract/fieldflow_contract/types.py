"""Shapes the orchestrator produces/returns. The React panel generates TS types from these."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SlotOption(BaseModel):
    slotId: str
    label: str          # e.g. "TODAY 11:00-13:00"
    technician: str
    note: str = ""      # e.g. "Same technician"


class Card(BaseModel):
    """A minimal RCS-card-ish payload. FakeVonage 'sends' this; real Vonage renders it later."""

    kind: str                       # "carousel" | "text" | ...
    title: str
    options: list[SlotOption] = []


class CaseView(BaseModel):
    """What the control panel shows per recovery case."""

    correlationId: str
    status: str
    context: dict[str, Any] = {}
    decisionTrace: dict[str, Any] = {}
    sentCard: Card | None = None
    updatedAt: datetime
