# Build Step 1 — Real policy engine + full LangGraph decision flow

**Status:** Ready to build · **Created:** 2026-10-07

> Goal of this step: make the brain actually **decide**, not echo a fake card. Still mock-first
> (FakeSalesforce / FakeVonage), still managed infra, still speed-first. North star is the whole
> system in the docs; this step builds the decision core and the decision-related failure modes.

## North star (what we're ultimately building)

Everything in the docs: the full **13-stage journey** (SRS §8), **all 6 failure modes** (SRS §9),
Salesforce/MCP, RAG, Groq/Gemini, commerce + Razorpay, Logfire god-eye tracing. This step is the
foundation the rest hangs off.

## In scope for Step 1

1. **Real Policy Engine** (`app/policy/`) — replace the pass-through stub. Deterministic checks on
   each proposed option: technician skill, territory, SLA window, working hours, customer
   entitlement, inventory-on-hand, price authority, current case state, idempotency. Returns
   `(valid_options, policy_result)` with reasons for what was removed. **The LLM never decides —
   this does.**
2. **Full LangGraph graph** (`app/graph/`) — grow from 2 nodes to the real flow:
   `load_case → load_context (customer/appointment/technician/asset/warranty/inventory) →
   evaluate_sla → generate_options → policy_validate →
   (auto-safe → execute) | (risky/low-confidence → human_approval interrupt) →
   offer_to_customer (interrupt, wait for reply) → resume_on_reply → verify → close`.
3. **Interrupt + resume** — use LangGraph's checkpointer (Postgres) so the graph pauses for the
   customer / human and resumes on the next event, durably.
4. **Decision-related failure modes:**
   - **NFR-4** low-confidence / risky → `human_approval` interrupt (Level 3).
   - **NFR-5** inventory changed between recommend and execute → atomic reserve fails → graph
     resumes → recomputes options → re-offers.
   - **NFR-6** customer replies against a stale case version → reject stale action → re-send
     current options (version the conversation state).
5. **Richer mocks** — FakeSalesforce returns enough for real option generation + a FakeInventory
   with mutable stock so NFR-5 can fire. FakeVonage records each outbound card/version.
6. **Decision trace** — persist the full `{decision, reason[], knowledgeSources[], toolsUsed[],
   confidence, policyResult}` to `ai_decisions` and attach to logs (Logfire later).

## Out of scope for Step 1 (later steps, keep seams clean)

Real MCP/Salesforce, RAG retrieval, Groq/Gemini call, commerce/Razorpay, Logfire wiring,
NFR-1 (RCS→SMS) and NFR-3 (Salesforce-down/DLQ — topology already exists), the rich panel.
Leave interfaces so these drop in without rework.

## Acceptance (self-checks, no infra)

Extend `pytest` (in-memory SQLite + fakes), all green:
- policy removes an option that fails a rule (e.g. wrong skill / outside SLA) and keeps valid ones;
- a low-confidence decision routes to `human_approval` and does **not** execute until approved;
- NFR-5: reserve fails when stock drops → graph recomputes and re-offers;
- NFR-6: a reply tagged with an old version is rejected and current options are re-sent;
- the existing idempotency + spine tests still pass.

Keep `ruff` clean. Keep the walking-skeleton run working (`/sim` → panel).

## Rules

Speed-first; mock-first; compact updates; **ask before any big context-doc rewrite**; don't let
the LLM mutate state. See [`CLAUDE.md`](../../../CLAUDE.md) and
[`context/02-orchestration-and-policy.md`](context/02-orchestration-and-policy.md).

## Plan (approved 2026-10-07)

**Approach.** The graph owns the *deciding* and the mockable side effects; the service layer owns
*durable state*. Nodes never touch the DB, so they stay pure and unit-testable.

