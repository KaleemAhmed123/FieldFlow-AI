# FieldFlow AI — Playbook

> **What this is:** the one-page "how to drive, demo, test, and extend this system" sheet — every
> command and prompt you'll reach for, with teaching comments. Keep it at root; update it as the
> build grows. Compact on purpose.
>
> **One idea the whole system serves:** *AI proposes, deterministic policy decides, a human
> approves risk; RCS (rich WhatsApp-style messaging) is the customer's control plane.*

---

## 0. The mental model (read once)

- **RCS** = rich messaging to the customer (the cards with "pick a slot"). Mocked by `FakeVonage`.
- **MCP** = the standard way an AI app calls tools/data (think USB for AI tools). Our orchestrator
  is the **MCP client**; Salesforce + e-com will be **MCP servers**. Today a local **Toolbox**
  stands in for the network — same shape, fakes behind it.
- **The authority ladder** — every change (mutation) climbs it, no exceptions:
  ```
  LEVEL 1 DETERMINISTIC  can this legally/technically happen? (policy + the action tool's checks)
  LEVEL 2 AI             what's best? how to explain it? (only runs if Level 1 allowed it)
  LEVEL 3 HUMAN          approve a risky / low-confidence call (graph pauses and waits)
  ```
- **Two stores:** Salesforce = truth about the *business* (customer, asset, stock). Our Postgres =
  truth about the *case* (what we asked, what we decided, what we already did). Don't mix them.

---

## 1. One-time setup

```bash
make install          # uv sync — installs the Python workspace (orchestrator + contract pkg)
```

- **uv** = the Python package manager/runner we use (fast, single tool). `uv run <cmd>` runs inside
  the project's venv without activating anything.
- **No `.env` needed to run tests.** Tests spin up their own in-memory SQLite + fakes — zero infra.
- **A real run** reads `apps/orchestrator/.env` (copy from `.env.example`). Defaults if absent:
  SQLite file for the DB (fine, no infra) + `localhost` RabbitMQ (won't exist → publish path is
  disabled, everything else works).

> **When you'll be asked for infra (I'll highlight it at the time):**
> - **DB (Supabase Postgres + pgvector):** needed for RAG (step 4) and durable multi-process runs.
> - **Queue (CloudAMQP, or `make up` for local RabbitMQ):** needed to fire events over HTTP (§3).
> - **Groq key:** step 5 (real LLM). **Razorpay test keys:** step 6. **Salesforce org + Vonage:**
>   step 9.

---

## 2. Everyday commands

```bash
make test             # uv run pytest -q   → the fast truth. No infra. Should be all green.
make lint             # uv run ruff check . → style/lint gate. Should say "All checks passed!"
make dev              # run the orchestrator (FastAPI + the queue consumer) on :8000
make panel            # run the React control panel (Vite) on :5173
make schema           # export the contract JSON Schema (frontend types) — after editing events/types
make up / make down   # start/stop local infra via Docker (only if you don't use managed tiers)
```

Health check once `make dev` is up:

```bash
curl http://localhost:8000/health        # {"status":"ok"}
curl http://localhost:8000/tools         # the controlled tool surface (reads vs actions)  ← Step 2
```

> **Windows PowerShell:** use `curl.exe` (plain `curl` is an alias for a different command there).

---

## 3. Run the live demo (end to end)

**Needs a queue** (CloudAMQP URL in `.env`, or `make up`), because events travel
`/sim → RabbitMQ → consumer → graph`. The DB can stay the default SQLite file.

```bash
# 1) Fire an at-risk appointment (a real Salesforce Pub/Sub event, simulated).
#    correlationId = workOrderId = the case key that threads everything.
#    reason picks the scenario (10 accepted; 3 drive distinct behaviour — see the table below).
curl -X POST http://localhost:8000/sim/appointment-at-risk \
  -H "Content-Type: application/json" \
  -d '{"workOrderId":"WO-10281","appointmentId":"SA-19281","reason":"technician_delay","delayMinutes":50}'

#    Fire the other two headline scenarios by changing reason:
#      "asset_complex"  → low confidence → pauses for human approval (NFR-4) → then /sim/approve
#      "part_missing"   → needs a scarce part → inventory race on reply (NFR-5)
#    Cosmetic variety that inherits an archetype: traffic_weather, technician_no_show,
#    customer_access_issue (delay) · wrong_part_shipped, additional_fault_found (parts) ·
#    safety_risk, warranty_dispute (complex).

# 2) See the case appear — status OPTIONS_SENT, a "sent" card, the decision trace with REAL toolsUsed.
curl http://localhost:8000/cases
curl http://localhost:8000/cases/WO-10281

# 3) The customer taps a slot. version MUST match the version they were shown (stale = rejected, NFR-6).
curl -X POST http://localhost:8000/sim/customer-reply \
  -H "Content-Type: application/json" \
  -d '{"correlationId":"WO-10281","slotId":"t-today-1","version":1}'

# 4) Case is now CLOSED. Re-check:
curl http://localhost:8000/cases/WO-10281

# Idempotency demo: re-POST step 1 with the SAME eventId → still ONE case, ONE card.
#   add  "eventId":"evt-demo-1"  to the step-1 body and fire it twice.
```

