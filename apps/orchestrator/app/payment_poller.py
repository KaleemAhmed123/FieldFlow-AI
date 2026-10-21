"""Automatic payment confirmation — the hands-off replacement for the /sim/payment nudge.

The POC takes no inbound Razorpay webhook, so we POLL: a background sweep finds cases paused at
PAYMENT_PENDING, asks the gateway whether each one's payment link is paid yet, and resumes the case
the moment it is — the exact resume /sim/payment does, so settle_payment then captures (idempotent)
and writes the payment to Salesforce.

Gated on a REAL Razorpay gateway (main.py only starts it for RazorpayGateway): the fake would report
every unpaid link as "captured", so offline/tests keep using /sim/payment. `/sim/payment` also stays
as a manual override on a real deploy.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Case
from app.logging import get_logger
from app.services import case_service

log = get_logger("payment_poller")


def _age_seconds(dt: datetime) -> float:
    """Seconds since `dt`, treating a naive datetime (SQLite) as UTC — Postgres is already aware."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (datetime.now(UTC) - dt).total_seconds()


async def sweep_once(
    sessionmaker: async_sessionmaker, graph: Any, gateway: Any, ttl_seconds: float = 180.0
) -> int:
    """One pass: resume every PAYMENT_PENDING case whose link is paid, and expire one gone unpaid
    past `ttl_seconds`. Returns the count resumed. Each case is independent — a bad one is logged
    and skipped, the rest still settle."""
    async with sessionmaker() as session:
        cases = (
            await session.execute(select(Case).where(Case.status == "PAYMENT_PENDING"))
        ).scalars().all()

    resumed = 0
    for case in cases:
        commerce = (case.decision_trace or {}).get("commerce", {})
        ref = (commerce.get("paymentLink") or {}).get("paymentLinkId")
        amount = (commerce.get("order") or {}).get("amountPaise")
        if not ref or not amount:
            continue
        try:
            # capture() polls payment_link.fetch on the real gateway — read-only until actually paid
            # (a Razorpay link auto-captures on pay). Run off the event loop (sync network call).
            receipt = await asyncio.to_thread(gateway.capture, ref, amount)
            if receipt.get("status") == "captured":
                async with sessionmaker() as session:
                    await case_service.resume_case(
                        session, case.correlation_id,
                        {"paymentId": receipt.get("paymentId"), "status": "captured"},
                        graph=graph, idempotency_key=f"autopay-{ref}",
                    )
                resumed += 1
                log.info("payment_poller.resumed",
                         correlationId=case.correlation_id, paymentRef=ref)
            elif _age_seconds(case.updated_at) > ttl_seconds:
                # Not paid in time → stop polling it (the customer abandoned the link).
                async with sessionmaker() as session:
                    await case_service.expire_payment(session, case.correlation_id)
        except Exception as exc:  # noqa: BLE001 — one case must not stop the sweep
            log.error("payment_poller.case_failed", correlationId=case.correlation_id,
                      error=str(exc))
    return resumed


async def run(
    sessionmaker: async_sessionmaker, graph: Any, gateway: Any, interval: float, ttl_seconds: float
) -> None:
    """Sweep forever on `interval` seconds. A failed pass is logged and the loop continues."""
    log.info("payment_poller.started", interval=interval, ttl=ttl_seconds)
    while True:
        try:
            await sweep_once(sessionmaker, graph, gateway, ttl_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — a bad pass must not kill the poller
            log.error("payment_poller.sweep_failed", error=str(exc))
        await asyncio.sleep(interval)
