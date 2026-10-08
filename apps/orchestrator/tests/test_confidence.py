"""The calibration contract (build step 5). If a weight/prior edit breaks routing, this goes red.

Promise guarded: easy jobs (delay, parts-in-stock) clear the 0.7 gate and auto-send; a complex job
stays below it and routes to a human — even when the LLM brags a self-rating of 1.0, and even when
the retrieval is perfectly grounded. That last part is what protects the live demo.
"""

from __future__ import annotations

from app.config import settings
from app.llm.confidence import confidence_factors, score_confidence

W = settings.confidence_weights
GF = settings.conf_grounding_full
T = settings.conf_threshold
# A fully-present context (all four key fields) — the easiest case for the data factor.
FULL_CTX = {
    "asset": {"model": "Daikin XYZ", "warranty": "active"},
    "technician": {"skills": ["daikin-inverter"]},
    "slaWindowMinutes": 120,
}


def _final(archetype: str, policy_result: str, top_score: float, llm_self: float) -> float:
    factors = confidence_factors(archetype, policy_result, top_score, FULL_CTX, llm_self, GF)
    final, _ = score_confidence(factors, W)
    return final


# --- the two "auto" promises -------------------------------------------------------------------
def test_delay_auto_sends():
    assert _final("delay", "APPROVED", 0.8, 0.9) >= T


def test_parts_in_stock_auto_sends():
    assert _final("parts", "APPROVED", 0.8, 0.8) >= T


def test_delay_auto_even_with_zero_grounding():
    # delay must clear the gate on difficulty + policy alone, not lean on the RAG score.
    assert _final("delay", "APPROVED", 0.0, 0.9) >= T


# --- the "human" promise, robustly -------------------------------------------------------------
def test_complex_routes_to_human_even_if_llm_brags():
    # LLM self-rates a perfect 1.0; the clamp caps it at the complex prior, so it can't inflate.
    assert _final("complex", "APPROVED", 0.8, 1.0) < T


def test_complex_stays_human_even_when_perfectly_grounded():
    # The whole point: a well-grounded complex job still goes to a human (the live-demo guarantee).
    assert _final("complex", "APPROVED", 1.0, 1.0) < T


# --- the clamp is one-directional --------------------------------------------------------------
def test_llm_can_lower_but_not_inflate():
    low = _final("delay", "APPROVED", 0.8, 0.2)   # pessimistic self-rating drags it down
    high = _final("delay", "APPROVED", 0.8, 1.0)  # but a 1.0 can't push past the prior ceiling
    assert low < high
    factors_hi = confidence_factors("delay", "APPROVED", 0.8, FULL_CTX, 1.0, GF)
    assert factors_hi["llm"] == 1.0 * 1.0  # delay prior is 1.0, so clamp leaves a 1.0 at 1.0


def test_denied_policy_tanks_confidence():
    # Nothing legal to offer → headroom 0 drags even an easy job down (and needs_human DENIED too).
    assert _final("delay", "DENIED", 0.8, 0.9) < _final("delay", "APPROVED", 0.8, 0.9)


def test_breakdown_is_auditable():
    factors = confidence_factors("parts", "PARTIAL", 0.6, FULL_CTX, 0.8, GF)
    final, breakdown = score_confidence(factors, W)
    assert breakdown["final"] == round(final, 4)
    assert set(breakdown["factors"]) == {"prior", "headroom", "grounding", "data", "llm"}
    assert breakdown["weights"] == W
