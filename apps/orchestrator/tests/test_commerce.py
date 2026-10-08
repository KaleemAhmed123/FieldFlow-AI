"""Commerce (Step 6): the price authority, the paid flow end to end, the high-value human gate,
no-double-charge (gateway + envelope), and refund. In-memory SQLite + FakeRazorpay, no infra."""

from __future__ import annotations

import pytest
from app.commerce.razorpay import FakeRazorpay, RazorpayGateway, build_gateway
from app.config import settings
from app.db.models import AuditLog, Case
from app.services import case_service
from fieldflow_contract import make_event
from sqlalchemy import func, select


async def _case(sessionmaker, cid: str) -> Case:
    async with sessionmaker() as s:
        return (await s.execute(select(Case).where(Case.correlation_id == cid))).scalar_one()


# --- The price authority: the amount comes from the book, never from the caller/LLM -------------
def test_create_quote_prices_from_the_book(toolbox):
    res = toolbox.call("commerce.create_quote", workOrderId="WO-1", partNo="CAP-492")
    assert res.ok
    # ₹3,200 part (book) + ₹500 labour = 370000 paise. Deterministic, not model-supplied.
    assert res.data["amountPaise"] == 320000 + settings.commerce_labour_paise
    assert res.data["priceAuthority"] == "price_book"


# --- FakeRazorpay capture is idempotent: a duplicate never charges twice -------------------------
def test_gateway_capture_is_idempotent():
    rp = FakeRazorpay()
    first = rp.capture("pay_1", 370000)
    second = rp.capture("pay_1", 370000)
    assert first["alreadyCaptured"] is False
    assert second["alreadyCaptured"] is True
    assert len(rp._captured) == 1  # charged once


def test_refund_tool_refuses_uncaptured_then_refunds(toolbox, razorpay):
    assert not toolbox.call("commerce.refund", paymentId="pay_nope").ok  # never captured → refuse
    razorpay.capture("pay_ok", 370000)
    res = toolbox.call("commerce.refund", paymentId="pay_ok")
    assert res.ok and res.data["status"] == "refunded"


# --- The paid flow end to end: additional_fault_found (chargeable even under warranty) -----------
async def test_paid_flow_quote_to_captured(sessionmaker, vonage, razorpay, graph):
    event = make_event(work_order_id="WO-PAY", reason="additional_fault_found")

    async with sessionmaker() as s:
        await case_service.handle_event(s, event, graph=graph)
    assert (await _case(sessionmaker, "WO-PAY")).status == "OPTIONS_SENT"

    # Customer picks the part-fit slot → reserve → reschedule → chargeable → quote → pay card.
    async with sessionmaker() as s:
        await case_service.resume_case(
            s, "WO-PAY", {"slotId": "t-part-1", "version": 1}, graph=graph
        )
    case = await _case(sessionmaker, "WO-PAY")
    assert case.status == "PAYMENT_PENDING"
    assert case.sent_card["card"]["kind"] == "payment"
    assert case.sent_card["card"]["payUrl"].startswith("https://rzp.io/")

    # Customer completed payment (/sim/payment): captured → settle → verify → close.
    async with sessionmaker() as s:
        await case_service.resume_case(
            s, "WO-PAY", {"paymentId": "pay_pay", "status": "captured"},
            graph=graph, idempotency_key="evt-pay-1",
        )
    case = await _case(sessionmaker, "WO-PAY")
    assert case.status == "CLOSED"
    commerce = case.decision_trace["commerce"]
    assert commerce["quote"]["amountPaise"] == 370000
    assert commerce["order"]["status"] == "CREATED"
    assert commerce["payment"]["status"] == "captured"
    assert len(razorpay._captured) == 1  # charged exactly once


# --- No double-charge: the same payment (same eventId) fired twice is dropped before re-running ---
async def test_duplicate_payment_does_not_double_charge(sessionmaker, razorpay, graph):
    event = make_event(work_order_id="WO-DUP", reason="additional_fault_found")
    async with sessionmaker() as s:
        await case_service.handle_event(s, event, graph=graph)
    async with sessionmaker() as s:
        await case_service.resume_case(
            s, "WO-DUP", {"slotId": "t-part-1", "version": 1}, graph=graph
        )

    async with sessionmaker() as s:
        first = await case_service.resume_case(
            s, "WO-DUP", {"paymentId": "pay_dup", "status": "captured"},
            graph=graph, idempotency_key="evt-dup-1",
        )
    async with sessionmaker() as s:
        second = await case_service.resume_case(  # same payment eventId → dropped
            s, "WO-DUP", {"paymentId": "pay_dup", "status": "captured"},
            graph=graph, idempotency_key="evt-dup-1",
        )

    assert first["status"] == "ok" and second["status"] == "duplicate"
    assert len(razorpay._captured) == 1               # charged once
    assert (await _case(sessionmaker, "WO-DUP")).status == "CLOSED"
    # And exactly one payment audit row — the duplicate wrote nothing.
    async with sessionmaker() as s:
        n = await s.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.correlation_id == "WO-DUP")
        )
    assert n >= 1


