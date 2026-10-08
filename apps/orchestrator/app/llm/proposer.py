"""The proposer ladder: Groq -> Gemini -> deterministic. The first that returns a valid Proposal
wins; the deterministic fallback never fails, so the decision loop can't be taken down by an LLM
outage or rate-limit.

Mock-first: with no API keys set (tests, keyless runs) there are no live providers, so the ladder
is just the deterministic proposer — fully offline. Providers are injectable, so the ladder's
ordering is unit-testable without any SDK installed.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from app.data.catalog import model_for_asset
from app.logging import get_logger

log = get_logger("proposer")


def _asset_parts(context: dict) -> list[dict]:
    """The catalog parts for the asset in context (empty if the model isn't in the catalog)."""
    model_name = (context or {}).get("asset", {}).get("model", "")
    m = model_for_asset(model_name) if model_name else None
    return m["parts"] if m else []

# Ten realistic at-risk reasons collapse to three behaviour archetypes. Only the archetype drives
# the proposer + the confidence prior; the extra labels are demo variety (a real SF event carries
# any of them).
REASON_ARCHETYPE = {
    "technician_delay": "delay", "traffic_weather": "delay",
    "technician_no_show": "delay", "customer_access_issue": "delay",
    "part_missing": "parts", "wrong_part_shipped": "parts", "additional_fault_found": "parts",
    "asset_complex": "complex", "safety_risk": "complex", "warranty_dispute": "complex",
}
# The deterministic proposer's own self-rating per archetype (feeds the clamped LLM factor when no
# live model answers). Mirrors the old mock confidences.
SELF_RATING = {"delay": 0.9, "parts": 0.8, "complex": 0.5}


@dataclass
class Proposal:
    """What a proposer returns. `options` is untrusted — policy still validates every one."""
    options: list[dict]
    llm_confidence: float          # the model's self-rating (clamped later, never trusted raw)
    explanation: str
    provider: str                  # "groq" | "gemini" | "deterministic"
    archetype: str = "delay"
    degraded: bool = False         # True if a configured LLM was tried and we fell back
    rate_limit_note: str | None = None


class RateLimited(Exception):
    """A provider hit HTTP 429. Carries the server's Retry-After (seconds) for the trace."""

    def __init__(self, retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(f"rate limited; retry after {retry_after}s")


# A provider is any callable (reason, context, knowledge) -> Proposal. It may raise RateLimited or
# any other exception; the ladder catches both and moves to the next rung.
ProviderFn = Callable[[str, dict, list], Proposal]


def deterministic_proposal(reason: str, context: dict) -> Proposal:
    """The canned fallback (the old mock proposer). Never calls the network, never fails."""
    tech = context.get("technician", {}).get("name", "Technician")
    skill = (context.get("technician", {}).get("skills") or [None])[0]
    archetype = REASON_ARCHETYPE.get(reason, "delay")

    if archetype == "parts":
        options = [
            {"slotId": "t-part-1", "label": "TODAY 15:00-17:00", "technician": tech,
             "note": "After part fitted", "requiredSkill": skill, "partNo": "CAP-492"},
            {"slotId": "t-swap-1", "label": "TOMORROW 10:00-12:00", "technician": tech,
             "note": "Loaner unit, no part needed", "requiredSkill": skill},
        ]
        explanation = "Offer the part-fit slot plus a loaner fallback if the part is unavailable."
    else:
        options = [
            {"slotId": "t-today-1", "label": "TODAY 11:00-13:00", "technician": tech,
             "note": "Same technician", "requiredSkill": skill},
            {"slotId": "t-tomorrow-1", "label": "TOMORROW 09:00-11:00", "technician": tech,
             "note": "Earlier slot", "requiredSkill": skill},
        ]
        explanation = (
            "Re-offer two slots with the same technician."
            if archetype == "delay"
            else "Complex job - propose slots but flag for human review."
        )

    return Proposal(
        options=options, llm_confidence=SELF_RATING[archetype], explanation=explanation,
        provider="deterministic", archetype=archetype,
    )


# The JSON schema the live providers ask the model to fill. Kept tiny on purpose: the model only
# proposes slots + a self-rating + a one-line why; policy decides everything that matters.
PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "options": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "slotId": {"type": "string"},
                    "label": {"type": "string"},
                    "technician": {"type": "string"},
                    "note": {"type": "string"},
                    "requiredSkill": {"type": "string"},
                    "partNo": {"type": "string"},
                },
                "required": ["slotId", "label", "technician"],
            },
        },
        "confidence": {"type": "number"},
        "explanation": {"type": "string"},
    },
    "required": ["options", "confidence", "explanation"],
}


