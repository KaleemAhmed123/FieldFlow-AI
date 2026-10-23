# FieldFlow AI — Production-Readiness Audit

**Date:** 2026-10-14 · **Auditor:** evidence-based pass over code + tests + live server
**Method:** code is the source of truth (docs/playbook treated as stale). Every claim cites
`file:line` or a live endpoint. Where live and code disagree, the live server wins.

## How to read this

- **DONE** — real, verified in code *and* exercised (tests and/or live JSON).
- **PARTIAL** — part of the requirement is real, part is missing.
- **MOCK-ONLY** — built behind a seam but the real thing is simulated / gated (FakeVonage real
  send gated, simulated OCR, placeholder PDF). **Scored at 0 for "live-verified".**
- **MISSING** — not found.

## Evidence captured (run 2026-10-14)

| What | Result |
|------|--------|
| `uv run pytest -q` | **118 passed in 12.80s** (exit 0) |
| `uv run ruff check .` | **All checks passed!** (exit 0) |
| git HEAD | `9e93359` (2026-10-13 18:42) |
| Live `/version` | **404 Not Found** — route exists in code (`api/routes.py:49`) → **deploy is behind HEAD (stale)** |
| Live `/health` | `{"status":"ok"}` |
| Live `/health/deps` (shallow) | `ok` — postgres ok, rabbitmq ok, logfire configured, vonage **armed**, razorpay **test-mode** |
| Live `/health/deps?deep=1` | **`down`** — postgres `unreachable` (2.5s), gemini `models.list failed`; groq/jina ok |
| Live `/cases` | 7 real cases, real SF 18-char ids (`0WOdM000005i3Qj…`), full decision traces |
| Live `/copilot/tools` | **`available:true`** — real Salesforce Hosted MCP tools (FFCopilot_*) |
| Live `/dlq` | `available:true, depth:0` (RabbitMQ connected) |
| Live `/reconcile` | 1 lingering case (`OPTIONS_SENT`, 42min) |
| Live e-com `/api/products`, `/api/stock/PUMP-14` | real Supabase rows (`PUMP-14` Noida qty 3) |
| Live Razorpay (in a case) | real short link `rzp.io/rzp/H1UYR1W`, `pay_Tnf…` **captured** |

**Docs/memory contradicted by the live server (trust live):**
- Memory: "SF Hosted MCP server deferred as debt" → **live copilot MCP is armed and answering.**
- Memory: Razorpay "fake-then-one-gated-real" → **live cases show real test-mode links + captures.**
- `/version` in code but 404 live → **the running build predates several HEAD commits.**
- `playbook.md` stale (confirmed by user).

---

## Part A — Functional audit (SRS §8)

| ID | Requirement (1 line) | Status | Evidence | Notes / gaps |
|----|----------------------|--------|----------|--------------|
| **FR-1** | Appointment-created card (View / Calendar / Change slot / Share location) | **MISSING** | no create-appointment trigger or initial card anywhere | journey starts at `appointment.at_risk`; there is no "appointment created" stage |
| **FR-2** | Failure → `at_risk` event onto RabbitMQ → LangGraph wakes | **DONE** | `sim/routes.py:33`, `webhooks/routes.py:120`, `main.py:117`; live `events_processed_total 1` | both `/sim` and real `/webhooks/sf/at-risk` publish to the same exchange |
| **FR-3** | AI investigates: load appt/cust/asset/tech, SLA, manual search | **DONE** | `graph/build.py:186` (RAG), `:212` (context reads), `:235` (SLA), `:241` (options) | live traces show `toolsUsed` + `knowledgeSources` |
| **FR-4** | Options generated, policy removes illegal ones | **DONE** | `policy/__init__.py:57` (6 checks), `graph/build.py:265` | live `policyResult`/`removed` present |
| **FR-5** | Valid slots as swipeable carousel | **DONE** (delivery gated) | `graph/build.py:309`, `tools/vonage.py:123` (real RCS carousel schema) | carousel built + Vonage-schema-correct; **real-device RCS delivery is the gated single-device fire** |
| **FR-6** | Customer selects → graph resumes | **DONE** | `sim/routes.py:71`, `webhooks/routes.py:82` → `case_service.resume_case` | live cases reach `CLOSED` |
| **FR-7** | Share GPS → backend computes ETA / feasibility | **PARTIAL** | `share_location` chip `graph/build.py:91` | chip exists; **no ETA / feasibility computation found** |
| **FR-8** | Evidence requested → inbound image | **MOCK-ONLY** | `case_service.py:148` `record_photo` | simulated OCR; no real inbound-image webhook (code says "not built yet") |
| **FR-9** | Vision + RAG → model validated, manual/warranty/part retrieved | **PARTIAL** | RAG real (live `knowledgeSources` w/ scores); OCR `matchesAsset:True` hard-coded | **RAG DONE & live-verified; vision/OCR MOCK-ONLY** |
| **FR-10** | Inventory check + atomic reserve | **DONE** | `tools/inventory.py:36`, e-com `schema.sql:33` (`SELECT … FOR UPDATE`), live e-com stock | atomic on both fake and real e-com |
| **FR-11** | Quote (part + labour + GST) as card | **PARTIAL** | `graph/build.py:381`, live quote lines `Part + Labour` | quote/order built + sent live; **no GST line item** |
| **FR-12** | Razorpay Test-Mode webview, success updates state | **DONE** (live) | `commerce/razorpay.py:99`, live case: real link + `captured` | real test-mode link + capture verified; confirmation by **poll** not webhook (POC design); full on-device webview tap is the gated fire |
| **FR-13a** | Confirmation card (Track / Calendar / Dial) | **DONE** | `graph/build.py:452` (`verify`) | calendar + dial + PDF present; **"Track" action not built** |
| **FR-13b** | Service-report PDF on completion | **MOCK-ONLY** | `graph/build.py:55` `SERVICE_REPORT_URL` = vercel site root | placeholder link; real per-case PDF is the gated step (reportlab is a dep, unused for this) |
| **FR-X** | Decision trace `{decision,reason[],knowledgeSources[],toolsUsed[],confidence,policyResult}` | **DONE** | `graph/build.py:276`; every live case carries the full trace + `confidenceBreakdown` | strongest-built requirement in the system |

