# Production-Readiness Remediation

## 1. Task

- **Name:** Production-readiness remediation — close the audit findings before a pilot.
- **Status:** Planned (no code written yet).
- **Started:** 2026-10-21
- **Last updated:** 2026-10-21
- **Source audit:** [`ai-system-production-readiness-audit.md`](ai-system-production-readiness-audit.md)
  (HEAD `26dcc04`). Every task below maps to a finding ID in that report.

---

## 2. What you asked for

> "We have to start with the work to fix all things we found soon. Make a proper plan according to
> the audit report content and record it so later we can work on it."

So: a recorded, actionable remediation plan — grouped by priority, each item tied to an audit
finding, with the files it touches, the smallest fix that holds, who should do it, and what *you*
(the tech lead) must supply from your side.

**Guardrails carried over from the audit + `CLAUDE.md`:**
- This stays a POC — fixes are the *smallest change that closes the risk*, not production gold-plating.
- Nothing here weakens the one idea: **AI proposes, deterministic policy decides, humans approve.**
- The audit itself is not re-opened; this plan only acts on its findings.

---

## 3. Open questions (my recommendation first; your answer goes here when you decide)

| # | Question | My recommendation | Your answer |
|---|----------|-------------------|-------------|
| OQ1 | Auth mechanism for the API? | **Shared API key** in an `X-API-Key` header, checked by one middleware. It's a single-operator panel — a full JWT/OAuth user system is overkill (YAGNI). Upgrade to JWT only when there are real multiple users. | **Yes — shared API key** (2026-10-22). |
| OQ2 | What to do with `/sim/*` in production? | **Mount `/sim/*` only when `app_env != "production"`** (so the live deploy simply doesn't have them), AND still require the API key everywhere else. Keeps the demo twin for local/staging, removes the "anyone can toggle Salesforce-down" surface in prod. | **Agreed, with one correction:** drop the pure-simulation routes in prod, but **`/sim/dlq/replay` is an ops recovery tool, not a sim** — move it to `/ops/dlq/replay` and keep it (behind the API key). (2026-10-22) |
| OQ3 | Retry policy before the DLQ? | **3 retries at 5 s → 30 s → 120 s backoff**, then dead-letter. Native RabbitMQ (retry queue + per-message TTL + `x-death` count) — no new service. | **Default accepted: 3 retries, 5/30/120 s** (2026-10-22). |
| OQ4 | Order of work — migrations before or after the security fixes? | **Security + retry first** (they block a pilot and are low-risk), migrations in Phase 1 (they touch the durable checkpointer — do them carefully, not under pilot pressure). | **Default accepted: security + retry first** (2026-10-22). |
| OQ5 | Live sandbox e2e — where to run it and who completes the payment? | **Run it locally against the real Razorpay *test* key + real SF reads** (isolated, doesn't pollute the public deploy or send a real RCS), and **you tap the test payment link once** (the real gateway polls Razorpay — a simulated "paid" won't capture). I drive everything else and read back the capture. | **Yes — local + real Razorpay test; you tap once** (2026-10-22). |

> **Per the explain-and-wait rule: I will not start coding any phase until you answer OQ1–OQ4.** The
> live e2e (OQ5) is gated on your answer too, because it fires real sends.

---

## 4. Plan

Three phases, ordered by what blocks a pilot. Each finding → the smallest fix that closes it.

### Phase 0 — Pilot blockers (P0/P1) — do first

| Finding | Fix (smallest that holds) | Files to touch | Effort |
|---------|---------------------------|----------------|--------|
| **AI-SEC-01** No auth on public API | One ASGI middleware checking `X-API-Key` against an env secret; allowlist only `/health`, `/ready`, `/health/deps`, `/version`, `/metrics` (monitors need them). Mount `/sim/*` only when not production (OQ2). | new `app/auth.py`; `app/main.py` (add middleware + conditional sim mount); `app/config.py` (`api_key`, `sim_enabled`); `apps/control-panel/src/lib/api.ts` (send the key) | **M** |
| **AI-SEC-02** Copilot unauth + no rate limit | Exposure closed by AI-SEC-01. Add a simple in-memory per-window call cap + daily token budget on `/copilot/chat`; keep tools read-only. | `app/api/routes.py` or small `app/copilot/limit.py` | **S** |
| **AI-REL-01** No retry tier before DLQ | RabbitMQ retry queue: on handler failure, republish to `events.retry` (per-message TTL) which dead-letters back to `events`; count attempts via the `x-death` header; only nack to `events.dlq` after N (OQ3). | `app/queue/broker.py`; `app/main.py` (handler wiring) | **M** |
| **AI-SEC-03** Secrets fail open when blank | Pydantic boot validator: when `app_env == "production"`, a blank `vonage_signature_secret` or `sf_hook_secret` is a **fatal** boot error. Skip stays the local/dev default. | `app/config.py` | **S** |

**Alternatives rejected:** full OAuth/JWT user auth (overkill for one operator); an external retry
scheduler/Celery (RabbitMQ TTL+DLX does it natively, no new service).

### Phase 1 — Real-money / real-customer blockers (P2)

| Finding | Fix | Files | Effort |
|---------|-----|-------|--------|
| **AI-DATA-01** No migrations | Add Alembic; generate the initial migration from current models; stop relying on `create_all` in the Postgres (prod) path (keep it for the SQLite test engine). | new `alembic/`, `alembic.ini`; `app/db/session.py` | **M** |
| **AI-SUP-01** Non-reproducible build, no CI | Un-ignore + commit `uv.lock`; add GitHub Actions CI (pytest + ruff on push); add `pip-audit`. | `.gitignore`; new `.github/workflows/ci.yml`; commit `uv.lock` | **S** |
| **AI-OUT-01** No moderation on customer text | Deterministic pre-send check on the model's `customer_message` (length cap, strip control chars / obvious injected instructions); fall back to the warm template on fail. | `app/llm/proposer.py` or new `app/llm/sanitize.py` | **S** |
| **AI-TEST-01** No authz/injection/eval tests | Add authz tests per route (after auth lands); a prompt-injection set for proposer + copilot; a documented manual live-sandbox e2e checklist. | `tests/test_auth.py`, `tests/test_injection.py` | **M** |
| **AI-OBS-01** Thin metrics, no alerts | Add latency histogram + provider-fallback + decision-outcome counters; wire one alert on FAILED-case / DLQ-depth growth (Logfire alert or UptimeRobot keyword on deep `/health/deps`). | `app/telemetry.py`; graph nodes | **S/M** |

### Phase 2 — Backlog (P3) — after the pilot gate

| Finding | Fix | Files |
|---------|-----|-------|
| **AI-PERF-01** Full `cases` scan per callback | Store/index `message_uuid`; direct lookup (needs migrations first). | `app/db/models.py`, `app/services/case_service.py` |
| **AI-DOM-01** No GST on quotes | Add a tax line to `build_quote` (env GST rate). | `app/commerce/service.py`, `app/config.py` |
| **AI-INT-01** Payment poll-only | Add `/webhooks/razorpay` with signature verify (keep the poller as backstop). | `app/webhooks/routes.py` |
| — | Checkpoint TTL/prune for CLOSED/REJECTED cases. | `app/graph/checkpointer.py` |
| — | Replace simulated OCR with a real vision call (FR-8/9). | `app/services/case_service.py` |

---

## 5. Tasks

Ticked off as we go. IDs map to §4.

**Phase 0 — pilot blockers**
- [x] P0-1 (AI-SEC-01) API-key middleware + health/metrics allowlist ✅ 2026-10-22
- [x] P0-2 (AI-SEC-01/OQ2) mount `/sim/*` only when `SIM_ENABLED` (default on; false in prod) ✅ 2026-10-22
- [x] P0-2b (OQ2) carve the real operator controls into `/ops/*` (`/ops/approve`, `/ops/dlq/replay`), always mounted behind the key; panel repointed ✅ 2026-10-22
- [x] P0-3 (AI-SEC-01) control panel sends the API key ✅ 2026-10-22
- [x] P0-8 (AI-BEH-01) activate policy's working-hours check (feed `hour` from each slot) + drop unparseable times; SLA-window/past deliberately not auto-applied (120-min window is incoherent for real multi-day availability) ✅ 2026-10-22
- [x] P0-9 (AI-BEH-02) guard the LLM `customer_message` — block money claims (free/discount/price/₹), control chars, over-length, empty; fall back to the warm template ✅ 2026-10-22
- [x] P0-4 (AI-SEC-02) copilot per-minute + per-day call caps (cost guard; refuses before spending Groq tokens) ✅ 2026-10-22
- [x] P0-5 (AI-REL-01) RabbitMQ retry tier: 3 backoff queues (5s/30s/120s) before the DLQ, attempt-counted via `x-retry-count` ✅ 2026-10-22
- [x] P0-6 (AI-SEC-03) fail-closed secret validator — blank API_KEY/VONAGE_SIGNATURE_SECRET/SF_HOOK_SECRET aborts boot when APP_ENV=production ✅ 2026-10-22
- [x] P0-7 authz tests — middleware gate (blank off / enforced / allowlist locked / any non-allowlisted route gated) ✅ 2026-10-22

**Phase 1 — money/customer blockers**
- [x] P1-1 (AI-DATA-01) Alembic + initial migration ✅ 2026-10-22
- [x] P1-2 (AI-SUP-01) commit `uv.lock`, add CI (pytest+ruff), add pip-audit ✅ 2026-10-22
- [x] P1-3 (AI-OUT-01) customer-message pre-send check — DONE via P0-9 (AI-BEH-02 superseded AI-OUT-01) ✅ 2026-10-22
- [x] P1-4 (AI-TEST-01) prompt-injection test set + manual live-e2e checklist ✅ 2026-10-22
- [x] P1-5 (AI-OBS-01) full Logfire: one connected trace per case (SF→close), LLM token spans,
  SQL+logs in-trace, metrics→Logfire (Prometheus dropped), Discord alert. See
  [`observability-logfire.md`](observability-logfire.md). Code shipped 2026-10-23 (152 tests); live
  token/UI pending. ✅
- [ ] P1-6 (AI-BEH-03) groundedness/faithfulness check on the proposal + an offline eval set gated in CI (also covers model/provider drift)

**Phase 2 — backlog**
- [ ] P2-1 (AI-PERF-01) index `message_uuid`
- [ ] P2-2 (AI-DOM-01) GST line on quotes
- [ ] P2-3 (AI-INT-01) Razorpay inbound webhook
- [ ] P2-4 checkpoint TTL/prune
- [ ] P2-5 real vision/OCR

**Verification task (separate, gated on OQ5)**
- [ ] V-1 live sandbox e2e: drive at-risk → offer → (device pays test link) → capture read back → SF payment record; record the result in §6.

---

## 6. Updates

- **2026-10-21** — Plan created from the AI-system audit (`26dcc04`). No code yet. Audit report moved
  into `docs/specs/`. Awaiting answers to OQ1–OQ5 before Phase 0 starts.
- **2026-10-22** — Decisions in: OQ1 shared API key; OQ2 drop simulation routes in prod but keep DLQ
  replay as `/ops/dlq/replay` (added task P0-2b); OQ3 3 retries 5/30/120 s; OQ4 security+retry first;
  OQ5 live e2e locally against real Razorpay test, user taps once. Still no code — Phase 0 starts on
  an explicit "go".
- **2026-10-22** — Two corrections after a tech-lead code challenge: (1) `/sim` is **not** dummy — the
  panel uses `/sim/approve` (real Level-3 human approval) and `/sim/dlq/replay` (real ops); P0-2b now
  carves both into `/ops/*` kept in prod, drops only the demo/twin sims. (2) Audit extended with three
  **AI-behaviour** findings — AI-BEH-01 (policy time-checks are dead code; slot times unvalidated),
  AI-BEH-02 (unguarded customer message), AI-BEH-03 (confidence ≠ correctness). Added tasks P0-8, P0-9
  (pilot blockers) and P1-6. Audit §23A has the detail.
- **2026-10-22** — **P0-1 + P0-3 shipped** (API-key gate + panel sends the key). New `app/auth.py`,
  `tests/test_auth.py`; full suite 132 passed, ruff + panel tsc clean. Gate is inert until `API_KEY`
  / `VITE_API_KEY` are set. Walkthrough in §7. Next: P0-2/P0-2b (`/ops` split), then P0-8.
- **2026-10-22** — **P0-2 + P0-2b shipped.** New `app/ops/routes.py` (`/ops/approve`,
  `/ops/dlq/replay`) always mounted; `/sim/*` now gated behind `SIM_ENABLED` (default true, set false
  in prod). Panel repointed. 132 passed, ruff + tsc clean. Default-on so current demos are
  unaffected. Walkthrough in §7. Next: P0-8 (policy time-validation fix).
- **2026-10-22** — **AI-SEC-01 CLOSED and verified live.** Pushed + deployed (Render `6b7d4cb`);
  `API_KEY` set on Render, `VITE_API_KEY` on Vercel. Verified: `/cases`, `/dlq`, `/copilot/tools`
  → 401 without a key and with a wrong key; `/health` → 200 (allowlist); `/ops/approve` → 401 (gated,
  route exists). The Critical P0 blocker is resolved in production.
- **2026-10-22** — **P0-8 shipped** (AI-BEH-01). Policy's working-hours check is now fed real data
  (`hour` derived from each slot's ISO `start`/`label`), so an out-of-hours slot is rejected;
  unparseable times are dropped before the carousel (no more DLQ crash). New `slot_time_fields` in
  `salesforce.py`; policy gained a past-slot branch (available to explicit callers). **Refinement
  found:** policy's `startMinutes > slaWindowMinutes` (120 min) check is incoherent for real
  availability (genuine slots are days out) — so it is NOT auto-applied; logged as a follow-up to
  redefine the SLA check. 135 passed, ruff clean. Walkthrough in §7.
- **2026-10-22** — **P0-9 shipped** (AI-BEH-02). New `sanitize_customer_message` in `proposer.py`,
  called from `parse_proposal`: the model's customer message is kept only if it carries no money
  claim (free/discount/price/refund/₹/rupees/cost), no control chars, and is a sane length — else the
  warm deterministic template (which never mentions money) is used. 137 passed, ruff clean.
  Walkthrough in §7. Next: P0-4 (copilot rate-limit).
- **2026-10-22** — **P0-4 shipped** (AI-SEC-02, final piece). New `app/copilot/limit.py`
  (`CopilotLimiter`: per-minute sliding window + per-day budget, 0 disables); `/copilot/chat` refuses
  with a friendly message before spending Groq tokens when over a cap. Defaults 10/min, 200/day
  (`COPILOT_RATE_PER_MIN`/`_PER_DAY`). 140 passed, ruff clean. **AI-SEC-02 now closed.** Walkthrough
  in §7. Next: P0-5 (retry tier before DLQ).
- **2026-10-22** — **P0-5 shipped** (AI-REL-01). Broker now retries a failed event 3× with backoff
  (5s/30s/120s) via fixed-TTL retry queues that dead-letter back to `events`, and only then nacks to
  `events.dlq`. Attempt count rides in `x-retry-count`; a replayed DLQ message starts fresh. New
  `next_retry_key` + `RETRY_TIERS` in `broker.py`; `tests/test_broker_retry.py`. 142 passed, ruff
  clean (RabbitMQ TTL wiring verified live, not in unit tests). Walkthrough in §7. Next: P0-6
  (fail-closed secrets in prod).
- **2026-10-22** — **P0-6 + P0-7 shipped → PHASE 0 COMPLETE (9/9).** P0-6: a pydantic boot validator
  aborts startup if `APP_ENV=production` and `API_KEY`/`VONAGE_SIGNATURE_SECRET`/`SF_HOOK_SECRET` are
  blank (fail-closed, AI-SEC-03); outside production blanks stay allowed. P0-7: authz tests lock the
  allowlist + prove any non-allowlisted route is gated. `tests/test_config.py` + extended
  `test_auth.py`. 146 passed, ruff clean. **All P0 pilot-blockers are closed.** Walkthroughs in §7.
  ⚠ When you set `APP_ENV=production` on Render, you MUST also set those three secrets or boot fails.
  Next session: Phase 1 (P1-1 Alembic → P1-2 CI/lock → P1-3 … ) + V-1 live e2e.
- **2026-10-22** — **P1-1 shipped** (AI-DATA-01). Added Alembic (async `env.py`), the initial
  migration for our 5 tables, and switched the Postgres boot path off `create_all` (SQLite dev +
  tests keep it). **OQ-A answered: DB is disposable** (all test data; everything reseeds from
  `app/data/catalog.json` + the seed scripts — nothing to save locally). **OQ-B answered: yes** —
  Render runs `alembic upgrade head` before serving, baked into the Docker image via
  `docker-entrypoint.sh` (ENTRYPOINT migrates, then `exec`s uvicorn) — because Render's Pre-Deploy
  Command is paid-only. The migration's `env.py` has
  an `include_object` guard so autogenerate can NEVER touch LangGraph's `checkpoints*` tables or the
  RAG `knowledge_chunks` (the checkpointer-wipe risk is designed out). 146 passed, ruff clean;
  migration round-trips (upgrade→downgrade) on a throwaway SQLite. Walkthrough in §7.
  **USER action items (strict order — Auto-Deploy is On Commit):** (1) run `alembic stamp head` once
  locally against the live Supabase DB; (2) THEN commit+push — the push auto-deploys and the Docker
  entrypoint migrates on boot. No Render dashboard change needed. See playbook §9c.
- **2026-10-22** — **P1-2 shipped** (AI-SUP-01). Un-ignored + committed `uv.lock` (reproducible
  builds); added GitHub Actions CI (`.github/workflows/ci.yml`) running `uv sync --locked`
  (proves the lock is honest) → ruff → pytest on Python 3.12, plus a **non-blocking** `pip-audit`.
  All steps validated locally in their exact CI form: 146 passed, ruff clean, lock consistent.
  **pip-audit already found CVEs:** `pypdf 6.19.0` (direct dep → fixed in 6.21.1) and `pillow 12.3.0`
  (transitive → 13.0.0). Non-blocking by design, so they report without failing CI — **follow-up:
  bump `pypdf>=6.21.1`** (one line) and re-check pillow's parent. Walkthrough in §7.
- **2026-10-22** — **P1-4 shipped** (AI-TEST-01). New `tests/test_injection.py` (6 adversarial tests,
  all offline) treating the LLM as an untrusted boundary: proposer can't smuggle a part past
  `parse_proposal` (delay strips any part; a parts job strips an invented partNo but keeps a real
  catalog one), an injection-framed money promise falls back to the template, and the copilot harness
  confines a hostile model — it can't invoke a tool that wasn't offered, a poisoned tool *result*
  can't escalate to a write (no such tool to route to), and the `_MAX_STEPS` cap stops a runaway
  loop. Plus **playbook §9e** — the manual live-sandbox e2e checklist (V-1 / OQ5). **152 passed**
  (+6), ruff clean. Walkthrough in §7. Next: P1-5 (metrics/alerts), P1-6 (groundedness eval), V-1 run.
- **2026-10-22** — **CVE follow-up closed.** Bumped `pypdf` → 6.21.2 (direct, pyproject); upgraded
  `pillow` → 13.0.0, `certifi`, `nltk` (transitive, lockfile-only). `pip-audit` now reports **no known
  vulnerabilities**. 152 pass, ruff clean, lock consistent.

---

## 7. Explanation

_Grows as each phase lands._

### P0-1 + P0-3 — API-key gate (shipped 2026-10-22)

**What changed.** Every orchestrator route now requires a shared secret in the `X-API-Key` header,
except the monitor allowlist (`/health`, `/ready`, `/health/deps`, `/version`, `/metrics`). The
control panel sends the key automatically.

**Why.** Closes AI-SEC-01 (Critical) — the public URL let anyone read cases, drive `/sim`, and hit
the copilot.

**How it works.** `app/auth.py` adds `ApiKeyMiddleware` (Starlette `BaseHTTPMiddleware`). On each
request: if the key is blank (dev/test) OR it's a CORS preflight (`OPTIONS`) OR the path is in
`OPEN_PATHS` → pass through; else constant-time compare (`hmac.compare_digest`) the `X-API-Key`
header against `settings.api_key` → 401 JSON on mismatch. Wired in `main.py` **before** CORS so CORS
stays outermost (preflight works; 401s carry CORS headers). The panel (`lib/api.ts`) attaches the
header from `VITE_API_KEY` on every call; blank → no header.

**Files.** `app/auth.py` (new), `app/config.py` (`api_key`), `app/main.py` (wire middleware),
`apps/control-panel/src/lib/api.ts` (send header), both `.env.example` files, `tests/test_auth.py`
(new, 3 tests).

**Decisions.** Shared API key over JWT (OQ1 — single operator, YAGNI). Blank key = gate OFF, matching
the project's mock-first secret convention, so tests + local dev are untouched (the live key is set
in env, never in code). Making a blank key fatal in production is deferred to P0-6 on purpose.

**Tests / verification.** `tests/test_auth.py` 3/3 pass; full suite **132 passed** (was 129);
`ruff` clean; panel `tsc --noEmit` clean.

**Edge cases / limitations.** The gate is inert until `API_KEY` is set on the server **and**
`VITE_API_KEY` in the panel (see activation steps). It is one shared key, not per-user identity
(fine for one operator; upgrade to JWT when there are many).

### P0-2 + P0-2b — split operate from simulate (shipped 2026-10-22)

**What changed.** The two real operator controls that were hiding under `/sim` moved to a new
`/ops/*` router (`/ops/approve`, `/ops/dlq/replay`), always mounted behind the API key. The rest of
`/sim/*` (fire event, fault toggle, forge reply/payment/photo/delivery) is now mounted only when
`SIM_ENABLED` is true; set `SIM_ENABLED=false` on a production deploy and those routes vanish.

**Why.** AI-SEC-01 defense-in-depth: `/sim/fault` ("pretend Salesforce is down") and fake-event
injection must not exist in production, but the human-approval button and DLQ replay must. Dropping
all of `/sim` would have killed the latter — so they were carved out first.

**How it works.** `app/ops/routes.py` holds the two handlers (same logic as before, just relocated).
`app/main.py` always includes `ops_router`; it includes `sim_router` only `if settings.sim_enabled`.
`config.sim_enabled` defaults True (current demos untouched). The panel calls `/ops/approve` and
`/ops/dlq/replay`; its other sim calls are demo-only and simply won't exist when sim is off.

**Files.** `app/ops/__init__.py` + `app/ops/routes.py` (new), `app/sim/routes.py` (two handlers +
unused telemetry import removed, docstring updated), `app/config.py` (`sim_enabled`), `app/main.py`
(wiring), `apps/control-panel/src/lib/api.ts` (repoint), `apps/orchestrator/.env.example`.

**Decisions.** `sim_enabled` default **on** (non-breaking, mock-first convention) over defaulting off
(would silently break the live demo's approve/replay-era muscle memory and demo buttons). Kept the
handlers' logic byte-for-byte to avoid behaviour drift — pure relocation.

**Tests / verification.** 132 passed; ruff clean; panel `tsc` clean; `SIM_ENABLED=false` confirmed to
parse to `sim_enabled=False`; `app.main` imports with both routers wired.

**Edge cases / limitations.** When `SIM_ENABLED=false`, the panel's demo buttons (fire/fault/forge)
404 — intended. Approve + DLQ replay keep working. No per-route authz beyond the single API key yet.

### P0-8 — activate the policy's time validation (AI-BEH-01) (shipped 2026-10-22)

**What changed.** Every proposed slot now gets its start `hour` (in the business timezone) attached
before policy runs, so policy's working-hours check (dead until now) actually fires — an out-of-hours
slot is rejected. A slot whose time can't be parsed is dropped before the carousel instead of
crashing the case to the DLQ at reschedule.

**Why.** AI-BEH-01: policy *claimed* to check SLA/working-hours/warranty, but those branches only ran
if the slot carried `startMinutes`/`hour` keys, which nothing ever set — so the time of every offered
slot went unvalidated. The LLM could propose a 2 a.m. or malformed slot and policy waved it through.

**How it works.** New `salesforce.slot_time_fields(start, label, tz)` derives `{startMinutes, hour}`
from a slot's ISO `start` or its `label` (returns `None` if unparseable). `generate_options` attaches
`hour` to each candidate and drops the `None` ones; policy's existing `hour` check then removes
out-of-hours slots. Policy also gained a past-slot branch (`startMinutes < 0`), available to any
caller that passes `startMinutes`.

**Files.** `app/tools/salesforce.py` (`slot_time_fields`), `app/policy/__init__.py` (past branch +
docstring), `app/graph/build.py` (enrich + drop), `tests/test_policy.py`,
`tests/test_availability_slots.py` (3 new tests).

**Important decision.** I did **not** auto-apply the `startMinutes > slaWindowMinutes` (120 min)
check to availability slots. Genuine Field Service openings are legitimately days out, so that check
would reject *every* real slot — it's a semantic mismatch (the SLA is a response-time target, not
"book within 2 hours"). Enforcing only the coherent, clock-stable check (working hours) + dropping
malformed times is the correct, non-breaking subset. Redefining the SLA check is logged as follow-up.

**Tests / verification.** 135 passed (was 132); ruff clean. New tests: policy removes out-of-hours +
past slots; `slot_time_fields` returns the right hour and `None` on garbage; an out-of-hours real
slot (01:30 IST) is dropped from the offer end-to-end.

**Edge cases / limitations.** A past-but-in-hours slot from a relative canned/LLM label is not caught
(no `startMinutes` auto-applied); real FSL slots are future by construction, so this only matters on
the canned fallback. The SLA-window check stays a unit-tested capability but is not wired to slots.

### P0-9 — guard the customer-facing message (AI-BEH-02) (shipped 2026-10-22)

**What changed.** The warm `customer_message` the LLM writes for the RCS offer is now checked before
it's trusted: if it makes a money claim (free / no charge / discount / refund / ₹ / rupees / price /
cost), contains control characters, is over-length, or is empty, it's replaced with the deterministic
warm template (which never mentions money).

