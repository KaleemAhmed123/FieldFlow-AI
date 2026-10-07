"""FieldFlow AI shared contract.

The single source of truth both sides build against: event payloads and the shapes the
orchestrator exposes. Kept tiny on purpose — grows as nodes land.
"""

from .events import AppointmentAtRisk, EventEnvelope, Reason, make_event
from .types import Card, CaseView, SlotOption

__all__ = [
    "EventEnvelope",
    "AppointmentAtRisk",
    "Reason",
    "make_event",
    "SlotOption",
    "Card",
    "CaseView",
]
