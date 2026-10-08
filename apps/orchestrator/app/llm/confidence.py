"""Evidence-weighted confidence: blend five checkable factors instead of trusting one LLM number.

Why: a single number the model emits is un-auditable and gameable (it can sound sure to "win").
So we compute `confidence = Σ(factor × weight)` from four deterministic signals already in the
system plus one from the LLM — and the LLM's slice is clamped so it can lower confidence but never
raise it above what the difficulty of the job warrants.

Each factor is normalized so a genuinely good case ≈ 1.0 (not "70% sure"); that normalization is
what stops strong jobs from being dragged below the gate and sent to a human needlessly.
"""

from __future__ import annotations

# Archetype prior = how hard this reason is, normalized so an easy job scores full marks.
# complex is 0.40 (not the planned 0.50) so the blended score stays below the 0.7 gate for the
# WHOLE grounding range [0,1]: ceiling = 0.45 + 0.55·prior = 0.67 at prior 0.40. At 0.50 the
# ceiling is 0.725, which would let a well-grounded complex job auto-send live (see build-step-5
# Updates). delay/parts are unaffected and clear 0.7 comfortably.
PRIOR = {"delay": 1.0, "parts": 0.85, "complex": 0.40}
# Policy headroom = how much legal room is left after validation.
HEADROOM = {"APPROVED": 1.0, "PARTIAL": 0.6, "DENIED": 0.0}
_DATA_FIELDS = ("asset.model", "asset.warranty", "technician.skills", "slaWindowMinutes")


def confidence_factors(
    archetype: str,
    policy_result: str,
    top_score: float,
    context: dict,
    llm_self: float,
    grounding_full: float,
) -> dict[str, float]:
    """Turn raw signals into five normalized [0,1] factors.

    - prior: difficulty of the reason (easy → 1.0).
    - headroom: APPROVED 1.0 · PARTIAL 0.6 · DENIED 0.0.
    - grounding: `min(1, top_score / grounding_full)` — a strong retrieval maps to full marks.
    - data: fraction of the key case fields that are present.
    - llm: `min(self_rating, prior)` — the clamp. The model can confirm or reduce, never inflate.
    """
    prior = PRIOR.get(archetype, 0.5)
    headroom = HEADROOM.get(policy_result, 0.0)
    grounding = min(1.0, max(0.0, top_score) / grounding_full) if grounding_full > 0 else 0.0
    asset = context.get("asset", {}) or {}
    tech = context.get("technician", {}) or {}
    present = [
        bool(asset.get("model")),
        bool(asset.get("warranty")),
        bool(tech.get("skills")),
        context.get("slaWindowMinutes") is not None,
    ]
    data = sum(present) / len(present)
    llm = min(max(0.0, llm_self), prior)  # the clamp: can only lower, never inflate
    return {"prior": prior, "headroom": headroom, "grounding": grounding, "data": data, "llm": llm}


def score_confidence(
    factors: dict[str, float], weights: dict[str, float]
) -> tuple[float, dict]:
    """Weighted blend, clamped to [0,1]. Returns (final, breakdown) for the decision trace."""
    final = sum(factors[k] * weights[k] for k in weights)
    final = max(0.0, min(1.0, final))
    breakdown = {
        "final": round(final, 4),
        "factors": {k: round(v, 4) for k, v in factors.items()},
        "weights": dict(weights),
    }
    return final, breakdown