**Why.** AI-BEH-02: the policy fence guards the system's *actions*, not the AI's *words*. The model
could promise "this repair is completely free" on a chargeable job and it would go to the customer
verbatim — a broken promise with real cost. Pricing belongs to the quote card, never a chatty line.

**How it works.** `sanitize_customer_message(candidate, fallback)` in `proposer.py` strips control
chars, then rejects (→ fallback) on empty / over-length / a `_MONEY_CLAIM` regex hit. `parse_proposal`
(the single choke point for LLM output) calls it with the reason-aware template as the fallback.

**Files.** `app/llm/proposer.py` (regex + `sanitize_customer_message` + wired into `parse_proposal`),
`tests/test_llm.py` (2 new tests).

**Decisions.** Forbid *all* cost-talk in the offer rather than trying to judge whether a promise is
true — simpler and safer, and a false positive just yields the (fine) template. Enforced at
`parse_proposal` so both live providers (Groq/Gemini) are covered; the deterministic path is already
safe by construction.

**Tests / verification.** 137 passed (was 135); ruff clean. New tests: a "completely free" message
falls back to the template; `sanitize_customer_message` keeps a clean message and rejects
money/empty/over-length.

**Edge cases / limitations.** Keyword-based, English-only — a cleverly-worded promise that avoids the
listed words could slip through (the LLM is instructed not to, and actions are still fenced). A
legitimate message mentioning cost is blocked (acceptable — the template is sent instead).

