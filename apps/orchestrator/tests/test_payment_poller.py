"""The auto-confirm sweep resumes a PAYMENT_PENDING case only once its link is actually paid."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app import payment_poller
from app.db.models import Case
from app.services import case_service
from sqlalchemy import select


class _Gateway:
    """Stand-in: capture() reports paid/not without touching Razorpay."""

    def __init__(self, paid: bool) -> None:
        self.paid = paid

    def capture(self, ref: str, amount: int, reported_status: str = "captured") -> dict:
        return ({"status": "captured", "paymentId": "pay_x"} if self.paid
                else {"status": "pending"})


async def _seed_pending(sessionmaker) -> None:
    async with sessionmaker() as s:
        s.add(Case(correlation_id="WO-1", status="PAYMENT_PENDING",
                   decision_trace={"commerce": {"paymentLink": {"paymentLinkId": "plink_1"},
                                                 "order": {"amountPaise": 370000}}}))
        await s.commit()


@pytest.fixture
def _capture_resume(monkeypatch):
    calls: list[tuple] = []

    async def fake_resume(session, cid, payload, *, graph, idempotency_key=None):
        calls.append((cid, payload, idempotency_key))
        return {"status": "ok"}

    monkeypatch.setattr(case_service, "resume_case", fake_resume)
    return calls


async def test_unpaid_link_is_not_resumed(sessionmaker, _capture_resume) -> None:
    await _seed_pending(sessionmaker)
    gw = _Gateway(paid=False)
    resumed = await payment_poller.sweep_once(sessionmaker, graph=None, gateway=gw)
    assert resumed == 0 and _capture_resume == []


async def test_paid_link_resumes_once_with_idempotency_key(sessionmaker, _capture_resume) -> None:
    await _seed_pending(sessionmaker)
    resumed = await payment_poller.sweep_once(sessionmaker, graph=None, gateway=_Gateway(paid=True))
    assert resumed == 1
    cid, payload, key = _capture_resume[0]
    assert cid == "WO-1"
    assert payload == {"paymentId": "pay_x", "status": "captured"}
    assert key == "autopay-plink_1"  # keyed by the link id → a repeat sweep can't double-charge


async def test_unpaid_link_expires_after_ttl(sessionmaker, _capture_resume) -> None:
    # PAYMENT_PENDING longer than the TTL and still unpaid → EXPIRED, no resume.
    old = datetime.now(UTC) - timedelta(minutes=5)
    async with sessionmaker() as s:
        s.add(Case(correlation_id="WO-OLD", status="PAYMENT_PENDING", updated_at=old,
                   decision_trace={"commerce": {"paymentLink": {"paymentLinkId": "plink_old"},
                                                 "order": {"amountPaise": 370000}}}))
        await s.commit()
    resumed = await payment_poller.sweep_once(
        sessionmaker, graph=None, gateway=_Gateway(paid=False), ttl_seconds=180
    )
    assert resumed == 0 and _capture_resume == []
    async with sessionmaker() as s:
        case = (await s.execute(
            select(Case).where(Case.correlation_id == "WO-OLD"))).scalar_one()
        assert case.status == "PAYMENT_EXPIRED"


async def test_fresh_unpaid_link_is_not_expired(sessionmaker, _capture_resume) -> None:
    await _seed_pending(sessionmaker)  # updated_at = now
    await payment_poller.sweep_once(
        sessionmaker, graph=None, gateway=_Gateway(paid=False), ttl_seconds=180
    )
    async with sessionmaker() as s:
        case = (await s.execute(select(Case).where(Case.correlation_id == "WO-1"))).scalar_one()
        assert case.status == "PAYMENT_PENDING"  # still waiting, well within the TTL