def build_prompt(reason: str, context: dict, knowledge: list) -> tuple[str, str]:
    """(system, user) prompt. We hand the model the canned options as a starting point and the
    retrieved knowledge, and ask it to pick/refine + rate + explain. It cannot invent authority:
    policy re-validates whatever comes back."""
    archetype = REASON_ARCHETYPE.get(reason, "delay")
    seed = deterministic_proposal(reason, context)
    cites = "\n".join(
        f"- {k.get('source')} {k.get('locator')}: {k.get('snippet')}" for k in (knowledge or [])
    ) or "(no knowledge retrieved)"
    parts = _asset_parts(context)
    parts_list = "\n".join(
        f"- {p['partNo']}: {p['name']}" + (" (scarce)" if p.get("scarce") else "") for p in parts
    ) or "(no catalog parts for this asset)"
    system = (
        "You are a field-service recovery assistant. Propose appointment options to recover an "
        "at-risk job. You ONLY propose; a deterministic policy engine validates and may reject "
        "every option, and a human approves risky ones. Rate your confidence [0,1] honestly - a "
        "complex or poorly-grounded job should score low.\n"
        "RULES: (1) For a 'delay' archetype the fix is purely rescheduling - NEVER attach a part "
        "(omit partNo on every option). (2) If a part is genuinely needed, use ONLY a partNo from "
        "the asset's catalog parts listed below - never invent one. (3) Prefer options that do not "
        "depend on a scarce part. Reply ONLY as JSON matching the schema."
    )
    user = (
        f"Reason: {reason} (archetype: {archetype})\n"
        f"Customer asset: {context.get('asset', {})}\n"
        f"Technician: {context.get('technician', {})}\n"
        f"SLA window (min): {context.get('slaWindowMinutes')}\n"
        f"Asset catalog parts (the ONLY valid part numbers):\n{parts_list}\n"
        f"Retrieved knowledge:\n{cites}\n\n"
        f"Suggested options to refine:\n{json.dumps(seed.options)}\n"
        "Return JSON: {options:[{slotId,label,technician,note,requiredSkill?,partNo?}], "
        "confidence:number, explanation:string}."
    )
    return system, user


def parse_proposal(
    raw: str | dict, provider: str, reason: str, context: dict | None = None
) -> Proposal:
    """Parse a provider's JSON into a strict Proposal. Raises ValueError on anything unusable so
    the ladder falls through to the next rung.

    Grounding is ENFORCED here, not just asked for in the prompt: a 'delay' never carries a part,
    and any partNo the model invents that isn't in the asset's catalog is stripped. Policy then
    still validates stock/skill on whatever survives — the model can never smuggle in authority."""
    data = json.loads(raw) if isinstance(raw, str) else raw
    options = data.get("options")
    if not isinstance(options, list) or not options:
        raise ValueError("no options in LLM output")
    archetype = REASON_ARCHETYPE.get(reason, "delay")
    valid_parts = {p["partNo"] for p in _asset_parts(context or {})}
    clean: list[dict] = []
    for o in options:
        if not (o.get("slotId") and o.get("label") and o.get("technician")):
            raise ValueError("option missing required keys")
        item = {k: v for k, v in o.items() if v is not None}
        part = item.get("partNo")
        if part and (archetype == "delay" or (valid_parts and part not in valid_parts)):
            item.pop("partNo", None)  # ground out: delay needs no part; unknown parts are invented
        clean.append(item)
    conf = float(data.get("confidence", 0.0))
    return Proposal(
        options=clean, llm_confidence=max(0.0, min(1.0, conf)),
        explanation=str(data.get("explanation", "")).strip() or "(no explanation)",
        provider=provider, archetype=REASON_ARCHETYPE.get(reason, "delay"),
    )


@dataclass
class Proposer:
    """Ordered live providers + the deterministic floor. Call as (reason, context, knowledge)."""
    providers: list[tuple[str, ProviderFn]] = field(default_factory=list)

    def __call__(self, reason: str, context: dict, knowledge: list) -> Proposal:
        # `failed`/`note` ride onto whatever rung ultimately answers, so a 429 on the primary is
        # surfaced in the trace even when a fallback provider (not just deterministic) succeeds.
        note = None
        failed = False
        for name, fn in self.providers:
            try:
                proposal = fn(reason, context, knowledge)
                proposal.degraded = failed       # True if we fell back from a higher rung
                proposal.rate_limit_note = note
                log.info("proposer.ok", provider=name, degraded=failed)
                return proposal
            except RateLimited as exc:
                failed = True
                secs = int(exc.retry_after) if exc.retry_after else "?"
                note = f"AI rate-limited - used fallback. Full AI retry in ~{secs}s."
                log.error("proposer.rate_limited", provider=name, retry_after=exc.retry_after)
            except Exception as exc:  # noqa: BLE001 — any provider failure falls to the next rung
                failed = True
                log.error("proposer.failed", provider=name, error=str(exc))
        proposal = deterministic_proposal(reason, context)
        proposal.degraded = failed
        proposal.rate_limit_note = note
        if failed:
            log.info("proposer.degraded_to_deterministic")
        return proposal


def build_proposer(settings, providers: list[tuple[str, ProviderFn]] | None = None) -> Proposer:
    """Build the ladder from settings: Groq first, then Gemini, each only if its key is set.
    Providers can be injected (tests) to exercise the ladder without any SDK."""
    if providers is None:
        providers = []
        if settings.groq_api_key:
            from app.llm.groq import groq_propose
            providers.append(("groq", lambda r, c, k: groq_propose(settings, r, c, k)))
        if settings.gemini_api_key:
            from app.llm.gemini import gemini_propose
            providers.append(("gemini", lambda r, c, k: gemini_propose(settings, r, c, k)))
    return Proposer(providers=providers)
