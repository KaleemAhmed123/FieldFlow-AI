"""Policy engine — the deterministic authority. The LLM proposes; this decides.

Given candidate options + the current case context, it removes every option that cannot
legally/technically happen and returns the survivors with a reason for each removal. No mutation
in the system is allowed to skip this. `needs_human` is the Level-3 gate (NFR-4): low confidence
or nothing clean to auto-offer must go to a human before anything executes.

A candidate is a plain dict; only the keys present are checked, so a bare slot passes everything
and a richer slot is held to every rule it declares:
  slotId, label, technician, note,
  requiredSkill  — must be in technician.skills
  startMinutes   — must be within context.slaWindowMinutes
  hour           — must be inside working hours
  requiresWarranty — asset must be under active warranty
  partNo         — must have stock in context.inventory snapshot
"""

from __future__ import annotations

CONFIDENCE_THRESHOLD = 0.7
WORK_START_HOUR = 9
WORK_END_HOUR = 18
CHECKS = ["skill", "sla", "working_hours", "entitlement", "inventory", "state"]
TERMINAL_STATES = {"CLOSED", "CANCELLED"}


def _removal_reason(cand: dict, context: dict) -> str | None:
    """First rule the candidate fails, or None if it is fully valid. Order = CHECKS."""
    case_state = context.get("caseState", "OPEN")
    if case_state in TERMINAL_STATES:
        return f"case state {case_state} is terminal"

    skills = set(context.get("technician", {}).get("skills", []))
    if (rs := cand.get("requiredSkill")) and rs not in skills:
        return f"technician lacks required skill '{rs}'"

    sla = context.get("slaWindowMinutes")
    if (sm := cand.get("startMinutes")) is not None and sla is not None and sm > sla:
        return f"start {sm}min breaches SLA window {sla}min"

    if (h := cand.get("hour")) is not None and not (WORK_START_HOUR <= h < WORK_END_HOUR):
        return f"start hour {h} outside working hours {WORK_START_HOUR}-{WORK_END_HOUR}"

    if cand.get("requiresWarranty") and context.get("asset", {}).get("warranty") != "active":
        return "asset not under active warranty"

    if (pn := cand.get("partNo")) and context.get("inventory", {}).get(pn, 0) <= 0:
        return f"part '{pn}' not in stock"

    return None


def validate_options(candidates: list[dict], context: dict) -> tuple[list[dict], dict]:
    """Return (valid_candidates, policy_result). policyResult: APPROVED | PARTIAL | DENIED."""
    valid: list[dict] = []
    removed: list[dict] = []
    for cand in candidates:
        reason = _removal_reason(cand, context)
        if reason:
            removed.append({"slotId": cand.get("slotId"), "reason": reason})
        else:
            valid.append(cand)

    if not valid:
        policy_result = "DENIED"
    elif removed:
        policy_result = "PARTIAL"
    else:
        policy_result = "APPROVED"

    return valid, {"checked": CHECKS, "removed": removed, "policyResult": policy_result}


def needs_human(confidence: float, policy_result: dict) -> bool:
    """Level-3 gate (NFR-4): below the confidence threshold, or nothing legal to offer."""
    return confidence < CONFIDENCE_THRESHOLD or policy_result.get("policyResult") == "DENIED"
