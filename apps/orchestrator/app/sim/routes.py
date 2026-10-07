"""Demo simulation endpoints — fire the events that a real Salesforce Pub/Sub would send.

POST /sim/appointment-at-risk  → publishes appointment.at_risk onto RabbitMQ.
Re-POST with the same eventId → the consumer dedupes it (idempotency demo).
POST /sim/approve        → resume a case paused for human approval (NFR-4, the operator tap).
POST /sim/customer-reply → resume a case paused for the customer's choice (drives NFR-5/NFR-6).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fieldflow_contract import Reason, make_event
from pydantic import BaseModel

from app.db.session import get_sessionmaker
from app.services import case_service

router = APIRouter(prefix="/sim", tags=["sim"])


class AtRiskRequest(BaseModel):
    workOrderId: str = "WO-10281"
    appointmentId: str = "SA-19281"
    reason: Reason = "technician_delay"  # picks the demo scenario; see /tools + the playbook
    delayMinutes: int = 50
    eventId: str | None = None  # pass the same id again to prove idempotency


@router.post("/appointment-at-risk")
async def fire_appointment_at_risk(body: AtRiskRequest, request: Request) -> dict:
    event = make_event(
        work_order_id=body.workOrderId,
        appointment_id=body.appointmentId,
        reason=body.reason,
        delay_minutes=body.delayMinutes,
    )
    if body.eventId:
        event.eventId = body.eventId
    broker = request.app.state.broker
    if broker is None:
        raise HTTPException(status_code=503, detail="RabbitMQ unavailable — run `make up` first.")
    await broker.publish(event.event, event.model_dump(mode="json"))
    return {"published": True, "eventId": event.eventId, "correlationId": event.correlationId}


class ApproveRequest(BaseModel):
    correlationId: str
    approved: bool = True


@router.post("/approve")
async def approve(body: ApproveRequest, request: Request) -> dict:
    """The operator's Level-3 decision — resume a case paused at human_approval (NFR-4)."""
    async with get_sessionmaker()() as session:
        return await case_service.resume_case(
            session, body.correlationId, {"approved": body.approved},
            graph=request.app.state.graph,
        )


class ReplyRequest(BaseModel):
    correlationId: str
    slotId: str
    version: int  # the version the customer was shown; a stale one is rejected (NFR-6)


@router.post("/customer-reply")
async def customer_reply(body: ReplyRequest, request: Request) -> dict:
    """The customer's tap — resume a case paused at await_reply."""
    async with get_sessionmaker()() as session:
        return await case_service.resume_case(
            session, body.correlationId, {"slotId": body.slotId, "version": body.version},
            graph=request.app.state.graph,
        )
