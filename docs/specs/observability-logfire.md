# Observability — full Logfire god-eye + LLM analytics

## 1. Task

- **Name:** Plug Logfire fully — one connected trace per case (SF call → RCS/close), LLM
  token/cost analytics, Logfire-native metrics, and a Discord alert on FAILED/DLQ growth.
- **Status:** In progress
- **Started:** 2026-10-23
- **Last updated:** 2026-10-23
- **Maps to:** audit finding **AI-OBS-01** (thin metrics, no alerting, no dashboards) and the
  remediation task **P1-5**. See
  [`ai-system-production-readiness-audit.md`](ai-system-production-readiness-audit.md) §20 and
  [`production-readiness-remediation.md`](production-readiness-remediation.md).

---

## 2. What you asked for

> "I have Logfire but it's not completely plugged — I can't see much on the dashboard. Plug it,
> then guide me: if I want to trace a request entirely from the SF call to the end here, how? I
> should be able to show the tech lead to impress, and also debug when something goes wrong. I also
> want the LLM dashboard — complete visibility and analytics."

Running on **Render + Vercel free tier** (no VPS), so self-hosted Prometheus/Grafana Docker images
don't fit. Need a managed, zero-infra way to get complete visibility.

---

## 3. Open questions (answered 2026-10-23)

| # | Question | Decision |
|---|----------|----------|
| OQ1 | Logfire only, or add Langfuse? | **Logfire only.** One pane — HTTP + SQL + LLM + logs + the case trace in one tool; its native LLM panel already gives token/cost/latency/provider analytics. Add Langfuse later only if we need prompt-versioning / eval datasets (pairs with P1-6). |
| OQ2 | How to stitch the trace across RabbitMQ? | **Full trace propagation through the queue.** Inject the OTel `traceparent` into the message header at publish; attach it at consume → the SF webhook and the whole case become **one connected tree**. |
| OQ3 | Prometheus counters (nobody scrapes `/metrics` on Render free)? | **Move to Logfire metrics, drop Prometheus.** Convert the counters to `logfire.metric_*`, remove `prometheus_client` + the dead `/metrics` route. |
| OQ4 | Alert channel? | **Discord webhook.** Logfire posts FAILED-case / DLQ-growth alerts to a channel. |
| OQ5 | Capture prompt/response content in traces? | **Yes (`SPAN_ONLY`).** Data is fake (`CLAUDE.md`), so capturing prompts + completions is safe and is what lights up the LLM panel. |

---

## 4. Plan

### The problem (why "can't see much")
The SF webhook returns `200` instantly, then the real pipeline runs in the **RabbitMQ consumer** — a
separate execution context. `instrument_fastapi` only traces the webhook, which ends at "published to
queue." The entire AI pipeline (load context → RAG → LLM → policy → offer → pay → close) runs dark.

### The fix — one trace per case
Leverage points (small diff, big visibility):

1. **structlog → Logfire bridge** (`logfire.StructlogProcessor`) — every existing `log.*` rides the
   trace. The code is already richly logged with `correlationId`; this is the biggest free win.
2. **`instrument_sqlalchemy(engine)`** — every DB query in the trace.
3. **`instrument_google_genai()`** — Gemini tokens + cost, automatic.
4. **Groq manual GenAI attributes** — Groq (the *primary* model) isn't auto-instrumented; pull
   `resp.usage` and emit `gen_ai.*` span attributes → same LLM panel.
5. **Queue trace propagation** — `traceparent` header on publish, `attach_context` on consume →
   webhook span and case become one tree (OQ2). Carried through retries too.
6. **Root "case" span** in the consumer, tagged `correlationId` / `reason` / final `status`.
7. **Per-node spans** — wrap all 18 nodes in the `add_node` loop (one place) → each stage timed.
8. **Metrics → Logfire** (OQ3) — convert counters; wire the two dead ones
   (`proposer_fallback` by provider, `decisions` by outcome).

### Trace shape (what you'll read)
```
POST /webhooks/sf/at-risk            ← FastAPI span (the SF call)
└─ publish appointment.at_risk       ← traceparent injected into the message
   └─ process event  (consumer; traceparent attached — same trace)
      └─ case {reason}  correlationId=…  status=…        ← the god-eye root span
         ├─ node load_case
         ├─ node load_context         → 4 Salesforce reads (SQL/HTTP child spans)
         ├─ node retrieve_knowledge   → Jina embed + rerank
         ├─ node generate_options     → groq chat  (provider · 1,240 tok · $0.0003 · 2.1s)
         ├─ node policy_validate      (outcome=APPROVED → decisions metric)
         ├─ node offer_to_customer    → Vonage send_card
         ├─ … await_reply / execute / build_quote / payment …
         └─ node close                status=CLOSED
```
Search `correlationId = X` in Logfire → the whole life of the case, end to end.

