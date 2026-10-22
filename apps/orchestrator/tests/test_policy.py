"""The policy engine decides, not the LLM: it removes illegal options and keeps valid ones."""

from __future__ import annotations

from app import policy


def _context() -> dict:
    return {
        "technician": {"name": "Rahul", "skills": ["daikin-inverter"]},
        "asset": {"warranty": "active"},
        "slaWindowMinutes": 120,
        "inventory": {"CAP-492": 1},
        "caseState": "OPEN",
    }


def test_removes_wrong_skill_and_outside_sla_keeps_valid():
    candidates = [
        {"slotId": "ok", "label": "valid", "technician": "Rahul",
         "requiredSkill": "daikin-inverter", "startMinutes": 90},
        {"slotId": "bad-skill", "label": "x", "technician": "Rahul",
         "requiredSkill": "lg-washer"},                       # tech lacks this skill
        {"slotId": "late", "label": "x", "technician": "Rahul", "startMinutes": 300},  # > SLA 120
    ]

    valid, result = policy.validate_options(candidates, _context())

    assert [c["slotId"] for c in valid] == ["ok"]
    assert result["policyResult"] == "PARTIAL"
    removed = {r["slotId"]: r["reason"] for r in result["removed"]}
    assert "skill" in removed["bad-skill"]
    assert "SLA" in removed["late"]


def test_removes_out_of_hours_and_past_keeps_in_hours():
    # AI-BEH-01: with `hour` / `startMinutes` now fed in, the once-dormant checks fire.
    candidates = [
        {"slotId": "ok", "label": "x", "technician": "Rahul", "hour": 14},        # in working hours
        {"slotId": "night", "label": "x", "technician": "Rahul", "hour": 2},      # 2 a.m. → out
        {"slotId": "past", "label": "x", "technician": "Rahul", "startMinutes": -30},  # past
    ]

    valid, result = policy.validate_options(candidates, _context())

    assert [c["slotId"] for c in valid] == ["ok"]
    removed = {r["slotId"]: r["reason"] for r in result["removed"]}
    assert "working hours" in removed["night"]
    assert "past" in removed["past"]


def test_all_invalid_is_denied():
    valid, result = policy.validate_options(
        [{"slotId": "p", "label": "x", "technician": "R", "partNo": "CAP-492"}],
        {**_context(), "inventory": {"CAP-492": 0}},  # part out of stock
    )
    assert valid == []
    assert result["policyResult"] == "DENIED"


def test_needs_human_on_low_confidence_or_denied():
    approved = {"policyResult": "APPROVED"}
    assert policy.needs_human(0.5, approved) is True          # below threshold
    assert policy.needs_human(0.95, approved) is False        # confident + legal → auto
    assert policy.needs_human(0.95, {"policyResult": "DENIED"}) is True  # nothing to offer