**Graph shape built:**
```
load_case → load_context → evaluate_sla → generate_options → policy_validate
  policy_validate ─ auto-safe ───────▶ offer_to_customer
  policy_validate ─ risky/low-conf ──▶ human_approval (interrupt, NFR-4)
  human_approval  ─ approved ────────▶ offer_to_customer
  human_approval  ─ rejected ────────▶ close
offer_to_customer → await_reply (interrupt, wait for tap)
await_reply → execute
  execute ─ stale reply (NFR-6) ─────▶ offer_to_customer  (re-send current options)
  execute ─ reserve lost race (NFR-5)▶ generate_options   (recompute, re-offer)
  execute ─ ok ──────────────────────▶ verify → close
```

**Files touched:** `policy/__init__.py` (real engine), `graph/build.py` (full graph), new
`graph/checkpointer.py`, `services/case_service.py` (start + resume + shared persist),
`tools/salesforce.py` (+reschedule), `tools/inventory.py` (+atomic reserve, mutable stock),
`db/models.py` (Case.version + AiDecision), `api/routes.py` (version in view), `sim/routes.py`
(+/approve, +/customer-reply), `main.py` (build graph once), 2 new test files.

**Decisions / alternatives rejected:**
- **Checkpointer = InMemorySaver, not Postgres.** `langgraph-checkpoint-postgres` isn't installed
  and acceptance runs with no infra. InMemory gives real interrupt/resume in-process; restart
  durability is a one-dep swap behind `make_checkpointer()`. Rejected: adding the Postgres saver +
  a live DB just to satisfy the wording — breaks the no-infra self-checks.
- **Side effects in nodes, DB in the service.** Rejected keeping all effects in the service
  (graph would only compute) — the node-level `interrupt()`/`Command(goto)` flow is the natural
  LangGraph shape and keeps the service a thin driver.
- **`execute` exits only via `Command(goto=...)`.** A static `execute → verify` edge *plus* a
  `Command(goto)` double-fired and clashed on the `status` channel; all exits are dynamic now.
- **Low-confidence trigger = event reason `asset_complex` (0.5 < 0.7 threshold).** Tied to the
  domain, no synthetic flag. (Confirmed with the user.)
- **Policy checks only the keys a candidate declares** — a bare slot passes; a rich slot is held
  to every rule it names. Keeps the default path clean and the removal test precise.

## Tasks

- [x] Real policy engine: skill / SLA / working-hours / entitlement / inventory / state + reasons.
- [x] `needs_human()` confidence gate (NFR-4) lives in policy, not the LLM.
- [x] Full LangGraph flow with the two interrupts + resume via the checkpointer.
- [x] NFR-5 atomic reserve → recompute → re-offer.
- [x] NFR-6 stale-version reply → reject → re-send current options.
- [x] Richer `FakeSalesforce` + mutable-stock `FakeInventory` (reserve, set_stock).
- [x] Decision trace persisted to `ai_decisions` + attached to the Case + audit trail.
- [x] `/sim/approve` + `/sim/customer-reply` resume endpoints.
- [x] Tests: policy unit + NFR-4/5/6 + happy path; idempotency + spine stay green; ruff clean.

## Updates

- **2026-10-07** — Built Step 1. 10/10 pytest green (was 2/2; +8 covering policy, approval
  gating, NFR-5, NFR-6, happy path), ruff clean, `app.main` imports. Default `/sim` event still
  lands as a 2-option `OPTIONS_SENT` carousel, so the walking skeleton is unchanged. The live
  RabbitMQ hop is still verified manually (`make up` + curl), not by tests — same as the spine.

## Explanation

**1. What changed.** The brain now actually decides. The pass-through policy stub became a real
deterministic engine; the 2-node graph became the full recovery flow with two durable pauses (for
a human and for the customer) that resume on the next event; and three failure modes are handled.

**2. Why it was needed.** The spine only echoed a fixed card. Step 1 makes the system do the thing
the whole product is about: AI proposes, deterministic policy decides what's legal, a human
approves the risky calls, and the customer picks — surviving races and stale replies.