### P0-4 — copilot rate limit (AI-SEC-02) (shipped 2026-10-22)

**What changed.** `/copilot/chat` now enforces a per-minute burst cap (default 10) and a per-day
budget (default 200). Over either, it returns a friendly "busy, try again" message and makes **no**
Groq call. `0` disables a cap.

**Why.** The API key (P0-1) stopped anonymous abuse, but nothing capped spend — a runaway loop or a
leaked key could burn the Groq budget (cost DoS). This closes the remaining half of AI-SEC-02.

**How it works.** `CopilotLimiter.allow()` (in `app/copilot/limit.py`) keeps a 60-second sliding
window of call timestamps plus a UTC-day counter; the endpoint checks it before building the Groq
client. In-process, one shared instance — fine for the single Render dyno.

**Files.** `app/copilot/limit.py` (new), `app/api/routes.py` (instantiate + check + logger),
`app/config.py` (`copilot_rate_per_min`, `copilot_rate_per_day`), `tests/test_copilot_limit.py` (new).

**Decisions.** In-memory over Redis (one process; marked as the upgrade path). Friendly 200-body over
a 429 so the panel renders it cleanly, matching the copilot's existing error handling.

**Tests / verification.** 140 passed (was 137); ruff clean. Tests: per-minute burst blocks then
recovers; per-day cap blocks then resets next UTC day; `0` disables.

