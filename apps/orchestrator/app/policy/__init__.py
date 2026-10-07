"""Policy engine — the deterministic authority. The LLM proposes; this decides.

Spine stub: pass-through with a recorded result. Real checks (SLA, skill, territory, inventory,
price, idempotency) land here next, and every mutation will route through it.
"""

from __future__ import annotations

from fieldflow_contract import SlotOption


def validate_options(options: list[SlotOption], context: dict) -> tuple[list[SlotOption], dict]:
    """Return (valid_options, policy_result). Spine: everything valid."""
    result = {"checked": ["(stub)"], "removed": [], "policyResult": "APPROVED"}
    return options, result