**3. How it works, step by step.**
- An `appointment.at_risk` event arrives (via `/sim` → RabbitMQ). `handle_event` dedupes it
  (idempotency) and invokes the graph with `thread_id = correlationId`.
- `load_context` pulls the fake Salesforce context; `evaluate_sla` computes breach/urgency;
  `generate_options` (the mock LLM seam) proposes candidate slots and a confidence, and snapshots
  current part stock into the context.
- `policy_validate` removes every illegal candidate (wrong skill, outside SLA, no stock, …) with a
  reason, and sets `APPROVED / PARTIAL / DENIED`. `needs_human()` then gates: confidence below 0.7
  **or** nothing legal to offer → `human_approval`, an **interrupt** that persists and waits.
- On approval (or when auto-safe) `offer_to_customer` sends the card via FakeVonage and bumps the
  case **version**; `await_reply` **interrupts** and waits for the tap.
- `execute` runs when the customer replies: a stale version is rejected and the current options are
  re-sent (NFR-6); otherwise it does an **atomic reserve** on any required part — if that lost the
  race it recomputes and re-offers (NFR-5) — then reschedules, verifies, and closes.
- `resume_case` feeds the human/customer decision back in via `Command(resume=...)`; the graph
  continues from its checkpoint. The service persists the Case, an audit row, and the decision
  trace after every step.

**4. Files / functions changed.**
- `app/policy/__init__.py` — `validate_options()` (per-rule removal with reasons, policyResult),
  `needs_human()` (the Level-3 gate), `_removal_reason()` (one rule-ordered check).
- `app/graph/build.py` — `build_graph(salesforce, vonage, inventory, *, checkpointer)` with 11
  nodes; `_propose()` is the mock LLM proposer; two `interrupt()`s and `Command(goto)` loop-backs.
- `app/graph/checkpointer.py` — `make_checkpointer()` (InMemorySaver; Postgres swap documented).
- `app/services/case_service.py` — `handle_event()` (start), `resume_case()` (resume), `_persist()`
  + `_case_status()` (one place that writes Case/audit/`ai_decisions`).
- `app/tools/salesforce.py` — `+reschedule()`, richer context (`caseState`).
- `app/tools/inventory.py` — mutable stock, `reserve()` (atomic), `set_stock()` (demo knob).
- `app/db/models.py` — `Case.version`, new `AiDecision` (the decision-trace table).
- `app/sim/routes.py` — `/approve`, `/customer-reply`. `app/main.py` — graph built once on
  startup. `app/api/routes.py` — `version` in the case view.

**5. Important decisions.** See *Decisions / alternatives rejected* above — the big ones are the
InMemory checkpointer (vs Postgres), effects-in-nodes/state-in-service, and `execute` exiting only
through `Command` to avoid a channel write-clash.

**6. Tests / verification.** `pytest apps/orchestrator/tests -q` → **10 passed**. New:
`test_policy.py` (removes wrong-skill/outside-SLA, DENIED when all invalid, the confidence gate),
`test_decision_flow.py` (NFR-4 gating + reject, NFR-5 race, NFR-6 stale reply, happy path to
CLOSED). Existing idempotency + spine e2e still green. `ruff check` → **All checks passed**.
`import app.main` → OK.

**7. Edge cases & limitations.** InMemory checkpointer loses paused cases on restart (Postgres
swap deferred). The LLM proposer, RAG, real Salesforce/MCP, Groq, commerce/Razorpay, Logfire, and
NFR-1/NFR-3 are later steps — seams left clean. The live RabbitMQ hop is still only manually
verified. `create_all` (no alembic) means the new `version` column / `ai_decisions` table need a
fresh dev DB. NFR-5 recompute reserves at the first location with stock (no multi-location
optimisation) and the mock proposer is deterministic, not a real model.