### Dashboards + alerts (Logfire UI — guided, not code)
- **LLM panel:** native once GenAI spans flow (tokens, cost, latency, model, per-provider).
- **Saved dashboard:** requests/min, p95 case latency, provider-fallback rate, decision-outcome
  split, DLQ depth, cost/day.
- **Alert (Discord):** FAILED-case appears, or DLQ depth grows — Logfire SQL alert → Discord webhook.

### Files to touch
`app/telemetry.py` (rewrite to Logfire metrics), `app/main.py` (instrument sqlalchemy + google-genai,
reorder configure), `app/logging.py` (StructlogProcessor), `app/db/session.py` (`get_engine`),
`app/queue/broker.py` (propagate + consume span + `.add`/`.record`), `app/services/case_service.py`
(case span + `.add`), `app/graph/build.py` (node spans + wire 2 metrics), `app/llm/groq.py` (GenAI
span), `app/api/routes.py` (drop `/metrics`), `app/auth.py` (drop `/metrics` from allowlist),
`tests/test_auth.py` (allowlist assertion), `pyproject.toml` (drop `prometheus-client`), `.env.example`
(GenAI capture + Discord), `playbook.md` (the tracing how-to + alert setup).

### Deliberately NOT changing
The pipeline logic, the policy/AI boundary, the API contract. Observability is additive and wrapped
so it can never crash the app (same rule as the existing Logfire block).

### Alternatives rejected
- Langfuse now (OQ1) — second tool fragments the single-pane view; defer.
- Grafana Cloud scrape of `/metrics` — keeps dead-ish infra; Logfire metrics are zero-infra.
- correlationId-only trace linking (OQ2) — full propagation is barely more code and gives the real
  connected tree.

---

## 5. Tasks

- [x] T1 `telemetry.py` → Logfire metrics; updated 8 call sites (`.inc()`→`.add(1)`, histogram
  `.time()`→`.record()`). ✅ 2026-10-23
- [x] T2 Dropped `/metrics` route + `prometheus-client` dep; fixed `OPEN_PATHS` + `test_auth.py`. ✅
- [x] T3 `main.py`: Logfire configured before logging; `instrument_sqlalchemy` + `instrument_google_genai`. ✅
- [x] T4 `logging.py`: `StructlogProcessor` bridge. ✅
- [x] T5 `broker.py`: inject `traceparent` on publish; attach + `process event` span on consume;
  `traceparent` carried through retries. ✅
- [x] T6 `case_service.py`: root `case recovery` span (correlationId / reason / status). ✅
- [x] T7 `build.py`: every node wrapped in a span (bubble-up-safe); `proposer_fallback` + `decisions` wired. ✅
- [x] T8 `groq.py`: GenAI span with token usage. ✅
- [x] T9 Tracing how-to + alert/dashboard setup → `playbook.md` §9f; `.env.example` updated. ✅
- [x] T10 Verify: **152 pytest pass**, **ruff clean**, Logfire API + app boot smoke-tested. ⏳ Live
  trace + LLM panel + Discord alert confirmed after you set the token/env + build the UI pieces.

---

## 6. Updates

- **2026-10-23** — Spec created; OQ1–OQ5 answered (Logfire-only · queue propagation · drop
  Prometheus · Discord · capture content).
- **2026-10-23** — **All code shipped (T1–T9).** One connected trace per case across the queue;
  Groq + Gemini LLM spans with token usage; SQL + structlog folded into the trace; metrics moved to
  Logfire and the two dead counters wired; `/metrics` + `prometheus-client` removed. 152 pytest
  pass, ruff clean, Logfire API + app boot smoke-tested. Dashboards + the Discord alert are Logfire
  UI steps, documented in playbook §9f (gated on your token/env). Walkthrough in §7.

---

## 7. Explanation

### What changed
Logfire went from tracing only the HTTP front door to tracing the **whole case as one connected
tree** — SF webhook → RabbitMQ → consumer → each of the 18 pipeline nodes → each SQL query → the LLM
call → Vonage → close. LLM calls now carry token usage. Metrics moved off Prometheus (which nothing
scraped on Render free) into the same Logfire project.