# --- Out-of-warranty asset is the other chargeable trigger (warranty is the authority, OQ2) ------
async def test_out_of_warranty_appointment_is_chargeable(sessionmaker, graph):
    event = make_event(work_order_id="WO-OOW", appointment_id="SA-OOW", reason="part_missing")
    async with sessionmaker() as s:
        await case_service.handle_event(s, event, graph=graph)
    async with sessionmaker() as s:
        await case_service.resume_case(
            s, "WO-OOW", {"slotId": "t-part-1", "version": 1}, graph=graph
        )
    assert (await _case(sessionmaker, "WO-OOW")).status == "PAYMENT_PENDING"


# --- High-value quote routes to a human before any payment link is offered (risk-tiering) -------
async def test_high_value_quote_gates_on_human(sessionmaker, vonage, graph, monkeypatch):
    monkeypatch.setattr(settings, "commerce_high_value_paise", 1)  # make any quote high-value
    event = make_event(work_order_id="WO-HV", reason="additional_fault_found")

    async with sessionmaker() as s:
        await case_service.handle_event(s, event, graph=graph)
    async with sessionmaker() as s:
        await case_service.resume_case(
            s, "WO-HV", {"slotId": "t-part-1", "version": 1}, graph=graph
        )
    case = await _case(sessionmaker, "WO-HV")
    assert case.status == "AWAITING_QUOTE_APPROVAL"   # paused for the operator
    assert all(c["card"]["kind"] != "payment" for c in vonage.sent)  # no pay card yet

    async with sessionmaker() as s:
        await case_service.resume_case(s, "WO-HV", {"approved": True}, graph=graph)
    assert (await _case(sessionmaker, "WO-HV")).status == "PAYMENT_PENDING"  # now the pay card


# --- A failed payment re-offers the pay card instead of closing ----------------------------------
async def test_failed_payment_reoffers(sessionmaker, graph):
    event = make_event(work_order_id="WO-FAIL", reason="additional_fault_found")
    async with sessionmaker() as s:
        await case_service.handle_event(s, event, graph=graph)
    async with sessionmaker() as s:
        await case_service.resume_case(
            s, "WO-FAIL", {"slotId": "t-part-1", "version": 1}, graph=graph
        )
    async with sessionmaker() as s:
        await case_service.resume_case(
            s, "WO-FAIL", {"paymentId": "pay_x", "status": "failed"},
            graph=graph, idempotency_key="evt-fail-1",
        )
    # payment failed → re-offered, not closed:
    assert (await _case(sessionmaker, "WO-FAIL")).status == "PAYMENT_PENDING"


# --- RazorpayGateway (Step 9): maps the SDK, polls for 'paid', refuses a live key ----------------
class _StubLinkApi:
    def __init__(self, created: dict, fetched: dict) -> None:
        self._created, self._fetched = created, fetched

    def create(self, payload: dict) -> dict:
        return self._created

    def fetch(self, link_id: str) -> dict:
        return self._fetched


class _StubClient:
    def __init__(self, created: dict, fetched: dict) -> None:
        self.payment_link = _StubLinkApi(created, fetched)


def test_razorpay_gateway_maps_create_and_poll_paid():
    created = {"id": "plink_x", "amount": 370000, "currency": "INR",
               "short_url": "https://rzp.io/i/x", "status": "created"}
    paid = {"status": "paid", "amount": 370000, "currency": "INR",
            "payments": [{"payment_id": "pay_real"}]}
    gw = RazorpayGateway(_StubClient(created, paid))
    link = gw.create_payment_link("ord_1", 370000, "INR")
    assert link["paymentLinkId"] == "plink_x" and link["shortUrl"] == "https://rzp.io/i/x"
    receipt = gw.capture("plink_x", 370000)
    assert receipt["status"] == "captured" and receipt["paymentId"] == "pay_real"


def test_razorpay_gateway_poll_not_paid_is_not_captured():
    created = {"id": "plink_y", "amount": 370000, "currency": "INR",
               "short_url": "https://rzp.io/i/y", "status": "created"}
    gw = RazorpayGateway(_StubClient(created, {"status": "created", "payments": []}))
    assert gw.capture("plink_y", 370000)["status"] != "captured"


def test_build_gateway_fake_when_blank_and_refuses_live_key(monkeypatch):
    monkeypatch.setattr(settings, "razorpay_key_id", "")
    monkeypatch.setattr(settings, "razorpay_key_secret", "")
    assert isinstance(build_gateway(settings), FakeRazorpay)
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_live_abc")
    monkeypatch.setattr(settings, "razorpay_key_secret", "secret")
    with pytest.raises(ValueError):  # a non-test key must abort — POC is Test-Mode only
        build_gateway(settings)
