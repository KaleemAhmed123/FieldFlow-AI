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
curl http://localhost:8000/version       # {"commit","shortCommit","branch"} — is the LIVE deploy current?
curl http://localhost:8000/tools         # the controlled tool surface (reads vs actions)  ← Step 2
curl http://localhost:8000/health/deps   # deep dep health (cheap: DB+queue only)           ← Step 10
curl "http://localhost:8000/health/deps?deep=1"  # + real vendor pings (groq/gemini models.list, jina HEAD)
curl "http://localhost:8000/reconcile?older_than_minutes=30"  # Step 12: non-terminal cases stuck >30m (read-only)
```

> **Logfire (god-eye view, Step 12):** wired in `main.py` — set `LOGFIRE_TOKEN` in `.env` and every
> FastAPI request streams to your Logfire project. No token → no-op (tests/offline unaffected). Live
> Hosted-MCP setup (for the admin copilot) is in
> [`docs/specs/field-service-recovery/hosted-mcp-setup.md`](docs/specs/field-service-recovery/hosted-mcp-setup.md).

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

**The one rule for money:** the LLM proposes *which part*; the **price** decides the **amount** — from
the **e-com inventory** (`GET /api/stock/{partNo}` → `pricePaise`), falling back to the in-code price
book (`app/commerce/service.py`) when the e-com doesn't know the part. The quote's `priceAuthority`
records which one (`ecom` / `price_book`). Every money step (quote/order/payment/refund) is an action
tool that runs the ladder and may refuse. **No double-charge** is guaranteed twice: idempotent capture at
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
- **Auto-confirm (real Razorpay only):** with a real test key set, a background sweep
  (`app/payment_poller.py`, every `RAZORPAY_POLL_SECONDS`=10s) polls each `PAYMENT_PENDING` link and
  resumes the case the moment it's paid — so on a live deploy the customer just pays on their phone,
  no `/sim/payment` needed. A link unpaid past `RAZORPAY_PAYMENT_TTL_SECONDS` (default 180s / 3 min)
  is marked `PAYMENT_EXPIRED` and the sweep stops polling it. `/sim/payment` stays as a manual
  override; the fake gateway never polls (offline/tests use `/sim/payment`).
- Env: `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` (blank → fake), `RAZORPAY_POLL_SECONDS`,
  `RAZORPAY_PAYMENT_TTL_SECONDS`, `COMMERCE_CURRENCY`, `COMMERCE_LABOUR_PAISE`,
  `COMMERCE_HIGH_VALUE_PAISE` (see `.env.example`).

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

**The private key on Render (it's gitignored, so it isn't in the deploy):** the `.key` file is a
secret — never committed — so on Render the relative `app/resources/private.key` path doesn't exist
and boot logs `vonage.private_key_unreadable` (harmless: it falls back to FakeVonage, but real send
auth is impossible). Fix with **Render Secret Files** (no code change — the seam just `read_text()`s
whatever path you give it):
1. Render → the service → **Environment** → **Secret Files** → **Add Secret File**.
2. Filename `vonage_private.key`; paste the full PEM (`-----BEGIN PRIVATE KEY-----` … block) from your
   local `app/resources/private.key`.
3. It mounts at **`/etc/secrets/vonage_private.key`** → set env var
   `VONAGE_PRIVATE_KEY_PATH=/etc/secrets/vonage_private.key` → Save → Render redeploys, key readable.
Setting the key alone fires nothing — the send still arms only when `VONAGE_TEST_TO` is also set.

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
| image area blank | Google RBM fetches/validates media itself and won't render a **dynamic** URL (placehold.co?text=…) | **FIXED** — `_card_media` now returns a **static** image `https://field-flow-ai.vercel.app/card.png` (file `apps/ecom/public/card.png`); static, no query string. Needs an e-com + orchestrator redeploy. Per-model images = A2 (later) |
| `422 Invalid suggestion \`action\`` (#1020) on the rich-RCS **text** + **payment** card | our action chips used `type:"action"` (+ a `share_location:true` flag), which RCS rejects | **FIXED** (2026-10-13) — `actions_to_suggestions` now emits only the valid flat chip types `reply`/`dial`/`open_url`/`share_location`; payment chip is `open_url`. `dial` needs **E.164** (`+`+digits, no dashes — `_e164()` strips them) **and** a `fallback_url`. calendar/photo have no POC-formable flat chip → panel-only, omitted from the real send |
| `POST /webhooks/status` → **500** loop (Vonage retries) | the handler read `to` as `{"number":…}`, but RCS sends `to` as a **plain string** | **FIXED** (2026-10-13) — `status_recipient()` accepts a string or a dict |
| tap / approve → **500**, case stuck | a confirmation (no slots) or an all-removed offer became an **empty carousel** (#1020 "must have ≥2 cards") | **FIXED** (2026-10-13) — no-option cards are **standalone cards** (`card_to_rcs`); policy drops a skill-slot only when the tech's skills are **known**, so a missing technician no longer empties the offer; the confirmation send is best-effort |
| `card.media_url` / `card.text` / `card.suggestions[0].description` **"is required"** 422 on the **payment** (and confirmation) card | per Vonage's schema, **every** RCS card needs `title` + `text` + `media_url` + `media_height`; a standalone `card` also needs an **`rcs` object** (`image_alignment` + `card_orientation`); an **`open_url`** suggestion needs a `description`. Our payment card had none → 422 → 500 on the parts/pay tap | **FIXED** (2026-10-13) — `_rich_card()` builds payment + confirmation to the full schema (image + text + rcs + described open_url); offer action chips (Share Location / Call) moved **onto the carousel cards** as buttons |
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

> **Failed events are now VISIBLE (not just a silent DLQ entry).** If the graph crashes mid-pipeline
> (e.g. a live Vonage RCS send 422s), `handle_event` writes a **`FAILED` case** whose `decisionTrace`
> carries `{error, errorType}`, then **re-raises** so the message still dead-letters for replay. So a
> broken live fire shows up at `GET /cases/{id}` and in the panel with the exact error — no need to
> read the server logs. A successful replay upserts the same case to its real status. This is why a
> `part_missing` live fire that used to vanish now lands as `FAILED` with the reason attached.

## 3g. Salesforce trigger: the flow started by a real SF event (build step 9c)

*Today `/sim/appointment-at-risk` fires the case. In production a real Salesforce **Platform Event**
(`Appointment_At_Risk__e`) over the **Pub/Sub API** fires it. The subscriber publishes the SAME
contract event onto the SAME RabbitMQ exchange — consumer, graph, policy, RCS downstream never
change.* Mock-first: the seam + payload mapper are built + tested; `/sim` stays the offline twin.

```bash
# Prove the mapper + the armed/unarmed gate offline (no org, no deps) — runs in CI:
uv run pytest -q tests/test_event_source.py
```

- **Arming (gated, needs the org):** the trigger is a **separate opt-in** from the reads (step 12,
  OQ1). Set `SF_LOGIN_URL` + `SF_CLIENT_ID` + `SF_CLIENT_SECRET` **and** `SF_PUBSUB_ENABLED=true` →
  `sf_pubsub_armed`. The 3 creds alone only arm the **REST reads** (§3h), never this trigger.
- The real gRPC subscription body is the **gated live step** — it needs the provisioned Field
  Service org + the `Appointment_At_Risk__e` Platform Event + the pubsub deps. Enabling it before
  that raises a clear "gated live step" error (fails loud by design).
- Setup lives in [`docs/specs/field-service-recovery/salesforce-handoff.md`](docs/specs/field-service-recovery/salesforce-handoff.md);
  the step write-up is [`build-step-9c-salesforce-trigger.md`](docs/specs/field-service-recovery/build-step-9c-salesforce-trigger.md).

### 3g-b. The LIVE trigger we actually use: an Apex record trigger → HTTP callout (in progress)

*Instead of the heavy gRPC subscriber above, a record-triggered Apex trigger on `ServiceAppointment`
does an `@future` HTTP callout to the orchestrator when the appointment is marked at-risk. No ngrok —
the orchestrator is already public on Render. Spec:
[`salesforce-trigger-and-rich-rcs.md`](docs/specs/field-service-recovery/salesforce-trigger-and-rich-rcs.md).*

```bash
# BUILT (step 1): the receiving endpoint — maps the SF payload → publishes to the same exchange.
uv run pytest -q tests/test_sf_hook.py        # 4 green (secret-gate, maps+publishes, 400 on bad)
# Fire it by hand (what the Apex trigger will do) — blank SF_HOOK_SECRET offline = no header needed:
curl -X POST http://localhost:8000/webhooks/sf/at-risk -H "Content-Type: application/json" \
  -d '{"WorkOrderId__c":"WO-10281","AppointmentId__c":"SA-19281","Reason__c":"technician_delay","DelayMinutes__c":50}'

# BUILT (step 2): deploy Salesforce Apex + fields via the Tooling API (no sf CLI, reuses SF_* creds).
uv run python apps/salesforce-apex/deploy_sf.py --self-check    # offline parsing check
uv run python apps/salesforce-apex/deploy_sf.py --fields        # create At_Risk__c + reason + delay
uv run python apps/salesforce-apex/deploy_sf.py \
  apps/salesforce-apex/FieldFlowAtRisk.cls \
  apps/salesforce-apex/ServiceAppointmentAtRisk.trigger \
  apps/salesforce-apex/FieldFlowAtRiskTest.cls                  # step 3 — the trigger/classes (TBD)
```

- **Secret:** the Apex sends `X-FieldFlow-Secret`; the endpoint checks it against `SF_HOOK_SECRET`
  (blank → skipped, offline/dev). Set it on Render **and** in the SF Named Credential before going live.
- **Still TODO (step 3):** the Apex trigger + class + test files, a `FieldFlow` Named Credential
  (URL + secret header), then tick `At_Risk__c` on a seeded appointment for the first live fire.

### 3g-c. Rich RCS messages (Phase 2)

*The customer card is no longer a bare slot list. Each case now reads as a full story:*

- **AI message body** — a warm, reason-aware note written by the LLM (deterministic fallback), shown
  above the slots. Real send leads with it as an RCS text, then the carousel.
- **Action chips** — every offer carries **Share Location** + **Call technician**; a **parts** offer
  also invites a **photo of the unit label** (the inbound-image primitive).
- **Confirmation card** — on success the customer gets an archetype-aware confirmation with **Add to
  Calendar**, **Call**, and a **Service report (PDF)** link (SRS FR-13b).
- **Photo (parts) demo** — after a parts case is OPTIONS_SENT, simulate the customer sending a label
  photo; simulated OCR confirms the model and writes `photoVerified` onto the decision trace:

```bash
curl -X POST http://localhost:8000/sim/photo -H "Content-Type: application/json" \
  -d '{"correlationId":"WO-10281"}'   # → trace.photoVerified = {model, matchesAsset, source}
```

> **Simulated-but-labelled:** the photo OCR, the technician ETA behind Share Location, and the PDF
> report are POC stand-ins (marked as such in the trace); the RCS primitives themselves are real. The
> panel renders the body, the chips (with icons), the confirmation, and the photo/report in the trace.

## 3h. Salesforce reads + reschedule: the real org via Apex REST (build step 12)

*`RestSalesforce` calls the Apex class in `apps/salesforce-apex/` with the SAME 3 `SF_*` creds. Blank
→ `FakeSalesforce` (offline default). Set the 3 creds → the **reads** go live (safe); the
**reschedule** write also needs the Apex class deployed. Not MCP — the deterministic path.*

```bash
# 1) FIRST create the custom field (the class won't COMPILE without it): Setup -> Object Manager ->
#    Asset -> Fields & Relationships -> New -> Checkbox -> label "Warranty Active" (-> Warranty_Active__c).
# 2) DEPLOY the Apex class (pick one):
#    A) Developer Console: Setup gear -> Developer Console -> File > New > Apex Class "FieldFlowRest"
#       -> paste apps/salesforce-apex/FieldFlowRest.cls -> File > Save.  (NB: do step 1 first.)
#    B) sf CLI: sf project deploy start --source-dir apps/salesforce-apex --target-org <alias>
#    Then grant the integration user API Enabled + Apex-class access (apps/salesforce-apex/README.md §3).
# 3) SEED rich demo data (reuses the .env SF_* creds; idempotent; catalog-driven). Creates 28 cases
#    = all 14 models x in/out warranty, 10 customers, 6 technicians, and PRINTS A FIRE MENU
#    (AppointmentNumber -> model -> warranty -> suggested reason). --clean removes the demo chain.
uv run --with simple-salesforce python apps/salesforce-apex/seed_demo_data.py          # SA-0003..SA-0030
uv run --with simple-salesforce python apps/salesforce-apex/seed_demo_data.py --clean  # reset
# 4) ARM the reads: put the 3 SF_* creds (+ SF_TIMEZONE) in apps/orchestrator/.env, restart the app.
#    Smoke-test a read with the curl in apps/salesforce-apex/README.md §5.
```

> **Rich demo cases (after the seed).** 28 appointments span every appliance (AC, fridge, washer,
> microwave, water-purifier, …). Fire any from the menu — the live LLM proposes **model-specific**
> parts grounded in that model's manual (RAG) with live stock from the e-com: fridge → `FANE-410`/
> `COMP-410`, AC → `PCB-492`, microwave → `HVT-28`. Reasons cover all archetypes (delay / parts /
> complex) + the paid-repair path. RAG (live pgvector, 209 chunks) + e-com (86 parts) already cover
> all 14 models, so everything connects. (Earlier live fires drain some e-com stock — re-run the
> e-com `pnpm seed` or use the dashboard **Set** to reset before a demo.)

- Live calls are **untested against a real org** until you deploy + seed. The seed script fails loud
  with Salesforce's exact error (usually a missing field/permission) — paste it back and we adjust.
- Write-up: [`build-step-12-real-mcp-and-observability.md`](docs/specs/field-service-recovery/build-step-12-real-mcp-and-observability.md) §7.

### Payment write-back → FieldFlow_Payment__c (spec: `docs/specs/sf-payment-object.md`)

*A captured Razorpay payment is now written to Salesforce as a `FieldFlow_Payment__c` record linked
to the ServiceAppointment. One POST endpoint on the SAME Apex class, idempotent (upsert on the
Razorpay paymentId). `deploy_sf.py` uses the `SF_*` creds — no `sf` CLI, no new deps.*

```bash
# From the repo root, with SF_* creds in apps/orchestrator/.env:
# 1) create the object + its 7 fields (Metadata API for the object, Tooling API for the fields):
uv run python apps/salesforce-apex/deploy_sf.py --payment
# 2) redeploy the Apex class (now compiles — it references the new object):
uv run python apps/salesforce-apex/deploy_sf.py apps/salesforce-apex/FieldFlowRest.cls
# 3) grant the integration user FLS on the new object/fields (else the write 500s "inaccessible"):
uv run python apps/salesforce-apex/deploy_sf.py --payment-perms
# 4) smoke-test the live endpoint (get $TOKEN as in README §5):
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://<yourdomain>.my.salesforce.com/services/apexrest/fieldflow/payment" \
  -d '{"paymentId":"pay_demo1","paymentRef":"plink_x","orderId":"ord_x","amountPaise":370000,"currency":"INR","status":"captured","appointmentId":"SA-0003"}'
# → {"paymentId":"pay_demo1","status":"RECORDED","recordId":"a0X..."}  (same paymentId again = same row)
```

- **Live-verified 2026-10-21** in `astreait88-dev-ed`: object + 7 fields + the updated `FieldFlowRest`
  class deployed, FLS granted via the dedicated `FieldFlow_Payment_Access` permission set, and a POST
  round-trip confirmed (record created + linked to SA-0001; repeat = same row, idempotent).
  NB: the profile has Modify All Data, so `--payment-perms` uses a dedicated permission set (it can't
  add object perms to a MAD profile).
- In the pipeline this fires automatically in `settle_payment` (graph) via the `salesforce.record_payment`
  tool — best-effort (money is already captured, so a SF write hiccup never strands the paid case).

### Real availability slots → Field Service GetSlots (spec: `docs/specs/availability-slots.md`)

*The customer's reschedule options are now **real bookable times** from Field Service's own scheduler
(`FSL.AppointmentBookingService.GetSlots`), not canned ones. One GET endpoint on the SAME Apex class.
The orchestrator shows **2 per RCS card** + a **"See other times"** pager; it books the exact instant.
Blank ids or no openings → **falls back to canned slots** (`slotsAuthority: "fallback"` on the trace),
so it never dead-ends. Orchestrator side built + tested (129 pass); the Apex is a draft you deploy.*

```bash
# From the repo root, with SF_* creds in apps/orchestrator/.env:
# 1) redeploy the Apex class (now has the /slots route):
uv run python apps/salesforce-apex/deploy_sf.py apps/salesforce-apex/FieldFlowRest.cls
# 2) get the two org ids:  Developer Console -> Query Editor:
#      SELECT Id, Name FROM FSL__Scheduling_Policy__c      -> the "Customer First" Id (a0p...)
#      (Operating Hours Id is on the OperatingHours record used by your territories, 0OH...)
# 3) set them for the orchestrator (apps/orchestrator/.env AND Render env), restart:
#      SF_SCHEDULING_POLICY_ID=a0p...   SF_OPERATING_HOURS_ID=0OH...   (SF_SLOTS_MAX=6 optional)
# 4) make sure demo appts have a Service Territory + a rolling arrival window (seed now sets a
#    90-day window: EarliestStartTime=now, DueDate=now+90d — re-seed to refresh).
# 5) smoke-test the live endpoint (get $TOKEN as in README §5):
curl -H "Authorization: Bearer $TOKEN" \
  "https://<yourdomain>.my.salesforce.com/services/apexrest/fieldflow/slots/SA-0070?policyId=<POLICY_ID>&operatingHoursId=<OH_ID>&max=6"
# → [{"start":"2026-..Z","end":"2026-..Z","grade":85.0}, ...]   ([] = no window/availability; see step 4)
```

- Org ids already captured for `astreait88-dev-ed`: **Operating Hours** `0OHdM000005WIlLWAW` (Base
  Calendar, Asia/Kolkata), **Scheduling Policy** `a0pdM000001SsT7QAK`.
- In the pipeline this fires in `generate_options` via the `scheduling.slots` read tool. The AI still
  decides the **part + message**; only the **times** come from the scheduler.

## 3j. Admin copilot: Salesforce Hosted MCP (build step 12 Task 4)

*The AGENTIC path (separate from the deterministic Apex REST §3h). Salesforce HOSTS the MCP server;
we build the client. Custom Apex tools + admin-based auth. Mock-first built; live needs the ECA +
server + a one-time login.*

```bash
# USER (Salesforce UI), once — see docs/specs/field-service-recovery/hosted-mcp-setup.md:
#  1. Tools: 8 classes in apps/salesforce-apex/copilot/ — ALREADY DEPLOYED + compile-verified via the
#     Tooling API (one @InvocableMethod PER class — Salesforce allows only one). Nothing to paste.
#  2. Setup -> MCP Servers -> New -> Add Tools -> To Apex actions -> add the 8 FFCopilot_* actions -> Activate -> copy URL.
#  3. Create a NEW External Client App (ECA): OAuth2 + PKCE, scopes incl. mcp_api + refresh_token,
#     callback http://localhost:8000/oauth/callback -> copy Consumer Key + Secret.
#  4. Put SF_MCP_SERVER_URL + SF_MCP_CLIENT_ID + SF_MCP_CLIENT_SECRET in apps/orchestrator/.env.
# ONE-TIME login (mints the refresh token; OAuth2+PKCE, no headless grant):
cd apps/orchestrator && uv run python -m app.mcp.login     # prints SF_MCP_REFRESH_TOKEN -> paste into .env
# SEE the live tools the copilot can discover:
curl http://localhost:8000/copilot/tools                   # unarmed -> {"available": false, ...}
```

- Code: `apps/orchestrator/app/mcp/` (`client.py` + `login.py`) · route `GET /copilot/tools` ·
  tools `apps/salesforce-apex/copilot/FFCopilot_*.cls` (8, read-only, deployed + data-verified vs the
  seeded org). Mock-first tests: `tests/test_mcp_client.py`.
- The 8 tools: appointment health · needing attention · customer appointments · technician schedule ·
  asset history · unassigned · out-of-warranty · status counts.
- Guardrail: copilot tools are **read-only**; any write stays human-confirmed.

## 3k. Admin copilot CHAT: Groq tool-calling over MCP (build step 14)

*The agentic chat that uses the MCP tools from §3j. Admin asks in plain English → **Groq** picks
tools → we run them over the live SF (8) + e-com (2) MCP servers → a grounded answer + `toolsUsed`
(a mini decision-trace). READ-ONLY (the copilot never mutates). Groq-only this slice; single-turn.*

```bash
# Where it lives: the control panel's right dock → "Copilot" tab (type a question, or tap a starter).
# API (curl): needs the live backend + GROQ_API_KEY + at least one armed MCP source.
curl -s -X POST http://localhost:8000/copilot/chat -H 'content-type: application/json' \
     -d '{"message":"How many appointments are in each status?"}' | jq
#   -> {"available":true,"answer":"...","toolsUsed":[{"name":"...","args":{...},"result":"..."}]}
# e-com question (works the moment ECOM_API_URL is set — no SF needed):
curl -s -X POST http://localhost:8000/copilot/chat -H 'content-type: application/json' \
     -d '{"message":"What is the stock of PCB-492?"}' | jq
```

- Code: `apps/orchestrator/app/copilot/` (`chat.py` = the loop) · route `POST /copilot/chat` ·
  MCP clients `app/mcp/client.py` (`SalesforceMcpClient` + `EcomMcpClient`, shared session) ·
  panel `apps/control-panel/src/components/CopilotChat.tsx`. Offline tests: `tests/test_copilot_chat.py`.
- **Tool sources:** SF Hosted MCP (§3j, needs `SF_MCP_*`) + e-com MCP (`ECOM_MCP_URL`, else derived
  from `ECOM_API_URL` + `/api/mcp` — arms automatically, no auth). Either can be off; the copilot
  uses whatever is armed.
- **Name aliasing:** SF's hosted MCP mangles tool names into ~65-char strings; Groq rejects names
  over 64 chars, so the loop aliases them and maps back when calling (the trace shows the real name).
- **The loop self-corrects:** if Groq calls a tool with the wrong args, the MCP validation error is
  fed back and the model retries — proven live (it fixed `part_number` → `partNo` on its own).
- ⚠ **SF refresh-token rotation (handled, but needs one fresh token to seed):** the SF ECA forces
  rotation ("Enable Refresh Token Rotation" is locked ON — can't disable without a Support case), so
  every refresh mints a new token and kills the old one. We **persist** the rotated token to the
  `app_secrets` table (`app/db/secrets.py`): the client flags a rotation, the copilot route saves it,
  and **boot restores the latest from the DB** — so restarts/redeploys self-heal. The `.env` /
  `SF_MCP_REFRESH_TOKEN` is only needed to seed the **first** call after a fresh deploy; if SF ever
  goes dead (e.g. DB reset, or no call ever succeeded), re-mint with `uv run python -m app.mcp.login`
  and update the env, then one successful call re-persists it. (E-com has no auth — never affected.)
- **Resilience:** a dead/unarmed source (e.g. SF token down) no longer 500s the copilot — it's
  skipped and listed in the reply's `sourcesUnavailable`; the working sources still answer.
- ⚠ **Groq free-tier token limit (~8k tokens/min).** A broad query (e.g. "total items in inventory"
  → `list_products` over all 86 parts) can exceed it. The copilot now **catches that gracefully**
  (a friendly "ask something narrower" message, never a 500) and **caps each tool result**
  (`_TOOL_RESULT_CAP` in `app/copilot/chat.py`) fed back to the model. For full-catalog counts,
  upgrade the Groq tier. (A 500 here also drops the CORS header, so it looks like a CORS error in the
  browser — it isn't.)

## 3i. E-com inventory service: the separate stock source + MCP (build step 13)

*Decision A: inventory is a **separate source** — product image + price + stock live in a Next.js +
Supabase app (`apps/ecom`), not Salesforce. The orchestrator reads/reserves over HTTP; blank
`ECOM_API_URL` → `FakeInventory` (offline default, every test). Admin-only, no storefront.*

```bash
# --- E-COM SERVICE (apps/ecom) ---
cd apps/ecom
cp .env.example .env.local          # fill NEXT_PUBLIC_SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY
#                                     (Supabase dashboard -> Settings -> API). service_role = server only.
# 1) Create the tables: paste supabase/schema.sql into the Supabase SQL editor and run it.
pnpm install
pnpm seed                           # loads 86 parts from the orchestrator catalog; scarce parts -> qty 1
pnpm dev                            # dashboard http://localhost:3000 · API /api/* · MCP /api/mcp

# --- WIRE THE ORCHESTRATOR TO IT ---
# In apps/orchestrator/.env:  ECOM_API_URL=http://localhost:3000  (then restart the app)
# RestInventory swaps in for FakeInventory automatically — the graph/tests don't change.
# LIVE (Render): set ECOM_API_URL=https://field-flow-ai.vercel.app on the Render service instead.

# --- The HTTP contract (what RestInventory calls) ---
curl http://localhost:3000/api/stock/PCB-492                 # {partNo, locations:[{location,qty}]}
curl -X POST http://localhost:3000/api/reserve -H 'content-type: application/json' \
     -d '{"partNo":"PCB-492","qty":1}'                       # {ok:true|false}  (atomic; NFR-5)

# --- NFR-5 race, live in a demo ---
# On the dashboard hit "Grab" on the scarce part (drops it to 0) right before the pipeline reserves
# it -> the reserve refuses instead of overselling. "Set" + a number restores stock.
```

### DEPLOYED (live on Vercel, 2026-10-12)

- **Public URL: https://field-flow-ai.vercel.app** — this is the value Render's `ECOM_API_URL` points at.
- **How it was deployed (Vercel dashboard → Import Git repo):**
  - Repo `KaleemAhmed123/FieldFlow-AI`, **Root Directory = `apps/ecom`** (the monorepo key step — the
    Next.js build is self-contained there; this is the OPPOSITE of the Render service's blank root).
  - Framework = Next.js (auto), package manager = pnpm (`pnpm-lock.yaml` present), build = default.
  - Two env vars (from `apps/ecom/.env.local`): `NEXT_PUBLIC_SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`.
  - No `vercel.json` needed; `next.config.mjs` already allows `placehold.co` images. No DB work (schema +
    seed already ran on the `fieldflow-ecom` Supabase project — Vercel just serves against it).
- **Verified live 2026-10-12:**
  ```
  GET /api/products        → HTTP 200, 86 products          ✅
  GET /api/stock/PCB-492   → {"partNo":"PCB-492","locations":[{"location":"Noida","qty":1}]}  ✅
  POST /api/mcp (init)      → HTTP 404 "Not found"            ✗  (see caveat)
  ```
  (`/api/reserve` not fired by hand — it mutates stock; the orchestrator exercises it. Contract + the
  atomic SQL were proven on the live DB at build-step-13.)
- **Writes are intentionally open (no auth)** — POC with fake data; a stray mutation is reversed with the
  dashboard "Set" button or a re-`pnpm seed`. Locking them would mean editing `RestInventory` + a Render
  env var, so it was skipped on purpose (user decision, 2026-10-12).
- **MCP path (`/api/mcp`) — FIXED + LIVE (verified 2026-10-13, returns 200):** `createMcpHandler` defaults
  its base path to `""` (serves `/mcp`); the fix passes `{}, { basePath: "/api" }` as the 2nd+3rd args in
  [`app/api/mcp/route.ts`](apps/ecom/app/api/mcp/route.ts) so it serves at `/api/mcp`. **Applied and
  deployed** — `POST https://field-flow-ai.vercel.app/api/mcp` (initialize) → HTTP 200. Ready for the
  admin copilot (build-step-14).
- Write-up: [`build-step-13-ecom-inventory.md`](docs/specs/field-service-recovery/build-step-13-ecom-inventory.md) §7.

## 3l. Reset to a clean demo slate + reseed everything (the real SF → RCS test)

*When data drifts — a stray half-wired appointment, drained e-com stock, stale cases/DLQ — wipe and
reseed so EVERY flow runs. `app/data/catalog.json` is the single source of truth; the three seeds
below all derive from it, so Salesforce + e-com + RAG stay consistent. Run in this order:*

```bash
# 1) SALESFORCE — clean the demo chain, then reseed 28 fully-wired appointments (each WITH a
#    technician) and print the FIRE MENU (AppointmentNumber -> model -> warranty -> suggested reason).
uv run --with simple-salesforce python apps/salesforce-apex/seed_demo_data.py --clean
uv run --with simple-salesforce python apps/salesforce-apex/seed_demo_data.py
#    !! --clean removes ONLY FFDemo-tagged records. DELETE any hand-made stray appointment (e.g. an
#    early SA-00xx with no assigned resource) BY HAND in Salesforce — it isn't cleaned, and an
#    appointment with no technician is exactly what crashed the first SF->RCS fire.

# 2) E-COM — reset the 86 parts + stock (earlier live fires drain scarce parts to 0).
cd apps/ecom && pnpm seed && cd ..

# 3) ORCHESTRATOR — wipe case history + paused checkpoints + purge the DLQ. KEEPS app_secrets (the
#    SF copilot refresh token). Dry-run first (counts only), then --yes to apply.
cd apps/orchestrator
uv run python scripts/reset_state.py          # dry run — what it WOULD delete
uv run python scripts/reset_state.py --yes    # apply
cd ..
# 4) RAG is already ingested from the same catalog — no reseed unless you edited catalog.json.
```

**Then fire the REAL SF trigger (not `/sim`):**
1. Pick an appointment from the FIRE MENU printed in step 1.
2. On that ServiceAppointment set **`At_Risk_Reason__c`** to the row's suggested reason (blank
   defaults to `technician_delay` = a plain reschedule).
3. Tick **`At_Risk__c`** (false → true) and Save → the `@future` callout fires → orchestrator →
   graph → a real RCS card lands on `VONAGE_TEST_TO`.
4. Watch it: `GET /cases` (a new case appears, past `FAILED`) and the async Apex log line
   `FieldFlow at-risk <num> -> 200 {"published":true,...}`.

> **Robustness (2026-10-13):** a missing technician/customer/asset no longer crashes the pipeline —
> `load_context` coalesces it to empty, so the card still sends (the call chip falls back to "Call
> support") instead of dead-lettering. **Verified live** against seeded `SA-0033`: `OPTIONS_SENT`,
> real customer/asset read from the org, groq proposer, carousel sent.
>
> **Seed vs this org's Field Service config (2026-10-13):** `seed_demo_data.py` was hardened for FS
> validation — a new ServiceAppointment can't be CREATED in Scheduled status (create in default, no
> status), and assigning a resource needs the SA scheduled + a ServiceTerritoryMember. This org has
> no territory members, so **technician assignment is best-effort and currently skipped** → every
> seeded card shows **"Call support"**. For named-tech cards ("Call Rahul"), set up a ServiceTerritory
> + OperatingHours + ServiceTerritoryMembers, then re-run the seed.

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
| Salesforce trigger (Step 9c) | SF Platform Event → mapper → same queue (downstream unchanged) | §3g · or `make test` → `test_event_source.py` |
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
  events/source.py      the at-risk event SOURCE (Step 9c): real Salesforce Pub/Sub subscriber when
                        armed, else None so /sim is the trigger. platform_event_to_at_risk maps the
                        SF payload → our contract event → same RabbitMQ exchange (downstream unchanged).
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
2026-10-08, **70 green**; the DLQ land+replay is a manual RabbitMQ demo — see §3f) →
**Step 9c Salesforce trigger** (the at-risk flow started by a real SF Platform Event over Pub/Sub —
seam + payload mapper **built + offline-tested** 2026-10-10, **78 green**; the gRPC subscription is
gated on the org — see §3g) →
**Decision A** (2026-10-10: inventory is a **separate e-com source** — product image + price + stock;
Salesforce owns the service domain only. E-com = a real Node/Postgres service + admin dashboard, no
customer storefront; stack/host TBD — recorded in `context/01-domain-and-data.md`).
Next: **e-com inventory service** (Vercel + Supabase) · **9c live fire** (fill the gRPC subscriber once
the org is provisioned) · **Step 12** make the stack honest — **real MCP** (SF Hosted MCP + e-com MCP
server + admin copilot; pipeline stays deterministic), **Logfire** god-eye view, **simple
reconciliation** (see [`build-step-12-real-mcp-and-observability.md`](docs/specs/field-service-recovery/build-step-12-real-mcp-and-observability.md)) ·
**`RestSalesforce` adapter SHIPPED** (2026-10-10, mock-first, 91 green) — reads + reschedule over
`apps/salesforce-apex/`, armed by the 3 `SF_*` creds; live calls gated on the Apex deploy · **9b live
fire** · **8** panel polish.

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

**★ CURRENT FRONT DOOR (2026-10-13, SF record-trigger LIVE + Phase 2 rich RCS DONE; next=commit slices 5-6 + copilot chat) — paste this to continue in a fresh chat**
```
Continue FieldFlow AI. Working dir C:\Users\hp\Desktop\RCS-VONAGE-POC.

READ FIRST (in order): CLAUDE.md (HARD rules — plain teaching style; PLAN-FIRST + WAIT for my go on
every open question; surface MY action items + which boring tasks to hand juniors; end every reply with
What I achieved / What I need from you / Next steps; spec-driven under docs/specs/field-service-recovery/;
playbook.md is the command home, update it in the SAME change); playbook.md §8 (this block) + §3g-b (SF
record trigger) + §3g-c (rich RCS) + §3h (SF Apex REST) + §3i (e-com); the spec
docs/specs/field-service-recovery/salesforce-trigger-and-rich-rcs.md (the whole SF-trigger + rich-RCS
build, slices 1-6); memory fieldflow-build-progress.

ONE IDEA: AI proposes -> deterministic policy decides -> human approves risk -> RCS is the customer
control plane. The decision trace is the hero.

STATE (2026-10-13): backend GREEN — from apps/orchestrator: `uv run pytest -q` -> 108 passed, `uv run
ruff check .` clean (dev deps: `uv sync --extra dev`). Panel builds (apps/control-panel: `pnpm build`).
Orchestrator LIVE on Render (fieldflow-ai-w6bm.onrender.com); e-com LIVE on Vercel
(field-flow-ai.vercel.app, POST /api/mcp initialize = 200). SF org = astreait88-dev-ed.

DONE THIS ERA:
- SF RECORD TRIGGER -> RCS -> CLOSE is LIVE end-to-end (2026-10-13). Tick ServiceAppointment.At_Risk__c
  (or Status='Cannot Complete') -> Apex trigger ServiceAppointmentAtRisk -> FieldFlowAtRisk.cls @future
  callout -> POST /webhooks/sf/at-risk (app/webhooks/routes.py; SF_HOOK_SECRET via X-FieldFlow-Secret
  header; reuses platform_event_to_at_risk + broker) -> graph -> real RCS carousel on the phone -> tap ->
  CLOSED. Deployed via apps/salesforce-apex/deploy_sf.py (stdlib Tooling API: Apex create +
  update-via-MetadataContainer + --fields + --self-check). 3 custom fields: At_Risk__c /
  At_Risk_Reason__c (10 reasons) / Delay_Minutes__c. FieldFlow Named Credential holds URL+secret.
  GOTCHAS: fields invisible until Field-Level Security is set; trigger fires only on a false->true
  TRANSITION (untick->save->tick->save to re-fire). COMMITTED + PUSHED.
- PHASE 2 RICH RCS (6 slices): the customer card = AI-written reason-aware body (proposer
  customer_message + deterministic fallback) + action chips (Share Location + Call technician on every
  offer; Send-a-photo on parts) + a confirmation card at verify (archetype-aware body + Add to Calendar +
  Call + Service report PDF). /sim/photo runs SIMULATED OCR -> photoVerified on the trace; PDF = a
  placeholder URL + serviceReport on the trace. All simulated-but-labelled (heavy compute stubbed, the
  RCS primitive real). Panel RcsCardPreview + DecisionTrace render all of it. Slices 1-3 COMMITTED+PUSHED;
  SLICES 5-6 BUILT BUT NOT YET COMMITTED.

IMMEDIATE: commit slices 5-6 (human-commits style, no trailer, 4 snapshots backend/panel/tests/docs) +
push. Then pick NEXT:
- build-step-14 ADMIN COPILOT CHAT (plan-first): a /copilot chat route running the Groq->Gemini ladder in
  tool-calling mode over MCP; e-com MCP (/api/mcp) is LIVE + ready; SF Hosted MCP needs my ECA (below).
  Plumbing already built: app/mcp/ (client+login), GET /copilot/tools, 8 FFCopilot_* Apex tools deployed.
- OR optional gated-live polish: real inbound-image webhook (needs a device#->case map), real per-case PDF.

MY OPEN ACTION ITEMS:
1. SF Hosted MCP server + a NEW External Client App (OAuth2+PKCE, scopes mcp_api+refresh_token, callback
   http://localhost:8000/oauth/callback) -> SF_MCP_* in .env -> `cd apps/orchestrator && uv run python -m
   app.mcp.login` -> SF_MCP_REFRESH_TOKEN (playbook §3j / hosted-mcp-setup.md). Only blocks SF tools in
   the copilot; e-com tools work without it.
2. (optional) the 9c gRPC Pub/Sub live fire — deferred; the HTTP-callout trigger above is what we use.

HOUSE RULES: PLAN-FIRST (restate task, list open questions WITH recommendations, WAIT for my go before
code). Keep tests green + ruff clean; update playbook.md + the spec Explanation in the SAME change; ask
before editing context/** beyond approved notes. Do NOT fire a billed Vonage send, a live payment, push,
or edit apps/orchestrator/.env without my explicit go.

Ask me: commit slices 5-6 now, or start build-step-14 planning, or something else?
```

**★ EARLIER FRONT DOOR (2026-10-11, SF reads+reschedule LIVE + MCP copilot plumbing done) — superseded**
```
Continue FieldFlow AI. Working dir C:\Users\hp\Desktop\RCS-VONAGE-POC.

READ FIRST (in order): CLAUDE.md (HARD rules — plain teaching style; PLAN-FIRST + WAIT for my go on
every open question; surface MY action items + which boring tasks to hand juniors; end every reply with
What I achieved / What I need from you / Next steps; spec-driven under docs/specs/field-service-recovery/;
playbook.md is the command home, update it in the SAME change); playbook.md §8 (this block) + §3i (e-com
run) + §3h (SF Apex REST); docs/specs/field-service-recovery/build-step-12-real-mcp-and-observability.md
(§3 Q1-Q6 + §4 plan — the copilot is item 6) + hosted-mcp-setup.md; memory fieldflow-build-progress.

ONE IDEA: AI proposes -> deterministic policy decides -> human approves risk -> RCS is the customer
control plane. The decision trace is the hero. GUARDRAIL for #4: the copilot is the ONE agentic piece
(LLM picks tools over MCP); the recovery PIPELINE stays deterministic; every copilot WRITE is
human-confirmed; MCP servers stay read-only for now.

STATE (2026-10-11): backend deep + GREEN — from apps/orchestrator: `uv run pytest -q` -> 99 passed,
`uv run ruff check .` clean (dev deps: `uv sync --extra dev`). Steps: Spine,1,2,§3,4(RAG live),5(LLM
ladder live),6(commerce),9(Razorpay),9b(Vonage RCS live-fired),7(failures),9c(SF trigger mock-first),
8(React panel),10(catalog),13(E-COM SERVICE apps/ecom Next.js+Supabase+MCP — SHIPPED+LIVE+COMMITTED,
other chat), and STEP 12 (SF + MCP) now deep:
- RestSalesforce (Apex REST) reads + reschedule are LIVE-VERIFIED against the real org
  (astreait88-dev-ed): seeded via apps/salesforce-apex/seed_demo_data.py -> SA-0001 (in-warranty) +
  SA-0002 (out-of-warranty); reschedule moved SchedStartTime for real. Two Apex bugs fixed live
  (`in` reserved word; reschedule must update a FRESH ServiceAppointment(Id=...) w/ only the 2 time
  fields). Field-edit note in apps/salesforce-apex/README.md §3.
- Hosted-MCP admin-copilot PLUMBING built mock-first + deployed: app/mcp/client.py (SalesforceMcpClient:
  refresh-token->access-token + Streamable-HTTP session via `mcp` SDK, lazy) + app/mcp/login.py (one-time
  OAuth2+PKCE) + build_mcp_client swap line + GET /copilot/tools route + tests/test_mcp_client.py (+5).
  8 READ-ONLY tools as 8 classes in apps/salesforce-apex/copilot/FFCopilot_*.cls (appointment-health,
  needing-attention, customer-appts, technician-schedule, asset-history, unassigned, out-of-warranty,
  status-counts) — DEPLOYED + data-verified via Tooling API, declared `global` (required for MCP).
- Also: CRM-AI-OPPORTUNITIES.md (repo root) = top-5 CRM problems strategy doc.
E-com runs: cd apps/ecom && pnpm dev (dashboard :3000, MCP /api/mcp read-only). Orchestrator .env has
ECOM_API_URL=http://localhost:3000 so RestInventory is live.

APEX RULES LEARNED (don't repeat): one @InvocableMethod PER class; class+method+@InvocableVariable fields
must be `global` not `public` for Hosted-MCP discovery. SF Hosted MCP auth = OAuth2+PKCE (no headless
client-creds) -> the one-time `python -m app.mcp.login`. Run-as user of the client-creds flow =
shaam@astreait.com (System Administrator), NOT the browser admin.

MY OPEN ACTION ITEMS (the current blocker for the live copilot):
1. Stand up the SF Hosted MCP server: Setup -> MCP Servers -> "Salesforce Servers" TAB (not External)
   -> "Add MCP Server" (top-right) -> create a Salesforce MCP server -> add the 8 FFCopilot_* Apex
   actions -> Activate -> copy the server URL. (If it demands wrapping each as an Agent Action in
   Agentforce Studio first, tell Claude.)
2. Create a NEW External Client App (ECA) for MCP (separate from the Pub/Sub client-creds): OAuth2+PKCE,
   scopes incl. mcp_api + refresh_token, callback http://localhost:8000/oauth/callback -> Consumer
   Key+Secret. Put SF_MCP_SERVER_URL/CLIENT_ID/CLIENT_SECRET in apps/orchestrator/.env, then
   `cd apps/orchestrator && uv run python -m app.mcp.login` -> paste SF_MCP_REFRESH_TOKEN. (playbook §3j)
3. SF org provisioning (salesforce-handoff.md §8) -> unblocks the 9c Pub/Sub gRPC live fire (set
   SF_PUBSUB_ENABLED=true only once SalesforcePubSubSource.run is filled).
4. OPTIONAL: orchestrator crashes on Windows w/ a Postgres DATABASE_URL (psycopg needs
   SelectorEventLoop; graph/checkpointer.py) — Render/Linux fine; want the ~3-line run.py fix?

NEXT TASK (after I arm the MCP creds): BUILD THE COPILOT CHAT (build-step-14). Plumbing is done; what's
left = (a) a `/copilot` chat route that runs the Groq->Gemini ladder (app/llm/) in TOOL-CALLING mode over
the MCP client(s) — e-com MCP (/api/mcp) is live NOW, SF Hosted MCP plugs in once #1+#2 land; (b) a panel
chat UI in apps/control-panel that POSTs to /copilot (MCP tokens stay server-side). Writes human-confirmed,
never an LLM-invoked mutation. Also: once #1+#2 done, Claude live-verifies GET /copilot/tools first.

HOUSE RULES: PLAN-FIRST — write build-step-14 sections 1-5, restate the task, list open questions WITH
your recommendation, and WAIT for my explicit go before any code. Keep 99 tests green; update playbook.md
+ the build-step Explanation in the SAME change; ask before editing context/** beyond approved notes. Do
NOT fire a billed Vonage send, a live payment, or edit apps/orchestrator/.env without my explicit go.

UNCOMMITTED (earlier cross-session work, still in the tree): RestSalesforce adapter + seed script + MCP
client/login + 8 copilot Apex classes + reconcile + event-source + logfire + apex + CRM-AI-OPPORTUNITIES.md
+ shared hunks in main.py/config.py/.env.example/playbook + doc edits + .gitignore. ignoreit.txt = stray
transcript, gitignore it. Offer to commit as small snapshots (shared files need `git add -p`) when I ask.
E-com step 13 is already fully committed.

Ask me: arm the MCP creds now (I do action items #1+#2), or start build-step-14 copilot chat against the
LIVE e-com MCP first, or commit the earlier work?
```

**★ EARLIER FRONT DOOR (2026-10-10) — superseded by the #4 block above**
```
Continue FieldFlow AI. Working dir C:\Users\hp\Desktop\RCS-VONAGE-POC.

READ FIRST (in order): CLAUDE.md (HARD rules — plain teaching style, PLAN-FIRST + WAIT for my go on open
questions, surface my action items + junior delegation, end every reply with What I achieved / What I
need from you / Next steps; spec-driven under docs/specs/field-service-recovery/; playbook.md is the
command home); docs/specs/field-service-recovery/README.md (status + key decisions); playbook.md §6
(build status) + §10 (deployment); memory fieldflow-build-progress.

ONE IDEA: AI proposes -> deterministic policy decides -> human approves risk -> RCS is the customer
control plane. The decision trace is the hero.

STATE (2026-10-11): backend deep — Spine,1,2,§3,4(RAG live),5(LLM ladder live),6(commerce),9(Razorpay),
9b(Vonage RCS LIVE-fired on a real device 2026-10-09),7(failure demos),9c(SF Pub/Sub trigger mock-first),
8(React panel),10(catalog),12 quick wins(Logfire wired + reconciliation) + 12 Task3(RestSalesforce
adapter: SF reads+reschedule over Apex REST, mock-first) + 13(e-com inventory service: Next.js+Supabase+
MCP at apps/ecom, RestInventory swap-in; LIVE-VERIFIED 2026-10-11 on a new Supabase project
fieldflow-ecom — 86 parts, reserve race confirmed; user to set ECOM_API_URL in orchestrator .env). From
apps/orchestrator: `uv run pytest -q` -> 94 passed, `uv run ruff check .` clean,
`uv run python -c "import app.main"` OK (dev deps: `uv sync --extra dev`). E-com: cd apps/ecom &&
pnpm install && pnpm build (green). All mock-first/offline; only live fires gated.

DECISIONS (recorded in context docs + build-step-9c + build-step-12 + salesforce-handoff + hosted-mcp-setup):
- Decision A: inventory is a SEPARATE e-com source (product image+price+stock); Salesforce owns the
  service domain only. E-com = Node/Next.js service + admin dashboard, NO customer storefront.
- MCP made REAL (was MCP-shaped). Driver = an admin copilot (agentic chat over SF + e-com). GUARDRAIL:
  the recovery pipeline stays DETERMINISTIC (Apex REST + policy ladder, never LLM-invoked MCP on
  mutations); copilot WRITES stay human-confirmed. SF reads -> Salesforce Hosted MCP (hosted-mcp-setup.md);
  pipeline SF reads + reschedule -> Apex REST (apps/salesforce-apex/).
- Deployment: control panel + e-com -> Vercel; orchestrator -> Render (I ping /health every 5 min vs cold
  start); Supabase (DB) + CloudAMQP (queue) managed. Logfire god-eye WIRED (my LOGFIRE_TOKEN is set).

MY ACTION ITEMS (the real blockers; I have org access + FS enabled + SF_* trigger creds added):
1. Provision the org per salesforce-handoff.md §8 (My Domain, FS, Platform Event Appointment_At_Risk__e,
   Connected App client-credentials) — confirm done.
2. Deploy apps/salesforce-apex/FieldFlowRest.cls + create Asset.Warranty_Active__c + grant the integration
   user Apex-class access (its README) + confirm assumptions A1-A4.
3. For the copilot: a NEW External Client App for Hosted MCP (hosted-mcp-setup.md) — separate creds.

NEXT BUILD ORDER (confirm/reorder; then PLAN-FIRST — restate, open questions w/ your recommendation, WAIT):
1. [DONE 2026-10-10] RestSalesforce adapter -> SF reads+reschedule over Apex REST (build_salesforce swap
   line; armed by the 3 SF_* creds; live calls gated on the Apex deploy). 2. SF Hosted MCP + real MCP
   client (reads) — needs the new ECA. 3. [DONE 2026-10-11] E-com service (Next.js + Supabase; admin
   dashboard + NFR-5 grab-part knob) + its MCP server — apps/ecom, build-green; user action: Supabase
   creds + schema.sql + pnpm seed + set ECOM_API_URL (playbook §3i). 4. Admin copilot /copilot route +
   panel chat (writes human-confirmed) — now unblocked by #3. 5. 9c live fire (fill
   SalesforcePubSubSource.run gRPC once org live; set
   SF_PUBSUB_ENABLED=true).

RULES: mock-first (keep 91 tests green; disarm live creds via process env for dry runs); PLAN-FIRST + WAIT;
update playbook.md + the build-step Explanation in the SAME change; ask before editing context/** beyond
approved notes; do NOT fire a billed Vonage send, a live payment, or edit apps/orchestrator/.env without my
explicit go. Ask me which to start, then plan it.
```

**Continue after Step 10 (panel + realistic data both shipped) — older front door**
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

---

## 9b. API-key gate (AI-SEC-01, added 2026-10-22)

The orchestrator API is protected by one shared secret in the `X-API-Key` header. Open without it:
`/health`, `/ready`, `/health/deps`, `/version`, `/metrics` (monitors + Prometheus).

- **Blank key = gate OFF** (local/dev/tests) — nothing changes until you set it.
- **Turn it on (both sides must match):**
  1. Generate: `openssl rand -hex 32`.
  2. Orchestrator: set `API_KEY=<value>` on Render (env var) and in `apps/orchestrator/.env` locally.
  3. Panel: set `VITE_API_KEY=<same value>` in `apps/control-panel/.env` (+ Vercel env), rebuild.
- **curl once it's on:** add `-H "X-API-Key: <value>"` to every call except the open paths.
- **⚠ Production fail-closed (P0-6):** when `APP_ENV=production`, boot REQUIRES `API_KEY`,
  `VONAGE_SIGNATURE_SECRET`, and `SF_HOOK_SECRET` all set — a blank one aborts startup (by design).
  Keep `APP_ENV` at its default (`local`) for demo deploys, or set all three before flipping it.
- **Copilot rate limit (P0-4):** `/copilot/chat` is capped at `COPILOT_RATE_PER_MIN` (10) +
  `COPILOT_RATE_PER_DAY` (200); over a cap returns a friendly "busy" reply, no Groq spend.
- **Event retries (P0-5):** a failed event retries 3× (5s/30s/120s) via `events.retry.*` queues
  before landing in `events.dlq` — a transient outage self-heals; `/ops/dlq/replay` is the last resort.
**Operate vs simulate (P0-2):**
- Real operator controls are at `/ops/*` — `/ops/approve` (human Level-3 approval) and
  `/ops/dlq/replay` — **always mounted**, behind the API key.
- `/sim/*` (fire event, `fault` toggle, forge reply/payment/photo/delivery) is mounted only when
  `SIM_ENABLED=true` (the default). **Set `SIM_ENABLED=false` on the production Render deploy** so the
  forge/chaos routes don't exist there. Keep it true for local + demo deploys.
- Panel calls moved: Approve/Reject → `/ops/approve`, Replay DLQ → `/ops/dlq/replay`.

---

## 9c. Database migrations — Alembic (AI-DATA-01, added 2026-10-22)

Postgres schema is owned by **Alembic** (versioned migration scripts). `create_all` still builds the
schema on **SQLite** (local dev + tests) — no migrations there. All commands run from
`apps/orchestrator`, reading `DATABASE_URL` from `.env` (or the env var).

```bash
cd apps/orchestrator
uv run alembic current                 # which migration the DB is on
uv run alembic upgrade head            # apply all pending migrations
uv run alembic downgrade -1            # roll back one
# after editing app/db/models.py — generate a new migration (safe: env.py's include_object guard
# ignores LangGraph checkpoints + RAG knowledge_chunks, so autogenerate only touches OUR tables):
uv run alembic revision --autogenerate -m "describe the change"
```

**First-time adoption on the LIVE Supabase DB (do once, in this order):**
1. The live DB already has our 5 tables (old `create_all`). From your machine (Supabase
   `DATABASE_URL` in `apps/orchestrator/.env`), mark it at the baseline **without** running DDL:
   `cd apps/orchestrator && uv run alembic stamp head`. Touches no data.
2. Migration-on-deploy is **baked into the Docker image** — `apps/orchestrator/docker-entrypoint.sh`
   runs `alembic upgrade head` then `exec`s uvicorn (`ENTRYPOINT` + `CMD` in the Dockerfile). So on
   Render you set **nothing** — no Pre-Deploy (paid/locked), no Docker Command override. Every deploy
   and every cold-start wake migrates first; `upgrade head` is idempotent so a no-op is instant.
   (On a *fresh/empty* DB you skip the stamp — `upgrade head` just creates everything.)
- ⚠ **Order matters — Auto-Deploy is On Commit:** pushing triggers a deploy that runs `upgrade head`.
  Run `alembic stamp head` (step 1) **before** you push the Dockerfile change, or the first deploy
  crash-loops on "table already exists".
- ⚠ Shell scripts are pinned to LF via root `.gitattributes` (`*.sh text eol=lf`) — without it a
  Windows CRLF checkout breaks the entrypoint inside the Linux container.
- DB is disposable/test-only: everything reseeds from `app/data/catalog.json` + the seed scripts
  (§3l), so a clean rebuild is always available if you ever prefer it over stamping.

---

## 9d. CI + reproducible build (AI-SUP-01, added 2026-10-22)

`uv.lock` is **committed** (no longer gitignored) so every build installs the identical tree.
GitHub Actions (`.github/workflows/ci.yml`) runs on every push/PR: `uv sync --locked --all-extras`
→ `ruff` → `pytest` (Python 3.12, matching the Docker image) → `pip-audit` (non-blocking CVE scan).

Run the same checks locally:
```bash
uv sync --locked --all-extras                 # (repo root) fails if uv.lock drifts from pyproject
cd apps/orchestrator && uv run ruff check . && uv run pytest -q
# dependency CVE scan (what CI runs; non-blocking there) — from repo root:
uv export --locked --all-packages --no-emit-workspace --format requirements-txt > audit-reqs.txt
uvx pip-audit -r audit-reqs.txt
```
- **After editing deps:** run `uv add <pkg>` / `uv sync` so `uv.lock` updates, then commit the lock —
  else CI's `--locked` step fails.
- **CVEs — all cleared 2026-10-22:** bumped `pypdf` → 6.21.2 (direct, pyproject); `pillow` → 13.0.0,
  `certifi` → 2026.10.19, `nltk` → 3.10.4 (transitive, via `uv lock --upgrade-package` — parents
  allowed the patched versions, no pyproject change). `pip-audit` now reports **no known
  vulnerabilities**.

---

## 9e. Manual live-sandbox e2e checklist — V-1 (AI-TEST-01 / OQ5)

The one real end-to-end pass before trusting real money: run the orchestrator **locally** against the
**real Razorpay TEST key + real Salesforce reads**, drive an at-risk job to a paid capture, and read
the result back. Local (not the public deploy) so it can't send a stray RCS or pollute prod. ⚠ This
fires a **real** payment link — **you tap it once**; the fake gateway can't be used here (the live
poller reads Razorpay, so a simulated "paid" won't capture).

**Pre-flight (you):**
- [ ] `apps/orchestrator/.env`: real `SF_*` creds; `RAZORPAY_KEY_ID=rzp_test_…` + `RAZORPAY_KEY_SECRET=…`
      (TEST mode); `VONAGE_*` as usual (or leave fake if you only want to verify payment + SF).
- [ ] Salesforce demo data seeded (§3 seed) — need `SA-OOW` (out-of-warranty → chargeable) present.
- [ ] If `API_KEY` is set locally, add `-H "X-API-Key: <key>"` to every curl below.

**Run (I drive; you tap once):**
1. [ ] Start local: `cd apps/orchestrator && uv run uvicorn app.main:app --reload --port 8000`
       (Windows needs `--reload` — see §4 ProactorEventLoop note). Alembic runs in-process on SQLite;
       for a Postgres run it migrates via the entrypoint only in Docker, so locally use the dev DB.
2. [ ] Fire at-risk against the chargeable appointment:
       `curl -X POST localhost:8000/sim/fire -H 'Content-Type: application/json' -d '{"workOrderId":"WO-PAY","appointmentId":"SA-OOW","reason":"part_missing","eventId":"evt-v1"}'`
3. [ ] AI proposes → **approve** the human-gated step: `curl -X POST localhost:8000/ops/approve …`
       (the panel's Approve button does the same).
4. [ ] Customer picks a slot → a **real** Razorpay payment link (`short_url`) is created.
5. [ ] **← YOU: open the `short_url`, pay with test card `4111 1111 1111 1111`.** The poller
       (`payment_poller.py`, every ~10s) fetches Razorpay and captures — **no `/sim/payment`**.

**Verify (read back):**
- [ ] Case reaches `CLOSED`; `GET /cases/WO-PAY` shows the captured payment in the decision trace.
- [ ] The SF payment record was written back (check the Salesforce record / the demo payment script).
- [ ] No double-charge on a re-fire (idempotent capture) — re-run step 2's eventId, expect no new order.

Record the outcome (pass/fail + what you saw) in the remediation plan §6 under V-1.

---

## 9f. Observability — trace a case end to end, LLM analytics, alerts (AI-OBS-01)

Everything streams to **one Logfire project** — no Prometheus/Grafana to host. Spec:
[`docs/specs/observability-logfire.md`](docs/specs/observability-logfire.md).

### Turn it on
```
# On Render (orchestrator service → Environment) AND in apps/orchestrator/.env for local:
LOGFIRE_TOKEN=<your project write token>                 # from logfire.pydantic.dev → project → Write tokens
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=SPAN_ONLY   # capture prompts+completions (fake data → safe)
```
Blank token → every trace/metric call is a no-op (tests/offline unaffected). `OTEL_...` must be a
**real process env var** (Render env var, or `$env:OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT="SPAN_ONLY"`
in the shell before uvicorn) — it's read by the OTel instrumentation, not from `.env`.

### Trace ONE case from the SF call to the end
1. Fire a case (real SF trigger, or the sim): `POST /webhooks/sf/at-risk` (§3g) or `POST /sim/appointment-at-risk` (§3).
2. Logfire → **Live** view. You'll see one connected tree:
   ```
   POST /webhooks/sf/at-risk            ← the SF call (FastAPI span)
   └─ process event                     ← the consumer (same trace — traceparent crossed the queue)
      └─ case recovery  correlationId=… reason=… status=…
         ├─ node load_context   → SELECT … (SQLAlchemy spans) + Salesforce reads
         ├─ node retrieve_knowledge
         ├─ node generate_options → groq chat  (gen_ai.usage.input_tokens / output_tokens)
         ├─ node policy_validate  (outcome)
         ├─ node offer_to_customer → Vonage send
         └─ node close            status=CLOSED
   ```
3. **Follow one case:** in **Explore**, run
   `SELECT * FROM records WHERE attributes->>'correlationId' = 'WO-123' ORDER BY start_timestamp`
   — every span AND every structlog line for that case, in order. That's your 3am debugger.
4. A failed case: filter `WHERE is_exception` or `attributes->>'status' = 'FAILED'` → jump straight to the node that threw + its logs.

### LLM dashboard + analytics
- Logfire ships an **LLM panel** — it reads the `gen_ai.*` attributes our Groq span and the
  auto-instrumented Gemini calls emit: tokens in/out, latency, model, per-provider. Open it from the
  left nav (AI / LLM).
- Build a saved **Dashboard** (Dashboards → New) from these queries (each a chart):
  - requests/min: `SELECT time_bucket('1 minute', start_timestamp), count(*) FROM records WHERE span_name='case recovery' GROUP BY 1`
  - p95 case latency: `SELECT time_bucket('5 minutes', start_timestamp), approx_percentile(0.95, duration) FROM records WHERE span_name='case recovery' GROUP BY 1`
  - decision-outcome split: metric `fieldflow.decisions` by `outcome`
  - provider-fallback rate: metric `fieldflow.proposer_fallback` by `provider`
  - LLM tokens/day: `SELECT time_bucket('1 day', start_timestamp), sum((attributes->>'gen_ai.usage.output_tokens')::int) FROM records WHERE attributes ? 'gen_ai.usage.output_tokens' GROUP BY 1`

### Alert → Discord (FAILED case / DLQ growth)
1. Discord → Server Settings → Integrations → **Webhooks** → New Webhook → pick a channel → **Copy URL**.
2. Logfire → **Alerts** → New alert. Query, e.g. a FAILED case in the last 5 min:
   `SELECT count(*) FROM records WHERE span_name='case recovery' AND attributes->>'status'='FAILED' AND start_timestamp > now() - interval '5 minutes'`
   Condition: result `> 0`. Channel: **Discord** → paste the webhook URL.
3. (Optional) DLQ growth: alert on the `fieldflow.events_failed` metric rising.

> **USER action items:** set `LOGFIRE_TOKEN` + `OTEL_...` on Render; create the Discord webhook and
> build the alert; (optional) build the dashboard. The code side is done — spans/metrics already flow
> once the token is set. **Junior-friendly:** building the dashboard panels + the alert from the
> queries above.

*Where each piece runs for the hosted demo. All free tiers.*

| Piece | Host | Notes |
|-------|------|-------|
| **Control panel** (React/Vite) | **Vercel** | static build; set `VITE_API_URL` to the Render orchestrator URL. |
| **E-com inventory service** (Node/Next.js + admin dashboard) | **Vercel** | API routes + dashboard in one app; **Supabase Postgres** for stock, **Supabase Storage** (or Vercel Blob) for product images. |
| **Orchestrator** (FastAPI + consumer + 9c subscriber) | **Render** (free web service) | the consumer + Pub/Sub subscriber run inside the one process. |
| **DB** | **Supabase** (Postgres + pgvector) | already managed. |
| **Queue** | **CloudAMQP** | already managed. |

- **Render free sleeps after 15 min idle** → the user pings **`GET /health`** every 5 min (external
  cron / uptime pinger) to keep it warm. `/health` is cheap and never hits the network, so it's safe
  to hammer. *(ponytail: a warm-ping is the POC fix; a paid always-on dyno is the prod upgrade.)*
- **E-com on Vercel is serverless**, so the NFR-5 atomic reserve **must** be a single Postgres
  conditional `UPDATE ... SET qty = qty - $n WHERE qty >= $n` — correct no matter how many serverless
  instances run. The app layer is a thin API over that one guarantee.
- **Product image** served from the e-com over public HTTPS → the orchestrator puts that URL on the
  RCS card → fixes the 9b blank-card (Google RBM fetches the image itself).
- Orchestrator env on Render = the same `.env.example` keys (Supabase `DATABASE_URL`, CloudAMQP
  `RABBITMQ_URL`, the LLM/Jina/Vonage/SF keys). Nothing new to wire — just set them in Render's dashboard.