### Why it was needed
`instrument_fastapi` only traced the webhook, which returns `200` and ends at "published to queue."
The real pipeline runs in the RabbitMQ consumer — a separate execution context — so the entire AI
flow was invisible. That's why the dashboard "showed little." AI-OBS-01 / P1-5.

### How it works, step by step
1. **Boot** (`main.py`): Logfire is configured *first* (before logging), then `instrument_fastapi`,
   `instrument_google_genai` (Gemini token/cost auto), and — after the DB engine exists —
   `instrument_sqlalchemy` (every query a span). Each wrapped so a failure can't stop boot.
2. **Logs into traces** (`logging.py`): a `logfire.StructlogProcessor` is added to the structlog
   chain, so every existing `log.*` (already carrying `correlationId`) appears inside the active span.
3. **Across the queue** (`broker.py`): on `publish`, the current trace is serialized to a
   `traceparent` message header (`logfire.get_context()`); on consume, `logfire.attach_context()`
   re-attaches it and a `process event` span is opened — so the consumer's work continues the
   webhook's trace. The header is carried through the retry queues too, so a retried event stays in
   the same trace. Latency is recorded to the `fieldflow.event_seconds` histogram per attempt.
4. **The case span** (`case_service.py`): `handle_event` opens a `case recovery` span tagged
   `correlationId` / `eventId` / `reason`, and sets `status` (CLOSED/REJECTED/FAILED) at the end —
   the searchable root of the god-eye view.
5. **Per node** (`build.py`): the `add_node` loop wraps every node in a `node {name}` span. A
   LangGraph `GraphBubbleUp` (a normal `interrupt()` pause for a human/customer) closes the span
   cleanly instead of recording a fake error.
6. **LLM visibility**: Gemini is auto-instrumented; Groq (the primary, no auto-instrumentor) emits
   the standard `gen_ai.*` attributes by hand from `resp.usage` → both light up Logfire's LLM panel.
7. **Metrics** (`telemetry.py`): the counters are now `logfire.metric_counter/histogram`; the two
   previously-dead signals are wired — `proposer_fallback` (by `provider`) in `generate_options`,
   `decisions` (by `outcome`) in `policy_validate`.

### Files / functions changed
`telemetry.py` (Logfire metrics), `logging.py` (bridge), `main.py` (configure order + 2 instruments),
`db/session.py` (`get_engine`), `queue/broker.py` (`_trace_header`, consume span, retry header,
`.add`/`.record`), `services/case_service.py` (`case recovery` span), `graph/build.py` (`_traced`
wrapper + 2 metrics), `llm/groq.py` (GenAI span), `api/routes.py` (dropped `/metrics`), `auth.py`
(dropped `/metrics` from the allowlist), `tests/test_auth.py` (allowlist), `pyproject.toml`
(drop `prometheus-client`, add logfire `sqlalchemy`+`google-genai` extras, `[tool.logfire]`),
`.env.example` + `playbook.md` §9f.

### Important decisions
- **Full queue propagation** over correlationId-only linking (OQ2) — one real connected tree; the
  cost is ~10 lines in the broker.
- **Dropped Prometheus** (OQ3) — nothing scraped `/metrics`; one tool is cleaner than dead infra.
- **Bubble-up-safe node wrapper** — critical: without it, every human/customer pause would show as a
  failed span and pollute the traces and the FAILED-case alert.
- **Groq by hand, Gemini auto** — the groq SDK has no Logfire instrumentor; manual `gen_ai.*`
  attributes reuse the same LLM panel without a wrapper library.

### Tests / verification
`uv run pytest -q` → **152 passed**; `uv run ruff check .` → **All checks passed**; a smoke script
exercised every Logfire call the code makes (metric add/record, span, get/attach context,
set_attributes, `instrument_google_genai`, `instrument_sqlalchemy`) and imported `app.main` cleanly.
Live traces/LLM-panel/alert are confirmed after the token + env are set (your step; playbook §9f).

### Edge cases and limitations
- The `traceparent` only connects the tree when the SF trigger publishes **inside** the webhook span
  (it does). The `/sim/*` path has no HTTP parent, so a sim-fired case is its own root trace — fine.
- Groq cost may show as unknown if its model isn't in Logfire's pricing table; **tokens** always show.
- `OTEL_..._CAPTURE_MESSAGE_CONTENT` must be a real process env var (not just `.env`) to capture
  prompt/response content on the Gemini path.
- Metrics are in-process on one Render dyno (same ceiling as the rate limiter) — fine for the POC.
