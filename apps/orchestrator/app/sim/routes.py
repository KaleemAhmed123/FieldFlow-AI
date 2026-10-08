"""Demo simulation endpoints — fire the events that a real Salesforce Pub/Sub would send.

POST /sim/appointment-at-risk  → publishes appointment.at_risk onto RabbitMQ.
Re-POST with the same eventId → the consumer dedupes it (idempotency demo).
POST /sim/approve        → resume a case paused for human approval (NFR-4, the operator tap).
POST /sim/customer-reply → resume a case paused for the customer's choice (drives NFR-5/NFR-6).
POST /sim/payment        → resume a case paused for payment: the customer paid (Step 6 commerce).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request
from fieldflow_contract import Reason, make_event
from pydantic import BaseModel, Field

from app import telemetry
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


class DeliveryStatusRequest(BaseModel):
    messageUuid: str
    status: str = "failed"  # "delivered" | "read" | "failed" | "undelivered" | "rejected"
    to: str | None = None


@router.post("/delivery-status")
async def delivery_status(body: DeliveryStatusRequest, request: Request) -> dict:
    """Offline twin of /webhooks/status (Step 7a): fire a delivery status without a real device.
    A 'failed'/'undelivered' status on a case still awaiting the reply → the RCS→SMS fallback."""
    async with get_sessionmaker()() as session:
        await case_service.record_delivery_status(
            session, request.app.state.vonage,
            message_uuid=body.messageUuid, status=body.status, to=body.to,
        )
    return {"recorded": True, "messageUuid": body.messageUuid, "status": body.status}


class FaultRequest(BaseModel):
    salesforceDown: bool = True


@router.post("/fault")
async def fault(body: FaultRequest, request: Request) -> dict:
    """Toggle 'Salesforce down' at runtime (Step 7b) — no restart. While down, every Salesforce
    read raises, so a fired event fails processing and dead-letters to events.dlq."""
    request.app.state.salesforce.down = body.salesforceDown
    return {"salesforceDown": body.salesforceDown}


@router.post("/dlq/replay")
async def dlq_replay(request: Request) -> dict:
    """Replay the parked messages back onto the main queue (Step 7b) — use after Salesforce is back
    up. Returns how many were requeued."""
    broker = request.app.state.broker
    if broker is None:
        raise HTTPException(status_code=503, detail="RabbitMQ unavailable — run `make up` first.")
    count = await broker.replay_dlq()
    for _ in range(count):
        telemetry.dlq_replays.inc()
    return {"replayed": count}


class PaymentRequest(BaseModel):
    correlationId: str
    paymentId: str = Field(default_factory=lambda: f"pay_{uuid.uuid4().hex[:12]}")
    status: str = "captured"  # "captured" | "failed"
    eventId: str | None = None  # pass the same id again to prove no double-charge


@router.post("/payment")
async def payment(body: PaymentRequest, request: Request) -> dict:
    """The customer completed payment on the Razorpay page — resume a case paused at await_payment.

    A normal /sim step, exactly like /sim/customer-reply (the POC fires every event via /sim; no
    inbound webhooks). The eventId is deduped in the service layer, so firing the same payment twice
    is dropped before the graph re-runs (the envelope no-double-charge guard; the gateway's
    idempotent capture is the second guard). Step 6.
    """
    async with get_sessionmaker()() as session:
        return await case_service.resume_case(
            session, body.correlationId,
            {"paymentId": body.paymentId, "status": body.status},
            graph=request.app.state.graph, idempotency_key=body.eventId,
        )
