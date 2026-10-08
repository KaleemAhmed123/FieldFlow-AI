"""Commerce logic — the deterministic price authority + quote/order builders.

The one rule, applied to money: the LLM may *propose which part* (it already does, in the option it
returns), but the **price book here decides the amount**. A model-suggested price is never trusted;
`build_quote` prices the part from the book + a fixed labour fee. This keeps "AI proposes,
deterministic policy decides" true for money.

Pure functions, no DB, no network. Money is integer PAISE (₹1 = 100 paise); rupees are a display
concern only. Quotes/orders live in the graph's state (not DB rows) — durable state (audit +
decision trace) is still the service layer's job, as for every other mutation.
"""

from __future__ import annotations

import uuid

# The price authority. Parts are priced here, not by the model. An unlisted part falls back to a
# flat default so a quote can always be produced (policy still gates whether we charge at all).
# Lives in code like the per-reason confidence priors — small, demo-scoped, reviewed by the team.
PRICE_BOOK_PAISE: dict[str, int] = {
    "CAP-492": 320000,   # ₹3,200  — compressor capacitor (the default parts-archetype part)
    "PCB-492": 480000,   # ₹4,800  — inverter control board (+ labour pushes over the ₹5k gate)
    "FAN-210": 140000,   # ₹1,400  — indoor blower fan motor
    "GAS-R32": 260000,   # ₹2,600  — R32 refrigerant top-up
    "SNSR-18": 90000,    # ₹900    — temperature sensor (cheap part)
    "COMP-900": 1250000,  # ₹12,500 — compressor swap (well over the human gate on its own)
}
DEFAULT_PART_PRICE_PAISE = 250000  # ₹2,500 fallback for a part not in the book


class CommerceService:
    """Holds the commerce config (labour fee, currency). Stateless beyond that."""

    def __init__(self, labour_paise: int, currency: str) -> None:
        self.labour_paise = labour_paise
        self.currency = currency

    def price_part(self, part_no: str) -> int:
        """The authority: a part's price in paise, from the book (never from the LLM)."""
        return PRICE_BOOK_PAISE.get(part_no, DEFAULT_PART_PRICE_PAISE)

    def build_quote(self, work_order_id: str, part_no: str) -> dict:
        """Price a chargeable part + labour into a quote. Amount is computed, never trusted."""
        part_paise = self.price_part(part_no)
        lines = [
            {"desc": f"Part {part_no}", "partNo": part_no, "amountPaise": part_paise},
            {"desc": "Labour", "amountPaise": self.labour_paise},
        ]
        amount = part_paise + self.labour_paise
        return {
            "quoteId": f"qt_{uuid.uuid4().hex[:12]}",
            "workOrderId": work_order_id,
            "lines": lines,
            "amountPaise": amount,
            "currency": self.currency,
            "priceAuthority": "price_book",  # show-your-work: the amount came from the book
        }

    def create_order(self, quote: dict) -> dict:
        """Turn an approved quote into an order (precedes the Razorpay payment link)."""
        return {
            "orderId": f"ord_{uuid.uuid4().hex[:12]}",
            "quoteId": quote["quoteId"],
            "workOrderId": quote["workOrderId"],
            "amountPaise": quote["amountPaise"],
            "currency": quote["currency"],
            "status": "CREATED",
        }


def rupees(amount_paise: int) -> str:
    """Display helper — paise → a ₹ string for the RCS card. Display only; math stays in paise."""
    return f"₹{amount_paise / 100:,.2f}"


if __name__ == "__main__":  # ponytail self-check: the price authority computes, doesn't trust
    svc = CommerceService(labour_paise=50000, currency="INR")
    q = svc.build_quote("WO-1", "CAP-492")
    assert q["amountPaise"] == 320000 + 50000, "amount must be book part price + labour"
    assert svc.price_part("UNLISTED") == DEFAULT_PART_PRICE_PAISE
    assert svc.create_order(q)["amountPaise"] == q["amountPaise"]
    # Print paise (ASCII) not the ₹ string — a Windows cp1252 console can't encode ₹.
    print("CommerceService self-check OK", q["amountPaise"], "paise")
