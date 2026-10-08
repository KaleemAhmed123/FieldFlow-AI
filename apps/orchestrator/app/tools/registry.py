"""The Toolbox — a controlled, MCP-shaped tool surface between the graph and the systems.

This is the seam a real MCP client drops behind later (Salesforce hosted MCP + an e-com MCP
server, fired from the SF UI). Today it dispatches to the in-process fakes; nothing about the
graph or the tests changes when the backend is swapped for the network — only `build_toolbox`.

Two kinds of tools, and the distinction is the whole point:
  - read   → a safe lookup. Dispatched straight to the backing system. The model may call freely.
  - action → a validated function that decides its own outcome. It runs the deterministic
             authority ladder (permission · state · validity) and returns a ToolResult; it may
             refuse. The model may *call* it but never decides the result. Raw write access to
             Salesforce never reaches the LLM.

Idempotency + audit + emit stay in the service layer (as in Step 1), so a node can call a tool
while staying DB-free. The tool runs only the deterministic ladder.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.commerce.razorpay import PaymentGateway
from app.commerce.service import CommerceService
from app.policy import TERMINAL_STATES
from app.tools.inventory import InventoryTools
from app.tools.salesforce import SalesforceTools


@dataclass
class ToolResult:
    """Uniform result for every call. Reads always ok=True with data; actions may refuse."""

    ok: bool
    data: Any = None
    reason: str | None = None


@dataclass
class _Tool:
    name: str
    kind: str  # "read" | "action"
    fn: Callable[..., Any]
    args: list[str]
    description: str


class Toolbox:
    """Register tools by name + kind; dispatch calls; describe the surface (for GET /tools)."""

    def __init__(self) -> None:
        self._tools: dict[str, _Tool] = {}

    def register(
        self, name: str, kind: str, fn: Callable[..., Any], *, args: list[str], description: str
    ) -> None:
        if kind not in ("read", "action"):
            raise ValueError(f"unknown tool kind {kind!r} for {name}")
        self._tools[name] = _Tool(name, kind, fn, args, description)

    def call(self, name: str, **kwargs: Any) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, reason=f"unknown tool '{name}'")
        missing = [a for a in tool.args if a not in kwargs]
        if missing:
            return ToolResult(ok=False, reason=f"{name} missing args: {', '.join(missing)}")
        if tool.kind == "read":
            # Read: safe lookup, wrap the raw return. No ladder.
            return ToolResult(ok=True, data=tool.fn(**kwargs))
        # Action: the function runs its own authority ladder and returns a ToolResult.
        return tool.fn(**kwargs)

    def describe(self) -> list[dict]:
        """The controlled surface, for the panel: name, kind, required args, one-line purpose."""
        return [
            {"name": t.name, "kind": t.kind, "args": t.args, "description": t.description}
            for t in self._tools.values()
        ]


def build_toolbox(
    salesforce: SalesforceTools,
    inventory: InventoryTools,
    commerce: CommerceService | None = None,
    gateway: PaymentGateway | None = None,
) -> Toolbox:
    """Register the Step-2 surface over the fakes. camelCase tool args (the contract) → the
    pythonic fake methods via thin adapters. Action tools run the ladder here, in the tool layer.

    `commerce` + `gateway` (Step 6) are optional: when both are passed, the commerce.* action tools
    are registered over the price authority + the payment gateway. Omit them (older callers/tests)
    and the surface is exactly the Step-2 one.

    Deferred seams (named, not built): knowledge.* (RAG step); workorder.close;
    reschedule.propose (today it's generate_options + policy_validate).
    """
    tb = Toolbox()

    # --- Read tools (safe lookups; concern-wise, one per object) -----------------------------
    tb.register(
        "salesforce.get_appointment", "read",
        lambda appointmentId: salesforce.get_appointment(appointmentId),
        args=["appointmentId"], description="The scheduled visit + its linked ids and SLA window.",
    )
    tb.register(
        "salesforce.get_customer", "read",
        lambda customerId: salesforce.get_customer(customerId),
        args=["customerId"], description="Customer name + contact.",
    )
    tb.register(
        "salesforce.get_asset", "read",
        lambda assetId: salesforce.get_asset(assetId),
        args=["assetId"], description="The serviced unit: model + warranty status.",
    )
    tb.register(
        "salesforce.get_technician", "read",
        lambda resourceId: salesforce.get_technician(resourceId),
        args=["resourceId"], description="ServiceResource: skills + territory (policy input).",
    )
    tb.register(
        "inventory.find_part", "read",
        lambda partNo: inventory.find_part(partNo),
        args=["partNo"], description="Live stock of a part per location (may be stale by execute).",
    )

    # --- Action tools (validated; the function decides, may refuse) ---------------------------
    def reserve(partNo: str, qty: int = 1) -> ToolResult:
        # Authority ladder for a reserve = the atomic stock check. Losing the race is a refusal,
        # not an oversell (drives NFR-5). The service layer keeps idempotency + audit.
        ok = inventory.reserve(partNo, qty)
        return ToolResult(
            ok=ok,
            data={"partNo": partNo, "qty": qty} if ok else None,
            reason=None if ok else f"no stock for '{partNo}'",
        )

    tb.register(
        "inventory.reserve", "action", reserve,
        args=["partNo"], description="Atomically hold a part. Refuses if stock is gone (NFR-5).",
    )

    def reschedule_confirm(appointmentId: str, slotId: str) -> ToolResult:
        # Authority ladder for a reschedule = appointment exists + case not terminal. Real SF adds
        # permission/territory/travel-time here once the org is wired; the shape stays the same.
        appt = salesforce.get_appointment(appointmentId)
        if appt is None:
            return ToolResult(ok=False, reason=f"unknown appointment '{appointmentId}'")
        if appt.get("caseState") in TERMINAL_STATES:
            return ToolResult(ok=False, reason=f"case state {appt['caseState']} is terminal")
        return ToolResult(ok=True, data=salesforce.reschedule(appointmentId, slotId))

    tb.register(
        "reschedule.confirm", "action", reschedule_confirm,
        args=["appointmentId", "slotId"],
        description="Apply a chosen slot after the ladder. Refuses on unknown/terminal case.",
    )

    # --- Commerce action tools (Step 6; only if a price authority + gateway were wired) ---------
    # Every one is a MUTATION that climbs the ladder in the tool layer (price authority / amount
    # check / gateway call) and returns a ToolResult that may refuse. Idempotency + audit + emit
    # stay in the service layer, so the graph nodes calling these stay DB-free.
    if commerce is not None and gateway is not None:
        def create_quote(workOrderId: str, partNo: str) -> ToolResult:
            # Price authority: the amount is computed from the book, never from the LLM.
            quote = commerce.build_quote(workOrderId, partNo)
            if quote["amountPaise"] <= 0:
                return ToolResult(ok=False, reason="quote amount must be positive")
            return ToolResult(ok=True, data=quote)

        tb.register(
            "commerce.create_quote", "action", create_quote,
            args=["workOrderId", "partNo"],
            description="Price a chargeable part + labour into a quote (price book is authority).",
        )

        def create_order(quote: dict) -> ToolResult:
            if not quote or quote.get("amountPaise", 0) <= 0:
                return ToolResult(ok=False, reason="cannot order a non-positive quote")
            return ToolResult(ok=True, data=commerce.create_order(quote))

        tb.register(
            "commerce.create_order", "action", create_order,
            args=["quote"], description="Turn an approved quote into an order (precedes payment).",
        )

        def create_payment_link(orderId: str, amountPaise: int, currency: str) -> ToolResult:
            if amountPaise <= 0:
                return ToolResult(ok=False, reason="payment amount must be positive")
            link = gateway.create_payment_link(orderId, amountPaise, currency)
            return ToolResult(ok=True, data=link)

        tb.register(
            "commerce.create_payment_link", "action", create_payment_link,
            args=["orderId", "amountPaise", "currency"],
            description="Create a Razorpay payment link for an order (→ RCS Open-URL).",
        )

        def capture_payment(
            paymentRef: str, amountPaise: int, reportedStatus: str = "captured"
        ) -> ToolResult:
            # The gateway is the authority on the outcome: the fake honours reportedStatus; the real
            # gateway polls Razorpay (ignores it). Idempotent → a repeat never double-charges.
            receipt = gateway.capture(paymentRef, amountPaise, reportedStatus)
            if receipt.get("status") != "captured":
                return ToolResult(ok=False, reason=f"payment {receipt.get('status')}", data=receipt)
            return ToolResult(ok=True, data=receipt)

        tb.register(
            "commerce.capture_payment", "action", capture_payment,
            args=["paymentRef", "amountPaise"],
            description="Capture/verify a payment. Idempotent — a repeat never charges twice.",
        )

        def refund(paymentId: str) -> ToolResult:
            result = gateway.refund(paymentId)
            if result.get("status") != "refunded":
                return ToolResult(ok=False, reason=result.get("reason", "refund failed"))
            return ToolResult(ok=True, data=result)

        tb.register(
            "commerce.refund", "action", refund,
            args=["paymentId"],
            description="Refund a captured payment (a human approves refunds). Idempotent.",
        )

    return tb