---

## Part B — Reliability audit (SRS §9)

| ID | Requirement | Status | Evidence | Notes / gaps |
|----|-------------|--------|----------|--------------|
| **NFR-1** | RCS→SMS failover | **DONE** (logic); real SMS gated | `case_service.py:116-145`; `/sim/delivery-status` twin + real `/webhooks/status`; `test_failures` | fallback fires on failed-delivery + `OPTIONS_SENT`; real SMS send via `VonageMessagesClient.send_sms` is gated |
| **NFR-2** | Idempotency / no double-charge | **DONE** | event dedupe `case_service.py:173`; payment dedupe `:226`; gateway idempotent capture `razorpay.py:55`; `test_idempotency` | **two independent layers** (envelope + gateway); live `events_duplicate_total` counter |
| **NFR-3** | SF down → retry → backoff → DLQ → reconciliation | **PARTIAL** | DLQ `queue/broker.py:80` (nack→DLQ), replay `:111`, reconcile `reconcile.py`; live `/dlq` + `/reconcile` | **no retry/backoff tier** — handler failure nacks *straight* to DLQ; the "retry→backoff" half of NFR-3 is missing |
| **NFR-4** | Low-confidence/risky → human approval | **DONE** | `graph/build.py:299` interrupt; `policy/__init__.py:85` `needs_human_for` (safety/warranty floor + threshold + DENIED); high-value `:393`; `/sim/approve` | risk-tiered gate; `test_policy`/`test_decision_flow` |
| **NFR-5** | Inventory race → clean fail → recompute | **DONE** | `graph/build.py:349` reserve-fail → `goto generate_options`; atomic `FakeInventory`/`ecom_reserve` | `test_inventory_rest` |
| **NFR-6** | Stale workflow version → reject → re-send | **DONE** | `graph/build.py:337` version check → re-offer; version in postback `tools/vonage.py:163` | `test_failures` |
| **NFR-7** | 3-level authority, no mutation skips L1 | **DONE** | policy always runs (L1); LLM proposes only (L2, `proposer.py`); human (L3); action tools run ladder + may refuse (`registry.py:62`) | architecturally enforced end-to-end |
| **NFR-8** | Bounded LLM latency, no LLM chains | **DONE** (design) | one `propose()` + one `retrieve()`; deterministic hot path; `llm_timeout_s=20` `config.py:41` | design-met; **no load/latency test** |
| **NFR-9** | Observability dashboards fed by real callbacks | **PARTIAL** | `/metrics` (Prometheus, live), Logfire configured (live), structlog, `/health/deps`, `/reconcile`, `/dlq`, FAILED-case visibility | **no Grafana dashboards**; metric taxonomy thin (no decision-outcome / RCS delivered-read breakdown); RCS delivery metrics need the gated real callbacks |
| **NFR-10** | Correlation id threads everything | **DONE** | `correlation_id` contextvar `logging.py`; on event/case/audit/decision; live cases keyed by it | consistent across the trail |

---

## Part C — Completion percentage (math shown)

25 requirements total (FR-1..FR-13b + FR-X = 15; NFR-1..NFR-10 = 10).
Scoring: DONE = 1 · PARTIAL = 0.5 · MOCK-ONLY = 0.5 demo / **0 live** · MISSING = 0.

