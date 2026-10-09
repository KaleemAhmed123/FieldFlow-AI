# FieldFlow AI — Playbook

> **What this is:** the one-page "how to drive, demo, test, and extend this system" sheet — every
> command and prompt you'll reach for, with teaching comments. Keep it at root; update it as the
> build grows. Compact on purpose.
>
> **One idea the whole system serves:** *AI proposes, deterministic policy decides, a human
> approves risk; RCS (rich WhatsApp-style messaging) is the customer's control plane.*
>
> **How to read this playbook:** skim the headings — each numbered section is one job (setup,
> everyday commands, run the demo, per-feature how-tos, repo map, what's next, delegation, prompts).
> Code blocks are copy-paste-ready; the `# comments` above each command say what it does and why.
> You don't have to curl by hand — see the Swagger note in §2 to fire any endpoint from the browser.

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
>   When `DATABASE_URL` is Postgres, paused cases are now **restart-durable** — the LangGraph
>   checkpointer writes to Postgres (see note below). On SQLite/offline it stays in-memory.
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

### Durable checkpointer (paused cases survive a restart)

- The **checkpointer** = where a paused case's graph state lives so Approve/Reply/Pay can resume it.
- **Postgres** when `DATABASE_URL` is Postgres (Supabase) — survives a `uvicorn` restart. **In-memory**
  on SQLite/offline (lost on restart; fine for tests). One seam: `app/graph/checkpointer.py`.
- First real boot runs a one-time `.setup()` creating `checkpoints`, `checkpoint_blobs`,
  `checkpoint_writes`, `checkpoint_migrations` in Supabase (idempotent — safe to re-run).
- Deps: `langgraph-checkpoint-postgres`, `psycopg[binary]` (added via `uv`). **Windows:** the app
  sets `SelectorEventLoop` automatically (psycopg3 async can't use the default Windows loop).
- A resume with no saved state (checkpoint lost/expired) now returns **409**, not a 500.
- ponytail / later: no retention yet — prune closed-case checkpoints when volume grows.

Health check once `make dev` is up:

```bash
curl http://localhost:8000/health        # {"status":"ok"}  — cheap liveness, never hits the network
curl http://localhost:8000/tools         # the controlled tool surface (reads vs actions)  ← Step 2
curl http://localhost:8000/health/deps   # deep dep health (cheap: DB+queue only)           ← Step 10
curl "http://localhost:8000/health/deps?deep=1"  # + real vendor pings (groq/gemini models.list, jina HEAD)
```

> **`/health/deps` (Step 10)** — one call, every external dep's state. **Cheap by default:** only
> Postgres `SELECT 1` + the RabbitMQ connection check (our own infra) + config-present for the rest —
> **zero third-party API calls**, so the panel can poll it freely. **`?deep=1`** adds the real pings:
> groq/gemini `models.list()` (free, not a completion) and an unauthenticated jina HEAD (reachability
> only, never embeds — embedding is billable). Result is **cached 30s** (`HEALTH_DEPS_CACHE_TTL_S`), the
> route **never throws** (a dead dep is `"down"`, still HTTP 200) and **never returns keys**. Shape:
> `{"status":"ok|degraded|down","deep":false,"checks":{"postgres":{"status":"ok","latencyMs":12}, …}}`.
> `status` = worst-of the required deps (postgres, rabbitmq); groq/gemini/jina/logfire can only drop it to
> `degraded`; vonage (`armed`/`fake`) + razorpay (`test-mode`/`fake`) are informational.

> **Windows PowerShell:** use `curl.exe` (plain `curl` is an alias for a different command there).

> **You don't need curl — FastAPI ships Swagger UI.** With `make dev` up, open
> **http://localhost:8000/docs** in a browser: an interactive page listing every endpoint
> (`/sim/*`, `/cases`, `/tools`, …). Click one → "Try it out" → fill the JSON body → "Execute". It
> fires the exact same request as the curl lines below, no terminal needed. (`http://localhost:8000/redoc`
> is a read-only reference view of the same API.) The curl snippets in this playbook are just the
> copy-paste / scriptable form of those same calls.

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

## 3b. RAG / knowledge (build step 4)

*RAG = retrieve relevant passages from our docs before the AI reasons, so decisions are grounded
and cited.* Mock-first: unit tests use an in-memory store + a deterministic embedder (no keys). The
live store is Supabase pgvector + Jina embeddings + Jina reranker.

```bash
# (Re)generate the knowledge corpus from the product catalog (app/data/catalog.json — 14 models,
# all fake). Dense per-model service-manual PDFs + global warranty/SOP/troubleshooting/part-compat.
uv run python scripts/generate_corpus.py

# Ingest it into the configured store. Idempotent + incremental: re-running embeds only what
# changed (add 5 pages anywhere → only those 5 embed). Needs JINA_API_KEY + Supabase for the real
# store; falls back to the in-memory fake otherwise.
uv run python scripts/ingest_knowledge.py
```

- Corpus lives in `app/rag/corpus/`. The graph calls `retrieve_knowledge` after `load_context`;
  the retrieved passages appear as `knowledgeSources` in each case's decision trace (`/cases/{id}`).
- **The catalog (`app/data/catalog.json`) is the single source of truth** — it also seeds
  `FakeInventory` stock and the `FakeSalesforce` asset, and grounds the LLM proposer (so a delay
  proposes no part, and any part used is a real catalog part). Edit the catalog → re-run
  `generate_corpus.py` → `ingest_knowledge.py`.
- **Warm the RAG before a live demo:** the first live retrieval after a cold start is slow (~60s
  for the Jina embed+rerank over the corpus); fire one throwaway event first, then it's ~2–6s.
- Env: `JINA_API_KEY`, `JINA_MODEL`, `EMBEDDING_DIM`, `RETRIEVAL_K` (see `.env.example`).

## 3c. LLM proposer + evidence-weighted confidence (build step 5)

*The LLM only proposes; policy still decides; humans still approve risk.* The proposer runs a fixed
ladder — **Groq `openai/gpt-oss-120b` → Gemini `gemini-flash-latest` → deterministic** — and the
first that returns valid JSON wins. The deterministic rung never fails, so an LLM outage or
rate-limit can't take the decision loop down. **Live-verified 2026-10-08** on real keys (Groq +
Gemini + a real 503 falling through to deterministic with the rate-limit note intact).

> **Model ids drift on free tiers.** The originally-planned `llama-3.3-70b-versatile` and
> `gemini-2.5-flash` were both gone by 2026-10-08. If a live call 404s, list what your key actually
> serves: `uv run python -c "from app.config import settings; import groq; print([m.id for m in groq.Groq(api_key=settings.groq_api_key).models.list().data])"` (and the `genai` client's `.models.list()` for Gemini), then set `GROQ_MODEL`/`GEMINI_MODEL` in `.env`.

- **Mock-first / offline:** with **both** `GROQ_API_KEY` and `GEMINI_API_KEY` blank, the
  deterministic proposer runs — this is what the whole test suite uses (no network, no keys).
- **Confidence** is blended from five weighted factors (reason difficulty, policy headroom, RAG
  grounding, data completeness, the LLM's own clamped rating), shown in the trace as
  `confidenceBreakdown`. The LLM can only *lower* confidence, never inflate past the gate.
- **Risk-tiering:** `ALWAYS_HUMAN_REASONS` (default `safety_risk,warranty_dispute`) forces human
  review at ANY confidence. Everything else is score-gated at `CONF_THRESHOLD` (0.7).
- Env: `GROQ_API_KEY`, `GEMINI_API_KEY`, `GROQ_MODEL`, `GEMINI_MODEL`, `LLM_*` tuning, `CONF_W_*`
  weights, `CONF_THRESHOLD`, `CONF_GROUNDING_FULL`, `ALWAYS_HUMAN_REASONS` (see `.env.example`).

```bash
# Prove the ladder + confidence offline (no keys needed) — these run in CI:
uv run pytest -q tests/test_llm.py tests/test_confidence.py

# LIVE (keys in .env + deps installed): fire an at-risk event (§3), read /cases/{id} — the trace's
# llmProvider says "groq"/"gemini"/"deterministic", degraded/rateLimitNote flag any fallback, and
# confidenceBreakdown carries the five factors. On Windows, prefix PYTHONIOENCODING=utf-8 for any
# script that prints raw model text (it can contain non-ASCII).
```

> **Deps are installed** (`groq`, `google-genai`). `make install` runs plain `uv sync`, which prunes
> the dev extras — use `uv sync --extra dev` to get `pytest`/`ruff` back before `make test`.

## 3d. Commerce: quote → Approve & Pay → capture (build step 6)

*When a repair needs paid work (a part not covered by warranty), the customer approves + pays over
RCS via a Razorpay page, then we capture and confirm.* Mock-first: `FakeRazorpay` behind a
`PaymentGateway` seam (blank `RAZORPAY_KEY_*` → the fake, offline). Money is integer **paise**.

**The one rule for money:** the LLM proposes *which part*; the **price book** (`app/commerce/
service.py`) decides the **amount**. Every money step (quote/order/payment/refund) is an action tool
that runs the ladder and may refuse. **No double-charge** is guaranteed twice: idempotent capture at
the gateway (keyed by paymentId) + envelope dedupe on the payment `eventId`.

**What makes a job chargeable:** the chosen option needs a part AND (asset out of warranty OR
`reason == additional_fault_found`). Two ways to demo it:

```bash
# A) reason-driven: a newly-found fault is outside warranty scope → chargeable on the default appt.
curl -X POST http://localhost:8000/sim/appointment-at-risk \
  -H "Content-Type: application/json" \
  -d '{"workOrderId":"WO-PAY","reason":"additional_fault_found"}'

# B) warranty-driven: fire against the out-of-warranty appointment SA-OOW (asset warranty expired).
curl -X POST http://localhost:8000/sim/appointment-at-risk \
  -H "Content-Type: application/json" \
  -d '{"workOrderId":"WO-PAY","appointmentId":"SA-OOW","reason":"part_missing"}'

# Customer picks the part-fit slot (the usual reply). Case → PAYMENT_PENDING, a "payment" card with
# a payUrl is "sent" (the Razorpay Open-URL).
curl -X POST http://localhost:8000/sim/customer-reply \
  -H "Content-Type: application/json" \
  -d '{"correlationId":"WO-PAY","slotId":"t-part-1","version":1}'

# The customer completes payment — a normal /sim step, like /sim/customer-reply (no webhooks in the
# POC). status=captured → case CLOSED.
#   eventId is the no-double-charge key: fire the SAME eventId twice → charged ONCE (2nd = duplicate).
curl -X POST http://localhost:8000/sim/payment \
  -H "Content-Type: application/json" \
  -d '{"correlationId":"WO-PAY","paymentId":"pay_demo","status":"captured","eventId":"evt-pay-1"}'

curl http://localhost:8000/cases/WO-PAY   # decisionTrace.commerce = {quote, order, payment}
```

- **High-value gate:** a quote ≥ `COMMERCE_HIGH_VALUE_PAISE` (default ₹5,000) pauses at
  `AWAITING_QUOTE_APPROVAL` for an operator — resume with the **existing** `/sim/approve`.
- Env: `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` (blank → fake), `COMMERCE_CURRENCY`,
  `COMMERCE_LABOUR_PAISE`, `COMMERCE_HIGH_VALUE_PAISE` (see `.env.example`).

```bash
# Prove the commerce flow + no-double-charge offline (no keys needed) — runs in CI:
uv run pytest -q tests/test_commerce.py
```

**Going live (real Razorpay Test-Mode — Step 9):** the gateway is built behind the seam. Set a
`rzp_test_…` key pair in `.env` and `build_gateway` swaps `FakeRazorpay` → the real `RazorpayGateway`
automatically (a non-test key aborts the boot — Test-Mode only). The real path creates a real payment
link (`short_url`), and `/sim/payment` **polls** Razorpay (`payment_link.fetch`) to confirm the real
`paid` status — still no webhook. The `razorpay` dep + the one live payment are the only remaining
gated bits:

```bash
uv add razorpay          # only when you run the live fire (not needed for any test)
# then set RAZORPAY_KEY_ID=rzp_test_... + RAZORPAY_KEY_SECRET=... in .env, run the §3d flow,
# open the real short_url, pay with test card 4111 1111 1111 1111, fire /sim/payment, see it CLOSED.
```

## 3e. Vonage RCS: real send + real inbound/status webhooks (build step 9b)

*The customer gets the reschedule options as a real RCS **carousel** on their Android, taps a slot,
and the tap comes back to us as a real **webhook** that resumes the case.* Mock-first:
`FakeVonage` is the default; `build_vonage` only swaps in the real client when the send is **armed**.
`/sim/*` stays the offline twin, so all tests run with no device and no creds.

**The two secrets (different jobs):**
- **Send** uses a **short-lived JWT (RS256)** signed with the application's **private key** —
  `VONAGE_APPLICATION_ID` + `VONAGE_PRIVATE_KEY_PATH`. RCS senders are tied to an application, so
  Basic auth (`api_key:api_secret`) **cannot** authenticate an RCS send — it returns `422`.
- **Inbound webhooks** are verified with the **`VONAGE_SIGNATURE_SECRET`** (dashboard → Settings) —
  a JWT signed HMAC-SHA256; we check it with Python stdlib, no extra dependency.

**Arming the real send (safe by default):** real send fires **only** when *all* of
`VONAGE_APPLICATION_ID` + `VONAGE_PRIVATE_KEY_PATH` + `VONAGE_RCS_AGENT_ID` + `VONAGE_TEST_TO` are
set. Creds can sit in `.env` during offline dev without a billed send ever firing — you arm it by
setting `VONAGE_TEST_TO` (digits only, **no `+`**) right before a demo. **$100 credit: one send per
manual demo, never in a loop or a test.**

**The postback trick:** each slot's button carries a hidden string
`postback_data = "correlationId|slotId|version"`. Vonage echoes it back on the inbound webhook, so
`/webhooks/inbound` alone knows which case, which slot, and which offer version (NFR-6 stale guard)
— no phone-number lookup.

### Set up the dev tunnel + webhooks (junior-friendly)

```bash
# 1. Expose localhost:8000 to the internet (Vonage must reach your webhooks).
ngrok http 8000
#    → copy the https URL it prints, e.g. https://ab12cd34.ngrok-free.app

# 2. Vonage dashboard → Applications → your app → Capabilities → Messages:
#    Inbound URL  = https://<ngrok>/webhooks/inbound     (POST)
#    Status  URL  = https://<ngrok>/webhooks/status      (POST)
#    Save. (The ngrok URL changes each restart on the free plan — re-paste it when it does.)

# 3. Dashboard → Settings → copy the Signature secret → VONAGE_SIGNATURE_SECRET in .env.
```

> **Status: live pipeline verified 2026-10-09.** The full AI path (RAG → proposer → policy → card)
> fires live; the send auth was switched from Basic to **JWT** (the fix for the `422`). A real card
> delivering to a device needs the RCS agent far enough along (test-device sends work without full
> brand launch).

### The gated live demo (needs creds + your go + a test Android)

```bash
# Deps are already in pyproject: pyjwt[crypto] (JWT signing) + httpx. Nothing to add.
# In .env (digits only on the number, NO +):
#   VONAGE_APPLICATION_ID=<app id>
#   VONAGE_PRIVATE_KEY_PATH=app/resources/private.key
#   VONAGE_RCS_AGENT_ID=astrea_it
#   VONAGE_TEST_TO=916394493446
#
# Start the app — on WINDOWS you MUST use --reload (uvicorn only sets the SelectorEventLoop that
# psycopg3 needs when it runs with a reload subprocess; a plain run crashes on the ProactorEventLoop):
#   uv run uvicorn app.main:app --reload --port 8000
#
# Fire with a REAL seeded appointment id — SA-19281 (or SA-OOW). Made-up ids crash load_context
# (FakeSalesforce returns None). The first RAG retrieval is ~60s cold; warm it with one throwaway.
curl -X POST http://localhost:8000/sim/appointment-at-risk -H "Content-Type: application/json" \
  -d '{"workOrderId":"WO-LIVE","appointmentId":"SA-19281","reason":"technician_delay","delayMinutes":50,"eventId":"evt-live-1"}'
# → a real RCS carousel lands on the phone. Tap a slot → Vonage POSTs /webhooks/inbound → the case
#   advances exactly like /sim/customer-reply. /webhooks/status callbacks land in the audit trail.
curl http://localhost:8000/cases/WO-LIVE   # the tap moved it past OPTIONS_SENT
```

```bash
# Offline (no device, no creds) — the full send→tap→resume contract + signature verify, runs in CI:
uv run pytest -q tests/test_vonage.py
```

**Live-fire learnings (verified end-to-end on a real device 2026-10-09).** The checklist that
actually gets a card delivered and the tap back — each was a real blocker we hit, in order:

| Symptom | Cause | Fix |
|---|---|---|
| `422` on send | Basic auth | **JWT** (app id + `private.key`); `VONAGE_APPLICATION_ID` + `VONAGE_PRIVATE_KEY_PATH` |
| `422 media_url / media_height required` | carousel cards need an image | set `media_url` + `media_height` on every card (done in `card_to_rcs`) |
| `422 rcs.card_width required` | carousel needs card width | top-level `rcs.card_width` (done) |
| `202` but **no card on phone** | number not an allow-listed **test device** | add the number as a test device on the agent; `to` is **digits only, no `+`** |
| card arrives, **tap never resumes** | Inbound URL not set on the **application** | set Inbound+Status URL on the app (`VONAGE_APPLICATION_ID`), not the agent builder |
| image area blank | Google RBM fetches/validates media itself | cosmetic — swap `CARD_MEDIA_BASE` for a hosted branded image; flow is unaffected |
| server crashes on boot (Windows) | psycopg3 + ProactorEventLoop | run with `uvicorn --reload` (selector loop only set under the reload subprocess) |

Golden rule we re-learned: **make the failure loud (log the response body + traceback) and read it
before guessing.** Every 422 above named the exact next field.

## 3f. Failure demos: RCS→SMS fallback + Salesforce-down/DLQ (build step 7)

*Two "things break, we degrade gracefully" demos.* Offline for tests; the DLQ land+replay needs
RabbitMQ (`make up` or CloudAMQP).

**7a — RCS→SMS fallback.** If the RCS card doesn't deliver, the same options go out as a plain SMS.

```bash
# Fire an at-risk event (§3) → options "sent" (OPTIONS_SENT). Then simulate a failed delivery:
curl -X POST http://localhost:8000/sim/delivery-status \
  -H "Content-Type: application/json" \
  -d '{"messageUuid":"<the card's messageUuid>","status":"failed"}'
# → the system sends the options as SMS (FakeVonage records it; real Vonage sends channel=sms).
#   An sms_fallback audit row is written; the customer still replies with a slotId as usual.
```

> Offline the FakeVonage card has no `messageUuid`; the **real** send (§3e) returns one. For a pure
> offline check, `test_failures.py` sets it and asserts the SMS fires only on failed + awaiting.

**7b — Salesforce-down → DLQ → replay.** A dependency outage parks the event safely, not lost.

```bash
# 1. Knock Salesforce "down" (no restart):
curl -X POST http://localhost:8000/sim/fault -H "Content-Type: application/json" -d '{"salesforceDown":true}'
# 2. Fire an at-risk event (§3) → processing fails → the message dead-letters to events.dlq.
# 3. See what's parked (read-only):
curl http://localhost:8000/dlq          # {available, depth, messages:[...]}
# 4. Bring Salesforce back:
curl -X POST http://localhost:8000/sim/fault -H "Content-Type: application/json" -d '{"salesforceDown":false}'
# 5. Replay the parked messages → they process normally:
curl -X POST http://localhost:8000/sim/dlq/replay   # {"replayed": N}
```

```bash
# Prove both offline (no RabbitMQ needed; the DLQ land+replay itself is the manual demo above):
uv run pytest -q tests/test_failures.py
```

## 4. Scenario → where it's proven

| Scenario | What it shows | How to see it today |
|----------|---------------|---------------------|
| Happy path | at-risk → options → tap → closed | `make dev` + §3 curl |
| Idempotency (NFR-2) | same event twice = one case | §3, same `eventId` twice |
| Human approval (NFR-4) | low confidence pauses for a human | live: `reason:"asset_complex"` + `/sim/approve` · or `make test` |
| Inventory race (NFR-5) | part taken → atomic reserve refuses → re-offer | live: `reason:"part_missing"` · or `make test` |
| Stale reply (NFR-6) | old version tap rejected → re-sent | `make test` → `test_decision_flow.py` |
| Tool refusal (Step 2) | action tool says no, with a reason | `make test` → `test_tools.py` |
| Commerce (Step 6) | chargeable repair → quote → Approve & Pay → capture → close | §3d · or `make test` → `test_commerce.py` |
| No double-charge (Step 6) | same payment fired twice charges once | §3d, same `eventId` twice · or `test_commerce.py` |
| Vonage RCS (Step 9b) | real carousel send + tap webhook + signature verify + dedup | §3e · or `make test` → `test_vonage.py` |
| RCS→SMS fallback (Step 7) | card undelivered → same options over SMS | §3f · or `make test` → `test_failures.py` |
| Salesforce-down/DLQ (Step 7) | outage → event parks in DLQ → replay on recovery | §3f (needs RabbitMQ) · or `test_failures.py` |

> **New to the code? Learn it by testing.** [`docs/specs/field-service-recovery/testing-guide.md`](docs/specs/field-service-recovery/testing-guide.md)
> maps every existing test to the promise it guards, and lists 10 scoped tests to add. Good first tasks.

---

## 5. Repo map (where to look)

```
apps/orchestrator/app/
  graph/build.py        the LangGraph flow (the decision core). Calls tools ONLY via the Toolbox.
  policy/__init__.py    the deterministic authority: validate_options() + needs_human() gate.
  rag/                  RAG: store (fake + pgvector), split, ingest, embed. retrieve_knowledge node.
  rag/corpus/           generated synthetic manuals/warranty/SOP/part-compat (all fake).
  tools/registry.py     the Toolbox (Step 2): read/action kinds, call(), describe(), build_toolbox().
  tools/salesforce.py   FakeSalesforce — granular reads + reschedule (swap for real MCP at step 9).
  tools/inventory.py    FakeInventory — find_part (read) + atomic reserve (action), mutable stock.
  tools/vonage.py       FakeVonage + real VonageMessagesClient (Step 9b) + card_to_rcs + build_vonage.
  webhooks/routes.py    /webhooks/inbound + /webhooks/status (Step 9b): JWT verify, dedup, resume.
  services/case_service.py  durable state: idempotency + Case row + audit + decision trace.
  api/routes.py         /cases, /cases/{id}, /tools, /health, /health/deps (Step 10), /metrics.
  health.py             check_deps() — deep dep-health for /health/deps (concurrent, cached, no leaks).
  sim/routes.py         /sim/* — fire events / resume a paused case (the offline twin of /webhooks/*).
  main.py               builds the fakes + Toolbox + graph once on startup; runs the consumer.
packages/contract/      shared Pydantic event/type models (one source of truth both sides validate).
docs/specs/field-service-recovery/   the specs + living context docs. START at context/00-overview.md.
```

---

## 6. Build status & what's next

Done: **Spine** → **Step 1** (policy + graph + NFR-4/5/6) → **Step 2** (Toolbox / MCP surface) →
**§3** (10 reasons / 3 archetypes) → **Step 4** (RAG, **live-verified** 2026-10-08) →
**Step 5** (LLM proposer ladder + evidence-weighted confidence, **shipped + LIVE-VERIFIED**
2026-10-08: real Groq `openai/gpt-oss-120b` + Gemini `gemini-flash-latest` + fallback proven) →
**Step 6** (commerce + Razorpay, **shipped mock-first** 2026-10-08: quote → Approve & Pay → capture,
price-book authority, two-layer no-double-charge) →
**Step 9 Razorpay** (real `RazorpayGateway` + poll-confirm + test-key guard **built + offline-tested**
2026-10-08; only the one live Test-Mode fire is gated) →
**Step 9b Vonage RCS** (real `VonageMessagesClient` send + `/webhooks/inbound` + `/webhooks/status`
with stdlib JWT verify + `message_uuid` dedup, **built + offline-tested** 2026-10-08, **65 green**;
only the one live send to a real Android is gated — see §3e) →
**Step 7 Failure demos** (RCS→SMS fallback + Salesforce-down/DLQ peek/replay, **built + offline-tested**
2026-10-08, **70 green**; the DLQ land+replay is a manual RabbitMQ demo — see §3f).
Next: **9b live fire** (arm `VONAGE_TEST_TO` + the two webhook URLs) · **9c** real
Salesforce MCP ([`salesforce-handoff.md`](docs/specs/field-service-recovery/salesforce-handoff.md)) ·
**7** failure demos · **8** panel + dashboards.

> **Webhook scope:** Razorpay payment = `/sim/payment` **poll** (no Razorpay webhook). **Vonage RCS
> inbound (taps) + status = real webhooks** (9b). `/sim/*` stays as the offline twin for tests/demos.

Full detail per step: `docs/specs/field-service-recovery/build-step-*.md`.

---

## 7. Delegation map (you're the tech lead)

- **Give to a junior (boring, scoped, reversible):** create free-tier accounts (Supabase,
  CloudAMQP, Razorpay test, Logfire), fill `.env`, run the panel, add the `reason` knob in §3,
  seed/fixture data, docs tidy-ups.
- **Keep for yourself / coordinate:** Salesforce DE org + access (the big dependency — start early;
  the offload sheet is [`docs/specs/field-service-recovery/salesforce-handoff.md`](docs/specs/field-service-recovery/salesforce-handoff.md)),
  Vonage (access + $100 credit received 2026-10-08 — spend sensibly), architecture calls, policy
  rules, anything irreversible or security-sensitive.

---

## 8. Prompts to continue with Claude

Paste these to drive the next pieces. House rules: **plan first, wait for go**, plain-English
teaching, mock-first, and I'll always surface what you must set up.

**Continue after Step 10 (panel + realistic data both shipped) — the current front door**
```
Continue FieldFlow. Working dir C:\Users\hp\Desktop\RCS-VONAGE-POC. Read in order: CLAUDE.md (HARD
rules: plain teaching style, plan-first, WAIT for my go on open questions, surface my action items +
junior delegation, end every reply with What I achieved / What I need from you / Next steps; playbook.md
is the command home; spec-driven under docs/specs/field-service-recovery/); handoff-fieldflow.md
(LATEST = session 6, read first); build-step-8.md + build-step-10-realistic-domain-data.md (both
SHIPPED); playbook.md §9 (run the panel) + §3b (catalog + RAG).

State: backend Steps 1–7, 9 (Razorpay), 9b (Vonage) built + offline-green; Step 8 React control panel
SHIPPED (dark+light, decision-trace hero, polling behind a useLiveCases SSE seam); Step 10 "realistic
domain data" SHIPPED + LIVE-VERIFIED — a 14-model catalog (app/data/catalog.json) seeds inventory +
the Salesforce asset + a dense PDF RAG corpus and grounds the proposer (delay → no part, enforced).
From apps/orchestrator: `uv run pytest -q` → 72 passed, `uv run ruff check .` clean,
`uv run python -c "import app.main"` OK (dev deps: `uv sync --extra dev`). Panel: cd apps/control-panel
&& pnpm install && pnpm dev (set VITE_USE_FIXTURES=true for offline). KEEP apps/control-panel/pnpm-workspace.yaml
(esbuild allowlist) or pnpm install errors. The one story: AI proposes → deterministic policy decides →
a human approves risk → RCS is the customer control plane; the decision trace is the hero.

Open / not done: (1) NOTHING is committed yet — Step 8 (12 commit cmds) + Step 10 (8 commit cmds) are
in my session notes; (2) a PARALLEL "Step 10 — dependency-health endpoint" (app/health.py,
tests/test_health_deps.py, build-step-10.md, edits to api/routes.py+config.py+broker.py) is in the tree
— STEP-NUMBER COLLISION, decide a renumber; (3) live-demo warm-up: the first Jina retrieval is ~60s
cold, warm it with one throwaway fire; (4) gated real integrations — Vonage live RCS send (needs VONAGE
creds + ngrok + the 2 webhook URLs + a test Android; code armed behind VONAGE_TEST_TO, $100 credit —
one send per demo) and Salesforce real MCP/Apex (needs a Field Service Developer Edition org — see
salesforce-handoff.md); (5) optional panel model-picker + more FakeSalesforce appointments so partners
can fire the other 13 catalog models.

Ask me which to do next: commit · resolve the step-10 collision · Vonage live · Salesforce MCP · panel
model-picker. Then plan-first (restate the task, list open questions with your recommendation, and WAIT
for my go), mock-first, keep the 72 tests green, update playbook.md + the step's Explanation in the same
change. Do NOT fire a billed Vonage send, run a live demo, or edit my apps/orchestrator/.env without my
explicit go (disarm Vonage/Razorpay via process env for any dry run).
```

**Build Step 9b (real Vonage RCS — send + real webhooks) — the NEXT step, plan already written**
```
Continue FieldFlow. Working dir C:\Users\hp\Desktop\RCS-VONAGE-POC. Read in order: CLAUDE.md (hard
rules: plain teaching style, plan-first, WAIT for my go on every open question, surface my action
items + junior delegation, end every reply with What I achieved / What I need from you / Next steps;
playbook.md is the command home; spec-driven under docs/specs/field-service-recovery/);
handoff-fieldflow.md (LATEST block first — session 4); build-step-9b.md (THE plan for this step);
build-step-9.md (Razorpay, the sibling swap); playbook.md §3c/§3d/§6.

State: Spine + Steps 1,2,§3,4,5,6 shipped; Step 9 Razorpay gateway BUILT + offline-tested (real
RazorpayGateway + poll-confirm + test-key guard; only the one live Test-Mode fire is gated). Run from
apps/orchestrator: `uv run pytest -q` → 58 passed; `uv run ruff check .` clean; dev deps via
`uv sync --extra dev`. The one rule holds everywhere: AI proposes, deterministic policy decides,
humans approve risk, tools act and may refuse.

Task = Step 9b: swap FakeVonage → real Vonage Messages API over RCS — real SEND (carousel of slot
options; "Approve & Pay" open-url card) AND REAL inbound + status WEBHOOKS. The webhook decision is
corrected: "no webhooks" was Razorpay-only (Razorpay stays a /sim/payment poll); Vonage webhooks ARE
built here and must be robust (JWT signature verify, dedup inbound by message_uuid, return 200) — the
partners will see this. Keep /sim/* as the offline twin so all 58 tests stay green on FakeVonage.

House rules for this step: PLAN FIRST — the plan already exists in build-step-9b.md (sections 1-5 +
open questions OQ1-OQ5 with my recommendations). Restate it, confirm/adjust the OQs with me, and WAIT
for my explicit go before editing code. Mock-first: build VonageMessagesClient + build_vonage factory
(fake unless creds set) + the Card→RCS payload mapping + /webhooks/inbound + /webhooks/status with
signed-fixture unit tests FIRST (offline, 58 stay green). The ONE live send to a real Android device
is gated on my go + creds. My action items: I'll add VONAGE_API_KEY, VONAGE_API_SECRET,
VONAGE_APPLICATION_ID, the private key, VONAGE_RCS_SENDER to .env ("soon"), plus an ngrok tunnel +
the two webhook URLs on the Vonage Application + a test Android (Google Messages) number. $100 credit
— spend sensibly (one send per manual demo, never in a loop/test). Update playbook.md + build-step-9b
Explanation in the same change when we ship. Ask before editing any context/** doc beyond the
already-approved webhook-scope note.
```

**Resume Step 8 (control panel) — foundation already built, GREEN checkpoint**
```
Continue FieldFlow. Working dir C:\Users\hp\Desktop\RCS-VONAGE-POC. Read in order: CLAUDE.md (HARD
rules: plain teaching style, plan-first, WAIT for my go on open questions, surface my action items +
junior delegation, end every reply with What I achieved / What I need from you / Next steps);
docs/specs/field-service-recovery/handoff-fieldflow.md (LATEST = session 5); build-step-8.md (THE
plan — §3 answered OQs, §4 Plan, §5 Tasks + the Resume notes); playbook.md §9 (how to run the panel).

State: Step 8 foundation is built and GREEN. From apps/control-panel: `pnpm install` then
`pnpm typecheck` + `pnpm build` pass; `pnpm run types` regenerates the contract types. Done: pnpm
deps, token-driven theme (dark default + light, one CSS-var block), fonts, `@/` alias, lib/cn.ts, and
the GENERATED contract.gen.ts. KEEP apps/control-panel/pnpm-workspace.yaml (esbuild build-script
allowlist) or pnpm install errors. The old App.tsx + api.ts are still the live app — don't delete
until the new shell lands.

Task = finish Step 8 per build-step-8.md §5 (tasks 2-8), the house aesthetic is a dark minimalist
"hacker vibe", comprehensive + component-rich (do NOT ponytail components away; ponytail still governs
clean code). Build order: finish the data layer (api.ts for every endpoint, hand-typed trace.ts for
the decision-trace shape in the Resume notes, metrics.ts, fixtures.ts + VITE_USE_FIXTURES flag,
TanStack Query hooks + useLiveCases polling seam, QueryClient in main.tsx) → shadcn ui/ primitives +
Layout shell → CaseList + the HERO CaseDetail decision trace (reason[], knowledgeSources[],
toolsUsed[], confidenceBreakdown, policyResult, removed[]) + RcsCardPreview + StatusTimeline →
ApprovalActions (/sim/approve) → FailureDeck + ToolsSurface → MetricsStrip. Endpoints + the one story
(AI proposes → policy decides → human approves risk → RCS is the control plane) are in build-step-8 +
handoff. Keep the backend's 70 tests green (don't touch backend; SSE stays deferred). Update
playbook.md §9 + the build-step-8 §7 Explanation when it ships.
```

**Build Step 8 (control panel — the demo UI partners will see) — plan-first**
```
Continue FieldFlow. Working dir C:\Users\hp\Desktop\RCS-VONAGE-POC. Read in order: CLAUDE.md (HARD
rules: plain teaching style, plan-first, WAIT for my go on every open question, surface my action
items + junior delegation, end every reply with What I achieved / What I need from you / Next steps;
playbook.md is the command home; spec-driven under docs/specs/field-service-recovery/ — write
build-step-8.md sections 1-5 before any code); docs/specs/field-service-recovery/handoff-fieldflow.md
(LATEST block first); scaffold.md §2 (target repo layout) + §6 (build order #8 = "Control panel
richness + Grafana dashboards"); playbook.md §2/§3/§3e/§3f/§5 (every endpoint + demo flow).

State: the BACKEND is done and fully offline-green — from apps/orchestrator: `uv run pytest -q` → 70
passed, `uv run ruff check .` clean, `uv run python -c "import app.main"` OK (dev deps:
`uv sync --extra dev`). Steps shipped: Spine, 1 (policy+graph+NFR-4/5/6), 2 (Toolbox/MCP surface), §3
(reasons/archetypes), 4 (RAG), 5 (LLM proposer + evidence-weighted confidence), 6 (commerce+Razorpay),
9 Razorpay gateway, 9b Vonage send+webhooks, 7 failure demos. The ONE story the UI must make obvious:
**AI proposes → deterministic policy decides → a human approves risk → RCS is the customer control
plane.** The decision trace ("show your work": reason[], knowledgeSources[], toolsUsed[], confidence
breakdown, policyResult, removed[]) is the HERO of the panel.

Task = Step 8: build the React control panel in apps/control-panel/ (React + Vite + TS per scaffold
§2; today the panel POLLS the API). I want it COMPREHENSIVE, component-rich and PREMIUM, with a
minimalist "hacker vibe" aesthetic (dark, terminal/monospace accents, restrained palette, crisp
density, subtle motion) — this is what we demo to the Vonage partners, so use all the design skills
(frontend-design, ui-ux-pro-max, minimalist-ui, enterprise-ux for the dense operator layout, shadcn
for components, dataviz for the metrics/confidence charts, advanced-frontend-architecture for state/
data-fetching). Richness here is DELIBERATE — do NOT ponytail components away; ponytail still governs
clean code, no dead abstractions. Views to cover (confirm scope with me): a live case list + a case
detail with the full decision trace, the RCS card preview (carousel + "Approve & Pay"), the human-
approval and quote-approval actions, the live SLA/status timeline, the /tools surface (reads vs
actions), a failure-demo control deck (fire at-risk by reason, customer-reply, payment,
delivery-status→SMS fallback, fault toggle, DLQ peek + replay), and a metrics strip from /metrics.

Endpoints to consume (all live now): GET /cases, GET /cases/{id} (status, version, context,
decisionTrace, sentCard), GET /tools, GET /dlq, GET /metrics (Prometheus text), GET /health; POST
/sim/appointment-at-risk (reason knob), /sim/customer-reply, /sim/approve, /sim/payment,
/sim/delivery-status, /sim/fault, /sim/dlq/replay. CORS origin is http://localhost:5173. Types come
from packages/contract (generate/mirror TS types from the Pydantic models — don't hand-duplicate).

House rules for this step: PLAN FIRST. Restate the task, then raise the open questions and WAIT for my
answers before any code — at minimum: (1) component approach (shadcn/Tailwind vs hand-rolled); (2)
live-feel (keep polling vs add SSE/WebSocket) — backend is poll today; (3) v1 view scope (which of the
above ship first); (4) is Grafana in scope for Step 8 or deferred (a metrics strip in-panel may be
enough for the demo); (5) mock fixtures vs live backend during UI dev. Give your recommendation for
each. Keep the backend's 70 tests green (don't change backend behavior just to suit the UI without
telling me). Surface my action items (node/pnpm versions, running the panel + the API together, any
design assets/brand). Spec-driven: write docs/specs/field-service-recovery/build-step-8.md (sections
1-5) alongside, update playbook.md (how to run the panel) in the same change, and add the
Explanation when it ships.
```

**Start the next build step**
```
Continue FieldFlow. Read CLAUDE.md + docs/specs/field-service-recovery/context/00-overview.md +
scaffold.md (build order). Plan Step <N> from scaffold §6: restate the task, list open questions
with your recommendations, and wait for my go before editing. Mock-first; keep every test green.
```

**Build Step 5 (Groq LLM) — decisions already locked**
```
Continue FieldFlow. Working dir C:\Users\hp\Desktop\RCS-VONAGE-POC. Read in order: CLAUDE.md (hard
rules: plain teaching style, plan-first, wait for my go, surface my action items + junior delegation,
end with What I achieved / What I need from you / Next steps, playbook.md is the command home);
docs/specs/field-service-recovery/handoff-fieldflow.md (LATEST block first); build-step-5.md (the full
Step 5 plan + locked decisions); build-step-4.md; testing-guide.md; playbook.md.

State: Spine + Step 1 + Step 2 + §3 + Step 4 (RAG, LIVE-VERIFIED) are shipped and green
(cd apps/orchestrator && uv run pytest -q → 28 passed; uv run ruff check . clean). Step 5 is DECIDED,
not built: Groq llama-3.3-70b-versatile proposer; fallback ladder Groq → Gemini gemini-2.5-flash →
deterministic; evidence-weighted confidence (5 weighted factors, LLM clamped so it can only lower not
inflate, calibration test locks delay/parts→auto & complex→human); add deps groq + google-genai.
GROQ_API_KEY + GEMINI_API_KEY already in .env (gitignored).

OQ1–OQ5 are already ANSWERED in build-step-5.md (OQ1 = risk-tiering: calibrated score PLUS a hard
ALWAYS_HUMAN_REASONS floor for safety_risk/warranty_dispute; OQ2 = all LLM + confidence knobs in .env;
OQ3 native JSON mode; OQ4 temp 0.2; OQ5 approved to update context/02+06 after ship). Implement Step 5
MOCK-FIRST in the task order there: config/deps → confidence.py + test_confidence.py → risk-tier floor
in needs_human → proposer seam + deterministic fallback → groq.py → gemini.py → wire into
generate_options → test_llm.py. Keep the 28 tests green with a fake proposer (offline). Do NOT run a
live Groq call or add deps until I give the go. Follow plan-first + explain-and-wait. Update
playbook.md + build-step-5.md Explanation in the same change.
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

---

## 9. Run the control panel (Step 8 — shipped)

*The React + Vite + TypeScript operator UI the Vonage partners see — a dense, dark-by-default
(light-capable) console whose hero is the AI decision trace. Build with **pnpm**. Full write-up:
[`docs/specs/field-service-recovery/build-step-8.md`](docs/specs/field-service-recovery/build-step-8.md).*

```bash
cd apps/control-panel
pnpm install            # first time. KEEP pnpm-workspace.yaml — it allowlists esbuild's build
                        # script; without it pnpm errors ERR_PNPM_IGNORED_BUILDS and Vite won't run.
pnpm dev                # Vite dev server on http://localhost:5173 (backend CORS already allows it)
pnpm typecheck          # tsc --noEmit — should be clean
pnpm build              # production build (tsc -b && vite build)
pnpm run types          # regenerate TS types from packages/contract/schema/*.json (after make schema)
```

- **Run the panel + the API together:** `make dev` (orchestrator on :8000; needs a queue for the
  `/sim/*` demos — CloudAMQP in `.env` or `make up`) **and** `pnpm dev` here (panel on :5173). Point
  the panel elsewhere with `VITE_API_URL` in `apps/control-panel/.env`.
- **No backend needed for UI work:** set `VITE_USE_FIXTURES=true` (e.g. in `.env.local`) and the
  panel serves an in-memory twin — every view (incl. paused/approval/commerce/failure) renders and
  the ops-deck buttons work, with no backend and no queue. Unset it for the real demo.
- **Theme:** dark by default, light is a full peer; the whole palette is CSS-variable tokens in
  `src/index.css` (Tailwind maps semantic names in `tailwind.config.js`). Re-skin = edit that one
  block. A persisted dark/light toggle lands with the shell.
- `make panel` (repo root) is the shortcut for `pnpm dev` in this folder.