**Edge cases / limitations.** Global (not per-user) — one noisy caller can exhaust the shared budget;
fine for a single-operator POC. Counters reset on process restart. Multi-instance needs Redis.

### P0-5 — retry tier before the DLQ (AI-REL-01) (shipped 2026-10-22)

**What changed.** A failed event is now retried 3× with backoff (5s → 30s → 120s) before it
dead-letters. Previously any handler exception went straight to `events.dlq`.

**Why.** A transient Salesforce/DB blip was permanently parking events in the DLQ, needing a manual
replay. NFR-3 ("retry → backoff → DLQ") was only half-built.

**How it works.** A new `fieldflow.retry` exchange feeds three fixed-TTL queues
(`events.retry.5s/30s/120s`), each dead-lettering back to the main `events` queue when its TTL
elapses. On failure, `on_message` reads `x-retry-count`, picks the next tier via `next_retry_key`,
republishes with the count incremented, and acks the original; once 3 retries are spent it nacks to
`events.dlq`. A replayed DLQ message carries no `x-retry-count`, so it gets a fresh set of retries.

**Files.** `app/queue/broker.py` (constants, `next_retry_key`, retry topology in `connect`, retry
logic in `on_message`), `tests/test_broker_retry.py` (new).

**Decisions.** Three fixed-TTL queues over a single per-message-TTL queue — the latter has a
head-of-line-blocking bug (a 120s message stalls a 5s one behind it). Worth two extra declarations
for a High-severity reliability fix. Backoffs 5/30/120s per OQ3.

