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


def build_toolbox(salesforce: SalesforceTools, inventory: InventoryTools) -> Toolbox:
    """Register the Step-2 surface over the fakes. camelCase tool args (the contract) → the
    pythonic fake methods via thin adapters. Action tools run the ladder here, in the tool layer.

    Deferred seams (named, not built): knowledge.* (RAG step); commerce.* + workorder.close
    (commerce step); reschedule.propose (today it's generate_options + policy_validate).
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

    return tb
