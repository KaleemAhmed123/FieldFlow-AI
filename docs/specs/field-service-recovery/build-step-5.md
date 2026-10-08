# Build Step 5 — Groq LLM as the real proposer (+ evidence-weighted confidence)

**Status:** Planned — decisions locked 2026-10-08, not yet built · **Created:** 2026-10-08 ·
**Last updated:** 2026-10-08

> Goal: replace the mock proposer with a **real LLM** that reads the case + the retrieved knowledge
> and returns `{options, confidence, explanation}` — while keeping the one rule intact: the LLM only
> *proposes*; deterministic policy still decides; humans still approve risk. Build order #5
> ([`scaffold.md`](scaffold.md) → "Groq wired for the decision + explanation step, with a cached
> fallback for live demos").

## The one rule (unchanged)

**The LLM proposes. Policy decides. Humans approve risk. Tools act and may refuse.** The LLM's
output is **untrusted**: we validate its JSON into a strict shape, and `policy.validate_options`
still filters every option before a customer sees it. The LLM cannot widen what is allowed, and (see
the confidence design) it cannot inflate its way past the human-approval gate.

## What you asked for (confirmed 2026-10-08)

- **Primary model: Groq `llama-3.3-70b-versatile`** (D1). Most predictable JSON, 280 tok/s, free tier.
- **Fallback ladder (D2):** Groq → **Gemini `gemini-2.5-flash`** (a *different* provider, so a Groq
  rate-limit/outage doesn't take us down) → **deterministic canned proposer** (today's `_propose`,
  never fails). Both `GROQ_API_KEY` and `GEMINI_API_KEY` are in `.env`.
- **Graceful rate-limits:** on HTTP 429, read Groq's `Retry-After`, fall back, and **surface it** in
  the decision trace + panel: *"AI rate-limited — used fallback. Full AI retry in ~Ns."*
- **Evidence-weighted confidence (D3):** don't trust a single number the LLM invents — compute
  confidence from checkable factors, each weighted; the LLM is one factor and **cannot inflate**.
  Weighted so genuinely-good cases are NOT dragged below the gate (the calibration concern below).
- **Dependencies (D4):** add `groq` + `google-genai` (the current unified Google SDK; replaces the
  deprecated `google-generativeai`).
- **Record the design in docs** (this file; context-doc update gated — see Open questions OQ5).

## Model research (why these, what was rejected)

Source of truth: [Groq models](https://console.groq.com/docs/models) ·
[Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits).

| Model | Role | Why / why not |
|-------|------|---------------|
| `llama-3.3-70b-versatile` (Groq) | **primary** | predictable JSON, strong reasoning, 280 tok/s, free |
| `openai/gpt-oss-120b` (Groq) | alt | strongest reasoning; formatting slightly less predictable |
| `openai/gpt-oss-20b` (Groq) | possible fast fallback | fast but less reasoning headroom |
| `llama-3.1-8b-instant` (Groq) | rejected | too shallow for an honest confidence rating |
| Qwen / MiniMax (Groq preview) | rejected | *preview* = can change/vanish; not for a reliable demo |
| `gemini-2.5-flash` (Google) | **cross-provider fallback** | native JSON schema, generous free tokens |
| Gemini Pro | rejected | removed from the free tier since Apr 2026 |

Free-tier reality (verify in each console; they drift): Groq ~30 RPM / ~1,000 RPD per model; Gemini
2.5 Flash ~10–15 RPM / ~500–1,500 RPD. Fine for a demo, **not** production — hence the ladder.

## The evidence-weighted confidence score (the headline addition)

**Problem it solves:** a single LLM-emitted number is (a) un-auditable and (b) gameable — the model
can sound confident to "win." And a naive average of weak signals drags every case to the middle, so
good jobs trip the human-approval gate needlessly.

**Design:** `confidence = Σ(factor × weight)`, clamped to [0,1], from five factors — four
deterministic (already in the system), one from the LLM.

| Factor | Weight | Normalized so "good" ≈ 1.0 |
|--------|-------:|----------------------------|
| **Archetype prior** (difficulty of the reason) | **0.40** | delay 1.0 · parts 0.85 · complex 0.5 |
| **Policy headroom** (legal options left) | 0.20 | APPROVED 1.0 · PARTIAL 0.6 · DENIED 0.0 |
| **Grounding** (RAG strength) | 0.15 | `min(1, top_rerank_score / 0.6)` — a 0.6+ rerank is *strong* |
| **Data completeness** | 0.10 | fraction of {asset model, warranty, skill, SLA window} present |
| **LLM self-rating** (skeptical) | 0.15 | `min(self_rating, archetype_prior)` — can **lower, never inflate** |

**Three guards that answer the calibration concern (over-escalation):**
1. **Normalize, don't use raw.** A rerank of 0.7 means "well grounded," so it maps to full marks —
   not "70% sure." Without this, strong cases look weak.
2. **Difficulty dominates (prior = 0.40).** A clean `delay` lands ~0.98 and `parts` ~0.91 — both
   clear 0.7 comfortably and auto-send. Only genuinely hard `complex` sits ~0.68 → human. So we do
   **not** add a human-in-loop where the AI could have handled it.
3. **LLM clamp.** The LLM's slice can confirm or reduce confidence but never raise it above the
   archetype prior, so it cannot brag a risky `complex` case past the gate.

**The gate is unchanged:** `policy.needs_human(confidence, policy_result)` still triggers on
`confidence < 0.7` or `DENIED`. We only change *how confidence is computed*.

**Explainability (demo gold):** the decision trace carries the full breakdown —
`{final, factors:{prior, headroom, grounding, data, llm}, weights}` — so the panel can show
*"Confidence 0.68: grounding 0.83, but complex job (prior 0.5) and the AI rated itself 0.4."*

**Calibration is a contract, not a vibe.** A `test_confidence.py` asserts: `delay` & `parts`
(part in stock) → `final ≥ 0.7` (auto); `complex` → `final < 0.7` (human) — even when the LLM
self-rates 1.0. If a weight edit breaks routing, the test goes red. Weights live in `config` so they
are tunable without code changes.

**Ponytail:** this is one pure function `score_confidence(factors) -> (float, breakdown)` + a weights
dict in config. No framework. One module, one test.

## Plan

```
generate_options ──▶ Proposer.propose(reason, context, knowledgeSources)
                         │  tries Groq → Gemini → deterministic (first that returns valid JSON wins)
                         ▼
                   Proposal{options[], llm_confidence, explanation, provider, degraded?}
                         │
                   score_confidence(factors)         ← blends LLM slice with 4 deterministic signals
                         ▼
   policy_validate (unchanged) ──▶ needs_human(final_confidence, policy_result) ──▶ …trace carries
                                    the breakdown + explanation + provider + any rate-limit note
```

**Files:**
- **new `app/llm/proposer.py`** — `Proposal` (pydantic, strict), the `Proposer` ladder, and the
  deterministic fallback (reuses today's `_propose`). Validates + repairs/falls back on bad JSON.
- **new `app/llm/groq.py`** — Groq call (structured output / `response_format` JSON schema), 429 →
  `RateLimited(retry_after)`.
- **new `app/llm/gemini.py`** — Gemini call (`response_schema`), same `Proposal` out.
- **new `app/llm/confidence.py`** — `score_confidence(factors) -> (float, breakdown)` + weights.
- **`app/graph/build.py`** — `generate_options` calls the proposer + confidence; drops the hard-coded
  `_propose`/`CONFIDENCE_BY_ARCHETYPE` (prior moves into `confidence.py`). Trace carries
  `explanation`, `confidenceBreakdown`, `llmProvider`, `rateLimitNote`.
- **`app/config.py` + `.env.example`** — `llm_provider`, `GROQ_API_KEY`, `GEMINI_API_KEY`, model ids,
  temperature, timeout, and the confidence weights/threshold.
- **`pyproject.toml`** — add `groq`, `google-genai`.
- **tests** — `tests/test_llm.py` (ladder: Groq fail → Gemini → deterministic; bad JSON → fallback;
  429 surfaces a note), `tests/test_confidence.py` (the calibration contract). Graph tests inject a
  **fake proposer**, so the existing 28 stay offline + green.
- **spec + playbook** — this file's Explanation on ship; Groq/Gemini env + smoke commands in
  `playbook.md`.

**Order:** config/deps → confidence module + test → proposer seam + deterministic fallback → Groq →
Gemini → wire into graph (fake proposer in tests) → all green → (gated) one live Groq call + a forced
429 to prove the ladder → playbook + this file's Explanation.

**Alternatives rejected:** LLM sets confidence alone (un-auditable, gameable); same-provider fallback
(doesn't survive a Groq rate-limit); 8B model (too shallow); preview models (unstable); a disk cache
of last-good proposals (the deterministic fallback already guarantees "never breaks" — YAGNI unless
we want byte-identical replays).

## Open questions (recommended answers; confirm before/while building)

- **OQ1 — complex/safety: score-only, or a hard human floor too?** *Rec: score-only.* The clamp +
  calibration test already keep `complex` below 0.7 even if the LLM brags. Add a one-line hard floor
  only if a real case ever slips to auto.
- **OQ2 — exact weights.** *Rec: the table above (prior 0.40 / headroom 0.20 / grounding 0.15 /
  data 0.10 / llm 0.15).* The calibration test is the real contract; tune in config.
- **OQ3 — structured output method.** *Rec: use each provider's native JSON mode* (Groq
  `response_format` json_schema, Gemini `response_schema`) with a pydantic schema, then a lenient
  parse + fallback as a safety net.
- **OQ4 — temperature.** *Rec: 0.2* (low — we want stable, parseable proposals, not creativity).
- **OQ5 — context-doc update (gated).** The confidence design touches
  [`context/02-orchestration-and-policy.md`](context/02-orchestration-and-policy.md) (the gate) and
  [`context/06-principles-and-decisions.md`](context/06-principles-and-decisions.md) (O1 LLM switch).
  *Rec: after Step 5 ships, add a short "evidence-weighted confidence" note to context/02.* **Gated on
  your yes** (CLAUDE.md rule: ask before rewriting context docs).

## Tasks

- [ ] Config + deps (`groq`, `google-genai`, keys, weights, threshold).
- [ ] `confidence.py` + `test_confidence.py` (calibration contract: delay/parts auto, complex human).
- [ ] `proposer.py` — `Proposal` schema, the ladder, deterministic fallback.
- [ ] `groq.py` (structured output, 429 → RateLimited).
- [ ] `gemini.py` (fallback).
- [ ] Wire into `generate_options`; trace carries explanation + breakdown + provider + rate-limit note.
- [ ] `test_llm.py` (ladder + bad-JSON fallback + 429 note); existing 28 green with a fake proposer.
- [ ] Rate-limit surfaced on the panel.
- [ ] **Gated:** one live Groq call + a forced 429 to prove the fallback; then playbook + Explanation.

## Updates

- **2026-10-08** — Plan created and decisions locked after Step 4 went live-verified. Model =
  `llama-3.3-70b-versatile`; fallback Groq→Gemini(2.5-flash)→deterministic; evidence-weighted
  confidence approved with the calibration guards (normalize + prior-dominant + LLM clamp + a
  calibration test) to prevent false human escalation. Deps `groq` + `google-genai` approved. Not yet
  built — next session implements mock-first.

## Explanation

_To be written when Step 5 ships (same 7 sections as the other steps)._
