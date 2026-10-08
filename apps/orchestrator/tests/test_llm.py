"""The proposer ladder + the risk-tier floor (build step 5). Fully offline: providers are injected
fakes, so no SDK and no network. Proves the ladder order, bad-JSON repair, the 429 surface, and the
hard human-review floor.
"""

from __future__ import annotations

from types import SimpleNamespace

from app import policy
from app.llm.proposer import (
    Proposal,
    Proposer,
    RateLimited,
    build_proposer,
    parse_proposal,
)

CTX = {"technician": {"name": "Rahul", "skills": ["daikin-inverter"]}}


def _ok(provider: str):
    def fn(reason, ctx, k):
        return Proposal(options=[{"slotId": "s", "label": "L", "technician": "Rahul"}],
                        llm_confidence=0.7, explanation="ok", provider=provider, archetype="delay")
    return fn


def _raise(exc: Exception):
    def fn(reason, ctx, k):
        raise exc
    return fn


# --- ladder ordering ---------------------------------------------------------------------------
def test_first_working_provider_wins():
    p = Proposer([("groq", _ok("groq")), ("gemini", _ok("gemini"))])
    assert p("technician_delay", CTX, []).provider == "groq"


def test_falls_through_on_provider_error():
    p = Proposer([("groq", _raise(RuntimeError("boom"))), ("gemini", _ok("gemini"))])
    r = p("technician_delay", CTX, [])
    assert r.provider == "gemini"
    assert r.degraded is True  # we fell back off the primary → flagged, even though gemini answered


def test_rate_limit_note_rides_onto_a_working_fallback():
    p = Proposer([("groq", _raise(RateLimited(9))), ("gemini", _ok("gemini"))])
    r = p("technician_delay", CTX, [])
    assert r.provider == "gemini" and r.degraded is True
    assert "rate-limited" in r.rate_limit_note and "9" in r.rate_limit_note


def test_all_providers_fail_falls_to_deterministic():
    p = Proposer([("groq", _raise(RuntimeError())), ("gemini", _raise(RuntimeError()))])
    r = p("technician_delay", CTX, [])
    assert r.provider == "deterministic"
    assert r.degraded is True


def test_rate_limit_surfaces_a_note():
    p = Proposer([("groq", _raise(RateLimited(12)))])
    r = p("part_missing", CTX, [])
    assert r.provider == "deterministic" and r.degraded is True
    assert "rate-limited" in r.rate_limit_note and "12" in r.rate_limit_note


def test_bad_json_from_provider_falls_through():
    def bad(reason, ctx, k):
        return parse_proposal('{"confidence": 0.9}', "groq", reason)  # no options → ValueError
    p = Proposer([("groq", bad), ("gemini", _ok("gemini"))])
    assert p("technician_delay", CTX, []).provider == "gemini"


# --- JSON parsing / repair ---------------------------------------------------------------------
def test_parse_strips_nulls_and_clamps_confidence():
    raw = ('{"options":[{"slotId":"s","label":"L","technician":"R","partNo":null}],'
           '"confidence":1.5,"explanation":"x"}')
    pr = parse_proposal(raw, "groq", "part_missing")
    assert pr.options[0]["slotId"] == "s"
    assert "partNo" not in pr.options[0]     # null dropped
    assert pr.llm_confidence == 1.0          # out-of-range self-rating clamped to [0,1]
    assert pr.archetype == "parts"


# --- build_proposer wiring from settings -------------------------------------------------------
def test_keyless_settings_build_offline_deterministic():
    p = build_proposer(SimpleNamespace(groq_api_key="", gemini_api_key=""))
    r = p("technician_delay", CTX, [])
    assert r.provider == "deterministic" and r.degraded is False


def test_both_keys_wire_groq_then_gemini():
    p = build_proposer(SimpleNamespace(groq_api_key="x", gemini_api_key="y"))
    assert [name for name, _ in p.providers] == ["groq", "gemini"]


# --- risk-tier hard floor (OQ1) ----------------------------------------------------------------
def test_always_human_reason_routes_to_human_at_any_confidence():
    approved = {"policyResult": "APPROVED"}
    floor = {"safety_risk", "warranty_dispute"}
    assert policy.needs_human_for("safety_risk", 1.0, approved, floor) is True
    assert policy.needs_human_for("warranty_dispute", 0.99, approved, floor) is True


def test_score_driven_reasons_bypass_the_floor():
    approved = {"policyResult": "APPROVED"}
    floor = {"safety_risk", "warranty_dispute"}
    assert policy.needs_human_for("asset_complex", 0.95, approved, floor) is False  # high → auto
    assert policy.needs_human_for("asset_complex", 0.50, approved, floor) is True   # low → human
    assert policy.needs_human_for("technician_delay", 0.95, approved, floor) is False
