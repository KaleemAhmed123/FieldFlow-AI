# Build Step 5 — Groq LLM as the real proposer (+ evidence-weighted confidence)

**Status:** SHIPPED + LIVE-VERIFIED 2026-10-08 (47 pytest green, ruff clean; real Groq + Gemini +
ladder-fallback proven on the user's keys) · **Created:** 2026-10-08 · **Last updated:** 2026-10-08

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

> **NOTE (2026-10-08):** the originally-planned `llama-3.3-70b-versatile` and `gemini-2.5-flash`
> were **both gone** from the user's free tiers when we went live (404 / "no longer available"). The
> **live-locked** defaults below are the proven survivors. Free-tier model ids drift — always verify
> per account with the SDK's `.models.list()`.

| Model | Role | Why / why not |
|-------|------|---------------|
| `openai/gpt-oss-120b` (Groq) | **primary (live-locked)** | strongest reasoning on the key; verified live, self-rated 0.92 on a delay case |
| `openai/gpt-oss-20b` (Groq) | fast alt | faster, less reasoning headroom |
| `llama-3.3-70b-versatile` (Groq) | ~~planned primary~~ | **404 on the user's key** — not accessible |
| `gemini-flash-latest` (Google) | **cross-provider fallback (live-locked)** | floating alias → survives version rotation; verified live |
| `gemini-3.8-flash` (Google) | pinned alt | the exact version Google's 404 recommended; reproducible but needs re-pinning |
| `gemini-2.0/2.5-flash` (Google) | ~~planned fallback~~ | **gone from the free tier** by 2026-10-08 |

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

**The gate (risk-tiering, OQ1):** a human is required when **any** of:
`reason in ALWAYS_HUMAN_REASONS` (hard floor: `safety_risk`, `warranty_dispute`) **or**
`confidence < 0.7` **or** `policyResult == DENIED`. The hard floor means a safety/legal case is never
auto-approved on the model's confidence — exactly how production risk systems tier decisions. We only
change *how confidence is computed*; the threshold logic gains the floor.

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
- **`app/config.py` + `.env.example`** — the full tunable surface (OQ2): `LLM_PROVIDER`, keys, model
  ids, `LLM_TEMPERATURE`/`TOP_P`/`MAX_TOKENS`/`TIMEOUT_S`/`MAX_RETRIES`, the five `CONF_W_*` weights,
  `CONF_THRESHOLD`, `CONF_GROUNDING_FULL`, and `ALWAYS_HUMAN_REASONS`.
- **`app/policy/__init__.py`** — `needs_human` gains the `reason in ALWAYS_HUMAN_REASONS` hard floor
  (risk-tiering, OQ1); signature takes the reason (or a thin `needs_human_for(reason, conf, result)`).
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

## Open questions — ANSWERED 2026-10-08

- **OQ1 — complex/safety: score-only, or a hard human floor too?** **ANSWER: both (risk-tiering, the
  way real companies do it).** The calibrated score is the primary gate, **plus** a hard "always route
  to human" floor for named high-risk reasons — `ALWAYS_HUMAN_REASONS = {"safety_risk",
  "warranty_dispute"}` — which skip straight to human approval regardless of any score. Rationale:
  safety-critical and legal/financial decisions are never auto-approved on a model's confidence in
  production. The list is **env-configurable**. `asset_complex` stays score-driven (it already lands
  <0.7). Implemented in `needs_human` (or a thin wrapper) as `reason in ALWAYS_HUMAN_REASONS or
  confidence < threshold or DENIED`.
- **OQ2 — weights + config.** **ANSWER: approved**, and **keep all LLM + confidence knobs in `.env`**
  so we can tweak/learn without code edits. Env surface: `LLM_PROVIDER`, model ids, `LLM_TEMPERATURE`,
  `LLM_TOP_P`, `LLM_MAX_TOKENS`, `LLM_TIMEOUT_S`, `LLM_MAX_RETRIES`; confidence
  `CONF_W_PRIOR/HEADROOM/GROUNDING/DATA/LLM` (default 0.40/0.20/0.15/0.10/0.15), `CONF_THRESHOLD`
  (0.7), `CONF_GROUNDING_FULL` (0.6 normalizer), `ALWAYS_HUMAN_REASONS`. The calibration test stays
  the contract — if a tweak breaks delay/parts→auto or complex/safety→human, it goes red.
- **OQ3 — structured output method.** *Rec stands:* each provider's native JSON mode (Groq
  `response_format` json_schema, Gemini `response_schema`) with a pydantic schema + a lenient parse
  and fallback as the safety net.
- **OQ4 — temperature.** *Rec stands: 0.2* (now an env knob, per OQ2).
- **OQ5 — context-doc update.** **ANSWER: approved.** After Step 5 ships, add a short
  "evidence-weighted confidence + risk-tiering" note to
  [`context/02-orchestration-and-policy.md`](context/02-orchestration-and-policy.md) (the gate) — and
  a one-liner under O1 in [`context/06-principles-and-decisions.md`](context/06-principles-and-decisions.md).

## Tasks

- [x] Config + **all LLM + confidence knobs in env** per OQ2 (deps `groq`/`google-genai` NOT added
  yet — gated). `.env.example` updated.
- [x] `confidence.py` + `test_confidence.py` (calibration contract: delay/parts auto, complex human —
  robust across the full grounding range).
- [x] Risk-tier hard floor as `needs_human_for` (`ALWAYS_HUMAN_REASONS`) + a test: `safety_risk` →
  human even at confidence 1.0.
- [x] `proposer.py` — `Proposal`, the ladder, deterministic fallback, shared prompt + JSON parser.
- [x] `groq.py` (structured output, 429 → `RateLimited`; lazy import).
- [x] `gemini.py` (cross-provider fallback; lazy import).
- [x] Wire into `generate_options` + `policy_validate`; trace carries `explanation`,
  `confidenceBreakdown`, `llmProvider`, `degraded`, `rateLimitNote`.
- [x] `test_llm.py` (ladder order + bad-JSON fallthrough + 429 note + floor); existing 28 green with
  the deterministic proposer (offline default).
- [x] **Deps added + live-verified:** `groq` + `google-genai` installed; real Groq + Gemini calls +
  a forced-429/503 fallback all proven on the user's keys (see Updates 2026-10-08 LIVE-VERIFIED).
- [ ] Rate-limit surfaced on the **panel** (trace carries `rateLimitNote`/`degraded`; panel is Step 8).
- [x] **OQ5 done (user-approved 2026-10-08):** confidence + risk-tiering note added to context/02
  (new "Confidence" section) and context/06 (O1 updated).

## Updates

- **2026-10-08** — Plan created and decisions locked after Step 4 went live-verified. Model =
  `llama-3.3-70b-versatile`; fallback Groq→Gemini(2.5-flash)→deterministic; evidence-weighted
  confidence approved with the calibration guards (normalize + prior-dominant + LLM clamp + a
  calibration test) to prevent false human escalation. Deps `groq` + `google-genai` approved. Not yet
  built — next session implements mock-first.
- **2026-10-08 (OQs answered)** — OQ1: **risk-tiering** — score is the primary gate **plus** a hard
  `ALWAYS_HUMAN_REASONS` floor (`safety_risk`, `warranty_dispute`) that forces human review regardless
  of confidence (how real companies tier safety/legal decisions). OQ2: weights approved + **every LLM
  and confidence knob moves to `.env`** (provider, models, temperature, top_p, max_tokens, timeout,
  retries, the 5 weights, threshold, grounding normalizer, always-human list) so they're tweakable.
  OQ3 native JSON mode, OQ4 temp 0.2 (now an env knob). OQ5: **approved** to add the confidence +
  risk-tiering note to context/02 + a line under O1 in context/06, **after Step 5 ships**.

- **2026-10-08 (built mock-first)** — Implemented offline. **46 tests pass** (was 28; +9 confidence,
  +9 ladder/floor), ruff clean, `import app.main` OK. Three decisions made during the build, named
  here because they refine the locked plan:
  1. **Confidence is computed in `policy_validate`, not `generate_options`.** One of the five factors
     is policy headroom (APPROVED/PARTIAL/DENIED), which isn't known until `validate_options` runs.
     `generate_options` now only produces the `Proposal`; the blend happens right after validation.
  2. **`complex` prior lowered 0.50 → 0.40.** With the planned 0.50, the complex *ceiling* (full
     grounding + APPROVED policy + full data + LLM self-rating clamped to the prior) is
     `0.45 + 0.55·0.50 = 0.725` — **above** the 0.7 gate. That means a well-grounded `asset_complex`
     job would auto-send **live** (the fake store's low retrieval scores hid this; Jina's rerank
     scores are higher). At prior 0.40 the ceiling is `0.45 + 0.55·0.40 = 0.67`, so complex routes to
     a human across the *entire* grounding range — the calibration test now asserts this worst case.
     delay/parts are unaffected and clear 0.7 comfortably. Priors live in `confidence.py` (per-reason,
     not an env knob); the five weights/threshold/normalizer remain env-tunable per OQ2.
  3. **No `LLM_PROVIDER` switch.** The ladder order is fixed (D2: Groq → Gemini → deterministic), so a
     "pick one provider" switch is meaningless. A provider is simply live when its key is set. This
     is simpler and matches the locked fallback design; `.env.example` documents it.
  Also: `needs_human` kept its 2-arg signature (its existing test is untouched); the risk-tier floor
  is a thin `needs_human_for` wrapper. Groq/Gemini SDK call shapes are written to best current
  knowledge but **verified only at the gated live call** (they import lazily, so nothing offline
  touches them).

- **2026-10-08 (LIVE-VERIFIED + deps installed + model drift)** — User approved the gated step.
  Added deps `groq>=0.11` (resolved 1.7.0) + `google-genai>=0.3` (resolved 2.29.0); `uv sync`.
  **All four live scenarios passed on the user's real keys:**
  - **Live Groq** (delay): `provider=groq`, self-rating 0.92, blended confidence **0.988**, real
    cited explanation.
  - **Live Gemini** (parts): `provider=gemini`, self 0.85, blended **0.9175**, real explanation.
  - **Forced 429 → fallback**: an injected Groq 429 + a *real* Gemini 503 (high demand) exercised
    the full ladder down to the deterministic floor — the rate-limit note survived end to end
    (`"AI rate-limited - used fallback. Full AI retry in ~7s."`), complex blended **0.67 (<0.7 →
    human)**, confirming the calibration tune live.
  - **All providers fail → deterministic**, `degraded=True`.
  - **Ladder refinement (code):** `degraded` + `rateLimitNote` now ride onto *whatever* rung
    answers (not only the deterministic floor), so a 429 on the primary is surfaced in the trace
    even when a fallback provider succeeds. +1 test (47 total).
  - **MODEL DRIFT — the locked model ids were gone from the free tiers.** Groq
    `llama-3.3-70b-versatile` → 404; Gemini `gemini-2.0-flash`/`gemini-2.5-flash` → 404/"no longer
    available". **New locked defaults (user-approved, verified live):** Groq **`openai/gpt-oss-120b`**
    (the plan's documented alt, strongest reasoning) and Gemini **`gemini-flash-latest`** (floating
    alias → no re-pinning as Google rotates versions). Updated in `config.py` defaults, `.env`, and
    `.env.example`. Lesson baked into the docs: **verify model availability per account** with the
    SDK's `.models.list()` — free-tier ids drift.
  - Windows note: live model output can contain non-ASCII (e.g. a non-breaking hyphen); the app
    stores/returns it fine as UTF-8 JSON, but a Windows cp1252 console `print` of it crashes — a
    display-only concern (set `PYTHONIOENCODING=utf-8` for scripts).

## Explanation

### 1. What changed
A new `app/llm/` package turns the mock proposer into a **real-LLM seam with a safety ladder**, and
replaces the single hard-coded confidence number with an **evidence-weighted score**:

- `app/llm/proposer.py` — the `Proposal` shape, the `Proposer` ladder (Groq → Gemini →
  deterministic), the deterministic fallback (the old mock), a shared prompt builder and a strict
  JSON→`Proposal` parser.
- `app/llm/groq.py`, `app/llm/gemini.py` — the two live providers (lazy-imported SDKs).
- `app/llm/confidence.py` — `confidence_factors()` + `score_confidence()` (one pure function + a
  weights blend).
- `app/policy/__init__.py` — a `needs_human_for()` wrapper adding the risk-tier hard floor.
- `app/graph/build.py` — `generate_options` calls the proposer; `policy_validate` blends the five
  factors into the final confidence and writes the full breakdown to the decision trace.
- `app/config.py` + `.env.example` — every LLM and confidence knob, env-driven.
- `tests/test_llm.py`, `tests/test_confidence.py` — the ladder/floor and the calibration contract.

### 2. Why it was needed
The decision loop needs a real brain (an LLM that reads the case + retrieved knowledge and proposes
recovery options), but an LLM is unreliable (rate-limits, outages) and *untrusted* (it can invent
options or sound falsely confident). So two guarantees had to be engineered, not hoped for: the loop
**never breaks** (a deterministic floor always answers), and the LLM **can't talk its way past the
human-approval gate** (confidence is mostly computed from checkable facts, and the LLM's slice is
clamped so it can only lower it).

### 3. How it works, step by step
1. `generate_options` calls `propose(reason, context, knowledgeSources)`. The ladder tries each live
   provider in order; the first to return valid JSON wins. Any error — or an HTTP 429 rate-limit —
   is caught and the ladder drops to the next rung. If all live providers fail (or none are
   configured), the **deterministic** proposer answers and the result is flagged `degraded`.
2. The returned options are **untrusted**. `policy_validate` runs the unchanged `validate_options`,
   which removes any illegal option and sets `policyResult` = APPROVED / PARTIAL / DENIED.
3. `policy_validate` then builds five normalized [0,1] factors — **prior** (reason difficulty),
   **headroom** (policyResult), **grounding** (`top_retrieval_score / 0.6`, capped at 1),
   **data** (fraction of key case fields present), **llm** (`min(self_rating, prior)` — the clamp) —
   and blends them: `confidence = Σ(factor × weight)`, clamped to [0,1].
4. The routing edge calls `needs_human_for(reason, confidence, policyResult, ALWAYS_HUMAN_REASONS)`:
   a human is required if the reason is on the hard floor (`safety_risk`, `warranty_dispute`) **or**
   confidence < 0.7 **or** policy is DENIED. Otherwise the card goes straight to the customer.
5. The decision trace carries `confidence`, the full `confidenceBreakdown` (factors + weights),
   the LLM's `explanation`, `llmProvider`, `degraded`, and any `rateLimitNote`.

### 4. Files / functions changed
- **`app/llm/confidence.py`** (new): `PRIOR`/`HEADROOM` maps; `confidence_factors(...)` normalizes
  raw signals (including the one-directional LLM clamp); `score_confidence(factors, weights)` →
  `(final, breakdown)`.
- **`app/llm/proposer.py`** (new): `Proposal` dataclass; `RateLimited` exception; `REASON_ARCHETYPE`
  + `SELF_RATING` (moved from the graph); `deterministic_proposal(...)`; `Proposer` (the ladder);
  `build_proposer(settings, providers=None)`; `build_prompt(...)`; `parse_proposal(...)`.
- **`app/llm/groq.py`** / **`app/llm/gemini.py`** (new): `groq_propose(...)` (JSON-object mode, 429 →
  `RateLimited`) and `gemini_propose(...)` (`response_schema`), both lazy-importing their SDK.
- **`app/policy/__init__.py`**: `needs_human` gains an optional `threshold`; new `needs_human_for`
  adds the `always_human` floor.
- **`app/graph/build.py`**: removed `_propose`/`REASON_ARCHETYPE`/`CONFIDENCE_BY_ARCHETYPE`;
  `build_graph(..., proposer=None)`; `generate_options` emits the proposal fields; `policy_validate`
  blends confidence + enriches the trace; the human-gate edge uses `needs_human_for`.
- **`app/main.py`**: builds `build_proposer(settings)` and injects it into the graph.
- **`app/config.py`** + **`.env.example`**: the LLM + confidence env surface.

### 5. Important decisions
- **Ladder with a deterministic floor** (not a cache of last-good replies): guarantees "never
  breaks" with zero extra state. A **cross-provider** fallback (Gemini, not a second Groq model) so
  a Groq-wide rate-limit still has an LLM option before the deterministic floor.
- **Evidence-weighted confidence** over a single LLM number: auditable and un-gameable. The three
  calibration guards — normalize (strong signal → full marks), prior dominates (0.40 weight), LLM
  clamp — keep good jobs auto-sending while complex/safety jobs escalate. (See Updates for the
  complex-prior tune that makes the escalation robust across all grounding.)
- **Risk-tiering** (OQ1): named high-risk reasons skip to a human regardless of score — how
  production systems tier safety/legal decisions.
- Rejected: LLM-only confidence (gameable), same-provider fallback (dies with Groq), a reply cache
  (YAGNI — the floor already guarantees availability).

### 6. Tests / verification
- `cd apps/orchestrator && uv run pytest -q` → **46 passed** (28 prior + 9 `test_confidence` +
  9 `test_llm`). `uv run ruff check .` → **All checks passed!**. `uv run python -c "import app.main"`
  → OK. All offline — the deterministic proposer is the default, no keys, no network.
- The calibration contract (`test_confidence.py`) pins routing: delay/parts-in-stock ≥ 0.7 (auto),
  complex < 0.7 even at grounding 1.0 and LLM self-rating 1.0 (human). The ladder tests
  (`test_llm.py`) prove order, bad-JSON fallthrough, the 429 note, and the hard floor.
- **Not run:** any live Groq/Gemini call (gated — needs your go + the two deps). The provider call
  shapes are therefore unverified against the live APIs.

### 7. Edge cases and limitations
- **Live provider code is unverified.** `groq.py`/`gemini.py` are written to current SDK knowledge
  but only exercised at the gated live call; the SDK surface may need a small fix then.
- **`PARTIAL` + zero grounding** can pull a `parts` recompute below 0.7 (→ human). In the fake store
  grounding is non-zero so the NFR-5 race test re-offers as expected; live grounding is higher, so
  this is safe — but it's a known sensitivity if weights are retuned.
- **Panel display** of `rateLimitNote`/`confidenceBreakdown` isn't wired yet (the trace carries
  them; the panel is Step 8).
- **Per-reason priors are code, not env** — only the five weights, threshold, grounding normalizer,
  and always-human list are env-tunable (per OQ2's listed surface).
