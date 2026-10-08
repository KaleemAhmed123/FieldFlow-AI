"""The payment gateway seam, behind an interface so real Razorpay swaps in without touching callers.

Mock-first: FakeRazorpay records links/captures/refunds in memory. The real Razorpay Test-Mode
client (the `razorpay` SDK + webhook-signature verification) drops in behind the same Protocol at
the gated live step — one line in main.py changes, nothing else.

Money is integer PAISE everywhere (Razorpay's smallest unit; ₹1 = 100 paise). Never float money.

The one guard that matters: `capture` is IDEMPOTENT, keyed by paymentId. Razorpay captures a given
payment id exactly once; a retry/repeat returns the same receipt with alreadyCaptured=True and
charges nothing more. That is how "no double-charge if the same payment is fired twice" (NFR-2 for
money) is guaranteed at the gateway, independent of the envelope-level dedupe in the service layer.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from app.logging import get_logger

log = get_logger("razorpay")


class PaymentGateway(Protocol):
    def create_payment_link(self, order_id: str, amount_paise: int, currency: str) -> dict: ...
    def capture(self, payment_ref: str, amount_paise: int, reported_status: str = ...) -> dict: ...
    def refund(self, payment_ref: str) -> dict: ...


class FakeRazorpay:
    """In-memory Razorpay stand-in. Generated ids; idempotent capture/refund (no double-charge)."""

    def __init__(self) -> None:
        self._links: dict[str, dict] = {}       # paymentLinkId -> link
        self._captured: dict[str, dict] = {}     # paymentId -> receipt (the idempotency ledger)
        self._refunded: dict[str, dict] = {}     # paymentId -> refund

    def create_payment_link(self, order_id: str, amount_paise: int, currency: str) -> dict:
        link_id = f"plink_{uuid.uuid4().hex[:12]}"
        link = {
            "paymentLinkId": link_id,
            "orderId": order_id,
            "amountPaise": amount_paise,
            "currency": currency,
            # The hosted page the RCS "Approve & Pay" button opens (Open-URL). Fake, but shaped
            # like a Razorpay short link so the panel/card can render it as-is.
            "shortUrl": f"https://rzp.io/i/{link_id}",
            "status": "created",
        }
        self._links[link_id] = link
        log.info("fake_razorpay.payment_link", orderId=order_id, amountPaise=amount_paise)
        return link

    def capture(
        self, payment_ref: str, amount_paise: int, reported_status: str = "captured"
    ) -> dict:
        """Idempotent capture, keyed by payment_ref (the payment-link id). First call charges; a
        repeat returns the SAME receipt with alreadyCaptured=True — no double-charge.

        `reported_status` lets a test/demo force a non-captured outcome (e.g. "failed"): the fake
        honours it (the real gateway polls Razorpay and ignores it)."""
        if reported_status != "captured":
            return {"paymentRef": payment_ref, "status": reported_status,
                    "amountPaise": amount_paise}
        if payment_ref in self._captured:
            log.info("fake_razorpay.capture.duplicate", paymentRef=payment_ref)
            return {**self._captured[payment_ref], "alreadyCaptured": True}
        receipt = {
            "paymentId": f"pay_{uuid.uuid4().hex[:12]}",
            "paymentRef": payment_ref,
            "amountPaise": amount_paise,
            "currency": "INR",
            "status": "captured",
            "alreadyCaptured": False,
        }
        self._captured[payment_ref] = receipt
        log.info("fake_razorpay.capture", paymentRef=payment_ref, amountPaise=amount_paise)
        return receipt

    def refund(self, payment_ref: str) -> dict:
        """Refund a captured payment. Idempotent; refuses (status=failed) if never captured."""
        if payment_ref not in self._captured:
            return {"paymentRef": payment_ref, "status": "failed", "reason": "payment not captured"}
        if payment_ref in self._refunded:
            return {**self._refunded[payment_ref], "alreadyRefunded": True}
        refund = {
            "refundId": f"rfnd_{uuid.uuid4().hex[:12]}",
            "paymentRef": payment_ref,
            "amountPaise": self._captured[payment_ref]["amountPaise"],
            "status": "refunded",
            "alreadyRefunded": False,
        }
        self._refunded[payment_ref] = refund
        log.info("fake_razorpay.refund", paymentRef=payment_ref)
        return refund


class RazorpayGateway:
    """Real Razorpay (Test-Mode) behind the same Protocol. Payment confirmation is by POLLING
    (`payment_link.fetch`) — no inbound webhook, per the POC rule. Amounts are integer paise.

    The `razorpay` SDK client is INJECTED (built by `build_gateway`), so this module imports with no
    dependency; only a real test-key boot pulls the SDK in. Razorpay payment links auto-capture on
    pay, so `capture` here VERIFIES (polls) rather than charging again."""

    def __init__(self, client, currency: str = "INR") -> None:
        self._client = client
        self._currency = currency

    def create_payment_link(self, order_id: str, amount_paise: int, currency: str) -> dict:
        link = self._client.payment_link.create({
            "amount": amount_paise,
            "currency": currency,
            "reference_id": order_id,
            "description": f"FieldFlow order {order_id}",
            "notes": {"orderId": order_id},
        })
        return {
            "paymentLinkId": link["id"],
            "orderId": order_id,
            "amountPaise": link["amount"],
            "currency": link["currency"],
            "shortUrl": link["short_url"],
            "status": link["status"],
        }

    def capture(
        self, payment_ref: str, amount_paise: int, reported_status: str = "captured"
    ) -> dict:
        # Razorpay is the source of truth: poll the link, ignore the caller-reported status.
        link = self._client.payment_link.fetch(payment_ref)
        if link.get("status") != "paid":
            return {"paymentRef": payment_ref, "status": link.get("status") or "pending",
                    "amountPaise": amount_paise}
        payments = link.get("payments") or []
        pay_id = payments[0].get("payment_id") if payments else link.get("id")
        return {
            "paymentId": pay_id,
            "paymentRef": payment_ref,
            "amountPaise": link.get("amount", amount_paise),
            "currency": link.get("currency", self._currency),
            "status": "captured",
            "alreadyCaptured": False,
        }

    def refund(self, payment_ref: str) -> dict:
        # A real refund needs the razorpay payment id (not the link id); poll the link for it first.
        link = self._client.payment_link.fetch(payment_ref)
        payments = link.get("payments") or []
        if link.get("status") != "paid" or not payments:
            return {"paymentRef": payment_ref, "status": "failed", "reason": "no captured payment"}
        refund = self._client.payment.refund(payments[0]["payment_id"])
        return {"refundId": refund.get("id"), "paymentRef": payment_ref, "status": "refunded"}


def build_gateway(settings) -> PaymentGateway:
    """Pick the gateway from settings. Blank keys → FakeRazorpay (offline, the default). A key is
    accepted ONLY if it is a Razorpay TEST key (`rzp_test_`) — a live key aborts the boot, so a
    POC can't fire a real charge. The `razorpay` SDK imports lazily, only on the test-key path."""
    key_id, secret = settings.razorpay_key_id, settings.razorpay_key_secret
    if not key_id or not secret:
        return FakeRazorpay()
    if not key_id.startswith("rzp_test_"):
        raise ValueError(
            "Razorpay: refusing a non-test key (expected 'rzp_test_...'). POC is Test-Mode only."
        )
    import razorpay  # lazy: only pulled in when a real test key is configured
    client = razorpay.Client(auth=(key_id, secret))
    log.info("razorpay.live", mode="test")
    return RazorpayGateway(client, currency=settings.commerce_currency)


if __name__ == "__main__":  # ponytail self-check: the no-double-charge guarantee
    rp = FakeRazorpay()
    first = rp.capture("pay_1", 370000)
    second = rp.capture("pay_1", 370000)
    assert first["alreadyCaptured"] is False and second["alreadyCaptured"] is True
    assert len(rp._captured) == 1, "a duplicate capture must not charge twice"
    assert rp.refund("pay_nope")["status"] == "failed"  # refund of an uncaptured payment refuses
    assert rp.refund("pay_1")["status"] == "refunded"
    print("FakeRazorpay self-check OK")