Human-approval path (operator taps approve) — used when a case pauses at Level 3:

```bash
curl -X POST http://localhost:8000/sim/approve \
  -H "Content-Type: application/json" \
  -d '{"correlationId":"WO-10281","approved":true}'
```

> **All three scenarios are firable live** (since the §3 reasons change): set `reason` in the
> step-1 body. `asset_complex` pauses for approval — resume it with `/sim/approve`. `part_missing`
> runs the inventory race on the customer reply. The other seven reasons are cosmetic variety that
> inherit one of the three archetypes (delay / parts / complex).

---

## 4. Scenario → where it's proven

| Scenario | What it shows | How to see it today |
|----------|---------------|---------------------|
| Happy path | at-risk → options → tap → closed | `make dev` + §3 curl |
| Idempotency (NFR-2) | same event twice = one case | §3, same `eventId` twice |
| Human approval (NFR-4) | low confidence pauses for a human | live: `reason:"asset_complex"` + `/sim/approve` · or `make test` |
| Inventory race (NFR-5) | part taken → atomic reserve refuses → re-offer | live: `reason:"part_missing"` · or `make test` |
| Stale reply (NFR-6) | old version tap rejected → re-sent | `make test` → `test_decision_flow.py` |
| Tool refusal (Step 2) | action tool says no, with a reason | `make test` → `test_tools.py` |

---

## 5. Repo map (where to look)

```
apps/orchestrator/app/
  graph/build.py        the LangGraph flow (the decision core). Calls tools ONLY via the Toolbox.
  policy/__init__.py    the deterministic authority: validate_options() + needs_human() gate.
  tools/registry.py     the Toolbox (Step 2): read/action kinds, call(), describe(), build_toolbox().
  tools/salesforce.py   FakeSalesforce — granular reads + reschedule (swap for real MCP at step 9).
  tools/inventory.py    FakeInventory — find_part (read) + atomic reserve (action), mutable stock.
  tools/vonage.py       FakeVonage — records the RCS card it "would send".
  services/case_service.py  durable state: idempotency + Case row + audit + decision trace.
  api/routes.py         /cases, /cases/{id}, /tools, /health, /metrics (what the panel reads).
  sim/routes.py         /sim/* — fire events / resume a paused case (stands in for real webhooks).
  main.py               builds the fakes + Toolbox + graph once on startup; runs the consumer.
packages/contract/      shared Pydantic event/type models (one source of truth both sides validate).
docs/specs/field-service-recovery/   the specs + living context docs. START at context/00-overview.md.
```

---

## 6. Build status & what's next

Done: **Spine** → **Step 1** (policy + graph + NFR-4/5/6) → **Step 2** (Toolbox / MCP surface).
Next: **4** RAG (pgvector) · **5** Groq LLM · **6** commerce + Razorpay · **7** failure demos ·
**8** panel + dashboards · **9** swap mocks → real Vonage + real Salesforce MCP.

Full detail per step: `docs/specs/field-service-recovery/build-step-*.md`.

---

## 7. Delegation map (you're the tech lead)

- **Give to a junior (boring, scoped, reversible):** create free-tier accounts (Supabase,
  CloudAMQP, Razorpay test, Logfire), fill `.env`, run the panel, add the `reason` knob in §3,
  seed/fixture data, docs tidy-ups.
- **Keep for yourself / coordinate:** Salesforce DE org + access (the big dependency — start early),
  architecture calls, policy rules, anything irreversible or security-sensitive.

---

## 8. Prompts to continue with Claude

Paste these to drive the next pieces. House rules: **plan first, wait for go**, plain-English
teaching, mock-first, and I'll always surface what you must set up.

**Start the next build step**
```
Continue FieldFlow. Read CLAUDE.md + docs/specs/field-service-recovery/context/00-overview.md +
scaffold.md (build order). Plan Step <N> from scaffold §6: restate the task, list open questions
with your recommendations, and wait for my go before editing. Mock-first; keep every test green.
```

**Demo the reason variants over HTTP (the §3 gap)**
```
Small task: add `reason` (technician_delay|part_missing|asset_complex) + optional part knob to
AtRiskRequest in app/sim/routes.py so I can fire NFR-4 and NFR-5 from the panel/curl. Keep make_event
the source of defaults. Add one test. Trivial — do it now, then show me the new curl.
```

**Set up the real database (Supabase)**
```
Walk me through wiring a real Supabase Postgres: which connection string, enable pgvector, what goes
in apps/orchestrator/.env, and how to verify the app boots against it. Tell me exactly what I do vs
what you do. Don't touch code until the env is confirmed.
```

**Status check anytime**
```
Where do we stand? What's built vs fake, is anything live (DB/queue/keys), and what's the next step
+ what you need from me. Compact.
```

**Review before shipping a step**
```
Run make test and make lint, show the real output, then give the post-implementation walkthrough
(what changed, why, how it flows, files, decisions, verification, edge cases).
```
