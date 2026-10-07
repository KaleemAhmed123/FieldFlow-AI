"""Demo simulation endpoints — fire the events that a real Salesforce Pub/Sub would send.

POST /sim/appointment-at-risk  → publishes appointment.at_risk onto RabbitMQ.
Re-POST with the same eventId → the consumer dedupes it (idempotency demo).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fieldflow_contract import make_event
from pydantic import BaseModel

router = APIRouter(prefix="/sim", tags=["sim"])


class AtRiskRequest(BaseModel):
    workOrderId: str = "WO-10281"
    appointmentId: str = "SA-19281"
    delayMinutes: int = 50
    eventId: str | None = None  # pass the same id again to prove idempotency


@router.post("/appointment-at-risk")
async def fire_appointment_at_risk(body: AtRiskRequest, request: Request) -> dict:
    event = make_event(
        work_order_id=body.workOrderId,
        appointment_id=body.appointmentId,
        delay_minutes=body.delayMinutes,
    )
    if body.eventId:
        event.eventId = body.eventId
    broker = request.app.state.broker
    if broker is None:
        raise HTTPException(status_code=503, detail="RabbitMQ unavailable — run `make up` first.")
    await broker.publish(event.event, event.model_dump(mode="json"))
    return {"published": True, "eventId": event.eventId, "correlationId": event.correlationId}
