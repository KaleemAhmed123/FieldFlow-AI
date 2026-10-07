"""Commerce module (lives inside the orchestrator — you own it).

Thin service for parts/quotes/orders/payments/refunds. Stub endpoints in the spine so the seam
exists; real logic + Razorpay Test-Mode land in build step 6.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/commerce", tags=["commerce"])


@router.get("/parts/{part_no}")
async def get_part(part_no: str) -> dict:
    return {"partNo": part_no, "price": 4500, "currency": "INR", "stub": True}