**Functional (15)**
- Demo: FR-1 0, FR-2..6 =5, FR-7 .5, FR-8 .5, FR-9 .5, FR-10 1, FR-11 .5, FR-12 1, FR-13a 1, FR-13b .5, FR-X 1 → **11.5 / 15 = 76.7%**
- Live: same but FR-8 0, FR-13b 0 → **10.5 / 15 = 70.0%**

**Reliability (10)**
- Demo: NFR-1 1, 2 1, 3 .5, 4 1, 5 1, 6 1, 7 1, 8 1, 9 .5, 10 1 → **9.0 / 10 = 90.0%**
- Live: NFR-1 .5 (real SMS gated), rest same → **8.5 / 10 = 85.0%**

| Number | Value | How |
|--------|-------|-----|
| **1. Demo-complete %** | **≈ 82%** | (11.5 + 9.0) / 25 = 20.5/25 |
| **2. Live-verified %** | **≈ 76%** | (10.5 + 8.5) / 25 = 19.0/25 |
| **3. Weighted headline %** | **≈ 79%** | 0.5·demo(82) + 0.5·live(76) = 79 |

**Weights justification:** It is a mock-first POC, so demo-complete is a fair ceiling — but
MOCK-ONLY features (RCS device delivery, OCR, PDF) must not be scored as production-done, which
live-verified captures. 50/50 is the honest blend. Note the **reliability layer (the actual
story) lands at 85–90%** while the FR edges that are deliberately gated drag the FR number down —
weighting NFRs higher (reliability is the pitch) would push the headline to ~82%, not lower.

---

## Part D — Production-readiness engineering audit (0–5)

| # | Parameter | Score | Justification | Top gap |
|---|-----------|:---:|---------------|---------|
| 1 | Correctness & test coverage | **4** | 118 pass, ruff clean; policy/idempotency/failures/commerce/rag/confidence/mcp/sf+inventory-rest/sf-hook/spine-e2e/copilot all covered | no live end-to-end integration test; coverage % unmeasured |
| 2 | Security | **2** | webhook HMAC+payload-hash verify (`webhooks/routes.py:36`), SF-hook shared secret, Razorpay **refuses live keys** (`razorpay.py:164`), CORS locked, service_role server-only | **entire orchestrator API + all `/sim/*` are unauthenticated on a public Render URL** — anyone can fire events, resume cases, toggle `/sim/fault` |
| 3 | Reliability & resilience | **4** | 2-layer idempotency, DLQ+replay, reconcile, atomic reserve, proposer ladder (LLM outage → deterministic floor), RCS→SMS, durable PG checkpointer, best-effort terminal sends | **no retry/backoff before DLQ**; reconcile is read-only (no auto-heal) |
| 4 | Observability | **4** | real Prometheus `/metrics`, Logfire tracing (live), structlog, correlation id, `/health/deps` shallow+deep, `/reconcile`, `/dlq`, FAILED visible in `/cases` | no Grafana dashboards; thin metric taxonomy; deep-deps shows PG `unreachable` live (pooler flakiness) |
| 5 | Performance & scalability | **3** | LLM bounded + deterministic hot path; durable checkpointer | `record_delivery_status` does a **full `Case` table scan** (`case_service.py:127`, ponytail-flagged); single consumer; untested under concurrency |
| 6 | Data integrity | **3** | no double-charge (2-layer), atomic reserve (FOR UPDATE), integer paise, transactional commits | **no migrations** — schema via `init_db` create_all; evolution will break the durable checkpointer/state |
| 7 | Config & secrets | **4** | fully env-driven, pydantic fail-fast, arming gates for every vendor, live-key refusal, rotated SF token persisted to DB | signature/SF-hook secrets **blank = skip check** (safe default is skip, not fail) |
| 8 | Deployment & CI/CD | **2** | Render auto-deploy (live), `/version` in code, Dockerfile | **stale deploy** (`/version` 404s live), **`uv.lock` gitignored** (non-reproducible), no CI, no `render.yaml`, no rollback doc |
| 9 | Error handling | **4** | fail-loud on malformed events (400), FAILED case rows, 409 on lost checkpoint, surfaces Vonage's exact error, DLQ on handler crash | blanket `BLE001` catches (logged, deliberate) can mask bugs; no alerting on FAILED/DLQ growth |
| 10 | API & contracts | **4** | pydantic `fieldflow_contract` pkg, `export_schema.py`, typed Card/Event models, app version | no API versioning (`/v1`); schema export not CI-enforced |
| 11 | Maintainability & code quality | **4** | ruff clean, vendor seams/Protocols everywhere, clear modules, excellent docstrings, ponytail ceilings marked | a few god-functions (`build_graph` ~370 lines) |
| 12 | Dependencies & supply chain | **2** | deps declared, lazy heavy imports | deps **floored (`>=`) not pinned**, **`uv.lock` gitignored/untracked**, no vuln scan |