**Tests / verification.** 142 passed (was 140); ruff clean. `test_broker_retry` covers the tier
sequence and the DLQ cutoff. The RabbitMQ TTL/dead-letter wiring is verified live against the broker
(needs infra), not in offline unit tests — consistent with how the rest of the broker is tested.

**Edge cases / limitations.** Retries re-enter the same single consumer; a dependency down longer
than ~155s total still ends in the DLQ (then manual/replay). Retry state lives in the broker, so a
message mid-backoff survives an app restart (queues are durable).

### P0-6 — fail-closed secrets in production (AI-SEC-03) (shipped 2026-10-22)

**What changed.** A boot-time validator: when `APP_ENV=production`, a blank `API_KEY`,
`VONAGE_SIGNATURE_SECRET`, or `SF_HOOK_SECRET` raises and the app refuses to start. Outside
production, blanks are still allowed.

**Why.** AI-SEC-03: those checks fail *open* when their secret is blank (a blank signature secret
skips webhook verification; a blank API key leaves the gate off). On a public URL that's a silent
hole — production should fail loud instead.

**How it works.** `@model_validator(mode="after")` on `Settings` lists the required secrets, and
raises `ValueError` (→ pydantic `ValidationError`) naming any that are blank when
`app_env == "production"`. Runs at construction, i.e. at import/boot — fail fast.

