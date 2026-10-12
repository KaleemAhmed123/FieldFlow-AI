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


class CardAction(BaseModel):
    """A suggested action chip on a card (slice 2). `type` maps to a real RCS suggested action:
    share_location (customer sends GPS), dial (call a number), calendar (add the appointment),
    view (open a URL). `value` carries the phone/url/label the action needs; blank where unused."""

    type: str           # "share_location" | "dial" | "calendar" | "view"
    label: str          # the button text, e.g. "Share my location"
    value: str = ""     # phone number (dial), url (view), or slot label (calendar)


class Card(BaseModel):
    """A minimal RCS-card-ish payload. FakeVonage 'sends' this; real Vonage renders it later."""

    kind: str                       # "carousel" | "text" | "payment" | "confirmation" | ...
    title: str
    body: str = ""                  # the AI-written, reason-aware message shown above the options
    options: list[SlotOption] = []
    actions: list[CardAction] = []  # suggested action chips (Share Location / Dial / …) — slice 2
    payUrl: str | None = None       # Open-URL target for an "Approve & Pay" button (Step 6)
    version: int = 0                # the offer version, echoed into RCS postback for the stale guard


class CaseView(BaseModel):
    """What the control panel shows per recovery case."""

    correlationId: str
    status: str
    context: dict[str, Any] = {}
    decisionTrace: dict[str, Any] = {}
    sentCard: Card | None = None
    updatedAt: datetime
