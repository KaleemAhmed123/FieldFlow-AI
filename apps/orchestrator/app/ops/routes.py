"""Operator controls that must exist in production (carved out of /sim, which is demo-only).

These are REAL operator actions, not simulations, so unlike /sim/* they are always mounted (behind
the API key, AI-SEC-01) and survive when `SIM_ENABLED=false` drops the demo/offline-twin routes in
a real deployment:

POST /ops/approve      — the Level-3 human approval (NFR-4): resume a case paused at human_approval
                         or a high-value quote gate. The control panel's Approve / Reject button.
POST /ops/dlq/replay   — replay dead-lettered events back onto the main queue after a dependency has
                         recovered (the one lever to recover parked events).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import telemetry
from app.db.session import get_sessionmaker
from app.services import case_service

router = APIRouter(prefix="/ops", tags=["ops"])


class ApproveRequest(BaseModel):
    correlationId: str
    approved: bool = True


@router.post("/approve")
async def approve(body: ApproveRequest, request: Request) -> dict:
    """The operator's Level-3 decision — resume a case paused at human_approval (NFR-4) or at the
    high-value quote gate. Used by the control panel in every environment."""
    async with get_sessionmaker()() as session:
        return await case_service.resume_case(
            session, body.correlationId, {"approved": body.approved},
            graph=request.app.state.graph,
        )


@router.post("/dlq/replay")
async def dlq_replay(request: Request) -> dict:
    """Replay the parked messages back onto the main queue — use after a down dependency (e.g.
    Salesforce) is back up. Returns how many were requeued."""
    broker = request.app.state.broker
    if broker is None:
        raise HTTPException(status_code=503, detail="RabbitMQ unavailable — run `make up` first.")
    count = await broker.replay_dlq()
    for _ in range(count):
        telemetry.dlq_replays.add(1)
    return {"replayed": count}