**Files.** `app/config.py` (validator), `tests/test_config.py` (new).

**Decisions.** Require all three in production (all three endpoints are public and always mounted).
Kept blank-allowed outside production so local/staging/demo + tests are unchanged.

**Tests / verification.** 146 passed; ruff clean. Tests: production + any blank secret → raises; all
set → boots; local + blanks → fine.

**Edge cases / limitations.** ⚠ Flipping `APP_ENV=production` on Render now REQUIRES those three
secrets set, or boot fails — intended, but call it out before switching. Only guards the three named
secrets, not every possible misconfig.

### P0-7 — authz tests (shipped 2026-10-22)

**What changed.** Tests that lock the auth contract: the open-path allowlist is exactly
`{/health, /ready, /health/deps, /version, /metrics}`, and any other route (e.g. `/ops/approve`) is
401 without the key and 200 with it.

**Why.** Prevent a future change from silently widening the allowlist or leaving a route ungated.

**How it works.** Since auth is a single path-based middleware (not per-route decorators), the gate
is proven once over stub routes plus an assertion that pins `OPEN_PATHS`. No per-route duplication
needed — every non-allowlisted path goes through the same gate.

**Files.** `tests/test_auth.py` (extended — now 6 tests).

**Tests / verification.** 146 passed; ruff clean.