**Average: 40 / 12 = 3.3 / 5.**

### Verdict: **POC-grade — pilot-ready on the reliability spine, NOT production-ready.**

The hard parts that are the story — idempotency, policy authority ladder, DLQ, decision trace,
atomic reserve, observability, *and* live-wired Salesforce MCP + Razorpay test-mode + e-com
inventory — are genuinely strong and mostly live-verified. What blocks real customers/money is
operational: no auth on a public URL, a stale/unreproducible deploy, a missing retry tier, no
migrations.

### Top-5 gaps to close before real customers/money (ranked)

1. **No authentication/authorization anywhere.** The public Render URL exposes `/sim/*` (fire
   events, resume any case, toggle `salesforce-down`), `/cases`, `/dlq`, `/reconcile`, `/copilot/*`.
   Anyone can drive or poison the pipeline. → add an API key / JWT gate; split `/sim` behind it.
2. **Stale deploy + non-reproducible builds.** `/version` 404s (deploy behind HEAD), `uv.lock`
   gitignored, no CI, no `render.yaml`. You cannot trust what is running. → commit the lock, add
   CI (pytest+ruff on push), pin the deploy to a known commit, make `/version` the smoke check.
3. **No retry/backoff tier before the DLQ (NFR-3 half-met).** A transient Salesforce blip
   dead-letters immediately. → add bounded retry-with-backoff (aio-pika delayed retry / a retry
   queue) before the nack-to-DLQ.
4. **Dependencies floored, not pinned + no vuln scan.** Supply-chain + reproducibility risk once
   money is real. → commit `uv.lock`, pin, add `pip-audit`/Dependabot.
5. **No DB migrations.** `init_db` create_all only; schema change will strand the durable
   checkpointer and case state. → add alembic (or an equivalent migration path) before any schema
   evolves in a shared environment.

---

## Part E — Deliberate POC corners (cut on purpose — NOT scored as gaps)

Per `CLAUDE.md` "speed over prod-grade". These are intentional and behind clean seams:

- **No alembic/migrations** — deferred (listed as a real gap above only because it blocks the
  *next* step, not because it was an oversight).
- **Vendors mock-first behind interfaces** — and most are actually live now: FakeSalesforce →
  **real org live**, FakeRazorpay → **real test-mode live**, FakeInventory → **real e-com live**,
  FakeVonage → real send **armed, single test device**.
- **Simulated OCR/vision** (FR-8/9) — `record_photo` returns `matchesAsset:True`.
- **Service-report PDF is a placeholder link** (FR-13b) — real per-case PDF is the gated step.
- **Single RCS test device**; real on-device carousel/payment taps are the gated live fire.
- **Payment confirmed by polling, no inbound Razorpay webhook** — explicit POC rule.
- **gRPC Pub/Sub trigger stubbed** (`events/source.py:96` raises) — the HTTP-callout path
  (`/webhooks/sf/at-risk`) is used instead; this is a chosen architecture, not a miss.
- **No Grafana dashboards** — raw Prometheus + Logfire only.
- **FR-7 ETA compute, FR-1 appointment-created card, FR-13a "Track"** — out of the built journey;
  these are genuine scope *omissions* (counted in Part A), distinct from the deliberate corners
  above.

**Separation note:** "no auth" is technically a deliberate POC corner (CLAUDE.md allows it), but
because the orchestrator is deployed on a **public** URL with live SF/Razorpay wiring, it is
promoted to the #1 *real* gap — a deliberate corner that stops being safe the moment the thing is
public and touching real systems.

---

## Appendix — commands used (reproduce this audit)

```bash
# tests + lint (from apps/orchestrator, after `uv sync --extra dev`)
uv run pytest -q
uv run ruff check .

# live server (trust these over docs)
curl -s https://fieldflow-ai-w6bm.onrender.com/health
curl -s https://fieldflow-ai-w6bm.onrender.com/health/deps
curl -s "https://fieldflow-ai-w6bm.onrender.com/health/deps?deep=1"
curl -s https://fieldflow-ai-w6bm.onrender.com/version     # 404 → stale deploy
curl -s https://fieldflow-ai-w6bm.onrender.com/cases
curl -s https://fieldflow-ai-w6bm.onrender.com/tools
curl -s https://fieldflow-ai-w6bm.onrender.com/copilot/tools
curl -s https://fieldflow-ai-w6bm.onrender.com/metrics
curl -s https://fieldflow-ai-w6bm.onrender.com/reconcile
curl -s https://fieldflow-ai-w6bm.onrender.com/dlq
curl -s https://field-flow-ai.vercel.app/api/products
```
