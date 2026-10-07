"""Events that travel Salesforce → RabbitMQ → LangGraph.

Every event shares one envelope. `eventId` is the idempotency key; `correlationId` threads the
whole recovery case (the work-order id in the demo).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(UTC)


class EventEnvelope(BaseModel):
    eventId: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex}")
    correlationId: str
    event: str
    occurredAt: datetime = Field(default_factory=_now)


# The at-risk reasons a real Salesforce field-change would carry. Only three drive distinct
# behaviour (the archetypes, mapped in the graph); the rest are realistic variety for the demo.
Reason = Literal[
    "technician_delay", "traffic_weather", "technician_no_show", "customer_access_issue",
    "part_missing", "wrong_part_shipped", "additional_fault_found",
    "asset_complex", "safety_risk", "warranty_dispute",
]


class AppointmentAtRisk(EventEnvelope):
    event: Literal["appointment.at_risk"] = "appointment.at_risk"
    appointmentId: str
    workOrderId: str
    reason: Reason = "technician_delay"
    detail: dict[str, Any] = Field(default_factory=dict)


def make_event(
    *,
    work_order_id: str = "WO-10281",
    appointment_id: str = "SA-19281",
    reason: Reason = "technician_delay",
    delay_minutes: int = 50,
) -> AppointmentAtRisk:
    """Build a demo at-risk event. correlationId = work order id for legibility."""
    return AppointmentAtRisk(
        correlationId=work_order_id,
        workOrderId=work_order_id,
        appointmentId=appointment_id,
        reason=reason,
        detail={"delayMinutes": delay_minutes},
    )