**Edge cases / limitations.** Doesn't boot the full app (that needs DB/broker/graph); it tests the
middleware + allowlist, which is the whole authz surface. A live 401/200 check was also done against
the deployed server (see the AI-SEC-01 log entry).

### P1-1 — Alembic migrations (shipped 2026-10-22)

**What changed.** The orchestrator now has real database migrations (versioned scripts that change
the DB shape over time), instead of `create_all` (a call that only ever *creates missing tables*,
never alters them). Added `alembic.ini`, an async `alembic/env.py`, and the initial migration
(`alembic/versions/952194cd31de_initial_schema.py`) covering our 5 tables. The Postgres boot path no
longer runs `create_all`; migrations own the Postgres schema. SQLite (local dev + the test engine)
still uses `create_all` — no migrations needed there.

**Why.** AI-DATA-01: with `create_all` only, the first real schema change (e.g. P2-1's
`message_uuid` index) would silently never apply, and there was no migration history for safe
rollout/rollback. Needed before any schema change ships to the shared pilot DB.

**How it works.** `env.py` reads the DB URL from `settings.database_url` (one source of truth, no
secret in the repo) and runs migrations through our async engine. Its **`include_object` guard** is
the safety core: autogenerate is scoped to tables declared on our `Base`, so it can never emit a
DROP for LangGraph's durable `checkpoints*` tables (created by `cp.setup()`) or the RAG pgvector
`knowledge_chunks` — both live in the same Postgres but are owned by their own libraries. That guard
is what makes migrations safe for a DB holding paused cases. `init_db()` now branches: Postgres →
skip `create_all` (the Docker entrypoint runs `alembic upgrade head` first — playbook §9c);
non-Postgres → `create_all` as before.

**Files.** `alembic.ini` (new), `alembic/env.py` (new), `alembic/script.py.mako` (new),
`alembic/versions/952194cd31de_initial_schema.py` (new, generated), `app/db/session.py`
(`init_db` branch), `apps/orchestrator/pyproject.toml` (alembic dep + exclude generated migrations
from ruff), root `pyproject.toml` (ruff exclude), `apps/orchestrator/Dockerfile` (ENTRYPOINT),
`apps/orchestrator/docker-entrypoint.sh` (new, migrate-then-serve), `.gitattributes` (new, `*.sh`
LF). `uv.lock` holds alembic but is still gitignored until P1-2.

**Deploy (Render, Docker, free tier).** Render's Pre-Deploy Command is paid-only, so migration runs
from the image: `docker-entrypoint.sh` does `set -e; alembic upgrade head; exec "$@"` — the standard
`exec "$@"` entrypoint idiom (fail-loud on a bad migration, uvicorn stays PID 1 for clean SIGTERM).
Idempotent, so every cold-start wake is a safe no-op. Single-instance assumption noted as the ceiling.

**Decisions.** Autogenerated the baseline against a *throwaway empty SQLite* (not the live DB), so no
network/creds and no risk to real data. Kept `create_all` for SQLite because adding Alembic to the
fast in-memory test path is pure overhead (YAGNI). Excluded `alembic/versions/*` from ruff — it's
machine-generated; linting it fights the generator. **Live DB adoption = `stamp head`, not wipe:**
even though the DB is disposable, stamping is one command, loses nothing, and needs no reseed.

**Tests / verification.** 146 passed (unchanged); ruff clean. The migration round-trips on a
throwaway SQLite: `alembic upgrade head` → `alembic current` shows `952194cd31de (head)` →
`alembic downgrade base` runs clean. The `include_object` guard was confirmed by the generated
migration containing exactly our 5 tables and nothing else (no `checkpoints*`, no `knowledge_chunks`).

**Edge cases / limitations.** The guard only shields *autogenerate*; a hand-written migration can
still do anything, so future migrations must be read before running (normal practice). The existing
live DB must be `stamp`ed once (its tables already exist) before the first `upgrade head`, or that
deploy errors on "table already exists" — hence the strict step order in §6 / playbook §9c.

### P1-2 — reproducible build + CI (shipped 2026-10-22)

**What changed.** Three supply-chain fixes: (1) `uv.lock` is now committed (removed from
`.gitignore`), so every build installs the identical dependency tree. (2) A GitHub Actions workflow
runs lint + tests on every push/PR. (3) `pip-audit` scans the locked deps for known CVEs in CI.

**Why.** AI-SUP-01: the lockfile was gitignored (builds could drift), and there was no automated
gate — a break or a known-vulnerable dependency could merge unnoticed.

**How it works.** `.github/workflows/ci.yml` installs uv (Python 3.12, matching the Docker image),
then `uv sync --locked --all-extras` — `--locked` **fails if `uv.lock` and `pyproject.toml`
disagree** (so the committed lock can't silently rot), `--all-extras` pulls the `dev` extra (pytest,
ruff). Then `ruff check` and `pytest`. A final `pip-audit` step exports the locked deps
(`uv export --no-emit-workspace`, which strips the local editable packages pip-audit can't hash) and
scans them; it's `continue-on-error`, so CVEs are reported without failing the build.

**Files.** `.github/workflows/ci.yml` (new), `.gitignore` (un-ignore `uv.lock`; ignore the
`audit-reqs.txt` scratch file), `uv.lock` (now committed).

**Decisions.** CI Python = **3.12** (match the deploy image, not the `>=3.11` floor — catch what
actually ships). **pip-audit non-blocking first:** a transitive CVE you can't instantly fix shouldn't
wall off every merge; it reports, you triage, then tighten to blocking once clean. **Scope =
orchestrator only** (control-panel `tsc` + e-com are out of the audit's scope — a deliberate POC
corner). Triggers on all pushes + PRs (simple; a branch filter is a later optimisation).

**Tests / verification.** Ran every CI step locally in its exact form: `uv sync --locked --all-extras`
("Resolved 161, Checked 156" — lock consistent), `uv run --all-extras ruff check .` (clean),
`uv run --all-extras pytest -q` (**146 passed**), and the export+`pip-audit` (0 editables; **flagged
`pypdf 6.19.0` and `pillow 12.3.0`** as vulnerable). The GitHub-hosted run itself can't be executed
from here — it runs on first push.

**Edge cases / limitations.** pip-audit is non-blocking, so a real CVE won't stop a merge until that's
flipped — the pypdf/pillow findings are logged as a follow-up bump. CI doesn't build the Docker image
or run the control-panel/e-com checks (orchestrator scope only). No caching tuning beyond uv's own.

### P1-4 — prompt-injection tests + live-e2e checklist (shipped 2026-10-22)

**What changed.** New `tests/test_injection.py` — 6 adversarial tests that assume the LLM (and tool
output) is hostile and prove the deterministic guards hold. Plus playbook §9e, a manual checklist for
one real sandbox e2e (Salesforce + Razorpay test).

**Why.** AI-TEST-01: there were correctness tests but no adversarial ones. "The model behaves" was
assumed, never proven under attack. These pin the actual safety boundary.

**How it works.** Proposer side (parse `parse_proposal` directly): a `delay` job drops *any* part the
model attaches (even a real one — a delay never needs a part); a `parts` job strips an invented
partNo but keeps a genuine catalog one; an injection-framed money promise
("Ignore all previous instructions … this repair is 100% FREE") trips the money guard → the warm
template is sent, so neither the instruction nor the promise reaches the customer. Copilot side
(scripted fake Groq + fake MCP source, reusing `test_copilot_chat`'s doubles): a hostile model that
names a tool never offered is rejected ("unknown tool") and the real read tool never runs; a poisoned
tool *result* telling the model to call a destructive tool can't escalate, because there is no write
tool to route to; and a model that never stops tool-calling is capped at `_MAX_STEPS` and forced to
answer (`truncated`). The live-e2e checklist (§9e) runs the orchestrator locally against the real
Razorpay *test* key + real SF reads, with the operator tapping the real payment link once.

**Files.** `tests/test_injection.py` (new, 6 tests), `playbook.md` §9e (new checklist).

**Decisions.** Net-new only — money-block, sanitize rules, null-part and confidence clamp already live
in `test_llm.py`, so these cover part-smuggling + copilot confinement instead of duplicating. Copilot
tests assert *harness invariants* (confinement, step cap) with a scripted model, not real LLM
behaviour — deterministic and offline. The live e2e is a documented manual checklist, not automated:
it fires a real payment link, so it's human-driven by design (OQ5).

**Tests / verification.** `pytest tests/test_injection.py` → 6 passed; full suite **152 passed**
(was 146); ruff clean.

**Edge cases / limitations.** The money guard is keyword/English-based (noted in P0-9) — an injected
line with no money word still reaches the customer copy, but that copy goes to RCS, not back to a
model, so it can't escalate. Copilot safety rests on the sources exposing only read tools; the tests
prove the harness can't be tricked into more, but don't audit each MCP server's own tool list.

---

## Delegation map (who does what)

- **Keep for the tech lead / senior** (design-sensitive or touches durable state):
  - P0-1/P0-2 auth design, P0-5 retry topology, P1-1 Alembic (touches the live checkpointer).
- **Safe to hand to a junior** (well-scoped, low-risk, clear done-state):
  - P0-6 boot validator, P1-2 commit lock + CI yaml, P1-3 message check, P2-2 GST line + test,
    P2-1 index (after migrations), P1-5 metric counters.
- **Needs you (external / can't be done in code alone):**
  - Choose + set the `API_KEY` on Render and in the panel `.env`.
  - Decide the production secret policy (OQ1–OQ2) and the retry numbers (OQ3).
  - For the live e2e (OQ5): confirm the Vonage test device is available and **tap the test payment
    link once** so the real gateway can read back a capture.
  - GitHub access/permissions for the CI workflow (P1-2).
