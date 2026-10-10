# Build Step 12 — real MCP, Logfire god-eye, simple reconciliation

## 1. Task

- **Name:** make three claimed-but-thin layers honest — **real MCP** (layer 5), **Logfire**
  observability wired as the god-eye view (layer 7), **reconciliation** as a simple pass (layer 7).
- **Status:** planned (2026-10-10). No code yet.
- **Started:** 2026-10-10 · **Last updated:** 2026-10-10.

## 2. What you asked for

- "Make MCP real." Driver: a **FieldFlow admin copilot** — a panel chat answering admins' open-ended
  queries over **Salesforce and e-com** (and more tools later). "e-com might use MCP too." "Don't just
  think of existing APIs — we'll have many things."
- Logfire: "configure it properly and very well — it's our GOD-eye-view room panel."
- Reconciliation: "build it simple, ponytail."
- Guardrail kept from the core design: the automated recovery pipeline stays deterministic; MCP powers
  the copilot + reads; copilot writes are human-confirmed.

## 3. Open questions (my recommendation — your call)

| # | Question | Recommendation |
|---|----------|----------------|
| Q1 | Is the admin copilot **in scope now**, or is it the *justification* for MCP, built later? | **Later** — it's the "why"; we build the MCP plumbing (SF Hosted MCP + e-com MCP server + a thin MCP client) first, the chat UI after e-com + panel exist. |
| Q2 | Which LLM powers the copilot? | **Reuse the Groq→Gemini ladder** already in `app/llm/` (function/tool-calling mode). No new vendor. |
| Q3 | Where does the copilot run? | **Panel (Next.js on Vercel) calls a thin `/copilot` route on the orchestrator** which is the MCP client. Keeps creds server-side; the browser never holds MCP tokens. |
| Q4 | SF Hosted MCP auth = user-based or admin-based? | **Admin-based** for the POC (one ECA, shared token) — simplest; least-privilege/user-based later. Needs a **new External Client App** (NOT the client-credentials one used for the Pub/Sub trigger). |
| Q5 | Reconciliation scope? | **Read-only sweep**: find cases non-terminal + past SLA with no pending human step → list them (and optionally re-drive). A `/reconcile` endpoint + a counter. Ceiling: no auto-heal, just surface. |
| Q6 | Logfire token/account? | **You create a free Logfire project + token** → `LOGFIRE_TOKEN` in `.env`/Render. Wiring degrades to no-op offline so tests stay green. |

## 4. Plan (sequenced by dependency)

> The deterministic pipeline is untouched. All of this is additive.

1. **Logfire (cheap, unblocked).** `uv add logfire`; `logfire.configure()` armed only when
   `LOGFIRE_TOKEN` is set (no-op otherwise); instrument FastAPI + SQLAlchemy + spans around the
   consumer, each graph node, each tool call, each LLM call (carry `correlationId`). The god-eye view.
2. **Reconciliation (cheap, unblocked).** A read-only sweep (Q5) + `POST /reconcile` + a Prometheus
   counter. One test over fixture cases.
3. **`RestSalesforce` adapter (unblocked once Apex deployed).** The deterministic read/reschedule path
   live against the org via `apps/salesforce-apex/` (reads first, then reschedule). Not MCP.
4. **SF Hosted MCP + MCP client (needs a new ECA — your action).** A thin MCP client in the
   orchestrator (the `mcp` SDK) over Salesforce Hosted MCP for reads.
5. **E-com MCP server (needs the e-com service first).** The e-com (Next.js) exposes its product/stock
   reads as an MCP server.
6. **Admin copilot (needs 4 + 5 + panel).** `/copilot` route = MCP client over both servers; panel chat
   UI; writes human-confirmed.

**Rejected:** routing the recovery pipeline's mutations through LLM-invoked MCP (breaks the ladder);
a second LLM vendor for the copilot (reuse the ladder).

## 5. Tasks

- [x] **Logfire wired** (2026-10-10) — `logfire[fastapi]` added; `logfire.configure(send_to_logfire=
      'if-token-present')` + `instrument_fastapi` in `main.py` lifespan, wrapped so it can't crash the
      app; no-op offline, streams when `LOGFIRE_TOKEN` set (user's token is set). Follow-up: per-node /
      LLM / SQLAlchemy spans.
- [x] **Reconciliation** (2026-10-10) — `app/reconcile.py` `find_lingering()` + `GET /reconcile`
      (read-only; non-terminal cases not updated for N min, most-stuck first) + `test_reconcile.py`.
      Ceiling: no auto-heal.
- [x] `RestSalesforce` adapter behind `build_salesforce` (2026-10-10) — reads + reschedule against
      the Apex REST surface; armed by the 3 client-credentials creds; mock-first, 91 tests green.
- [~] **MCP client + copilot tools BUILT 2026-10-11** (Option 2 custom Apex, admin-based). Code:
      `apps/orchestrator/app/mcp/` (`SalesforceMcpClient` = refresh-token→access-token + Streamable-HTTP
      session; `build_mcp_client` swap line; `login.py` = one-time OAuth2+PKCE to mint the refresh
      token) + `GET /copilot/tools` + `apps/salesforce-apex/FieldFlowCopilotTools.cls` (2 invocable
      tools). **99 tests green, ruff clean.** Finding: Hosted MCP auth is OAuth2+PKCE (no headless
      client-creds) → the one-time `python -m app.mcp.login`. USER ACTIONS remain: create the ECA,
      activate the MCP server over the Apex tools, run the login once. Then live-verify like the reads.
- [x] E-com MCP server — shipped with the e-com build (2026-10-11); read-only `list_products` +
      `get_stock` at `/api/mcp`. See [`build-step-13-ecom-inventory.md`](build-step-13-ecom-inventory.md).
- [ ] Admin copilot route + panel chat (writes human-confirmed).

## 6. Updates

- **2026-10-10** — Plan created from the 7-layer honesty audit. MCP decision reversed from
  "MCP-shaped is enough" → "make it real," justified by the admin-copilot agentic requirement (recorded
  in `context/00-overview.md` + `03-knowledge-and-tools.md`). Logfire + reconciliation scoped. Q1–Q6
  carry recommendations. The user's origin brainstorm is `poc_idea.md` (the 7-layer stack, wow
  checklist, failure matrix, hidden frictions all trace to it).
- **2026-10-10 (later)** — **Quick wins shipped:** Logfire wired + reconciliation sweep (tasks above),
  **79 tests green, ruff clean**. Hosted-MCP setup recipe written ([`hosted-mcp-setup.md`](hosted-mcp-setup.md)).
  Remaining 4 tasks blocked on org/e-com/panel (sequenced in §4).
- **2026-10-10 (Task 3)** — **`RestSalesforce` adapter shipped** (mock-first, **91 tests green, ruff
  clean**). Reads + reschedule run against the Apex REST class behind the same `SalesforceTools`
  Protocol; `build_salesforce` is the one swap line. Open questions resolved by the user all "as
  recommended": OQ1 (Pub/Sub trigger behind a new explicit `SF_PUBSUB_ENABLED` so arming REST reads
  can't start the stubbed trigger), OQ2 (slot label → UTC ISO-8601, `SF_TIMEZONE`-aware), OQ3 (both
  reads + reschedule built now; live reschedule gated on the Apex deploy), OQ4 (token cached, refetched
  once on 401). **Not** MCP — the deterministic path, per §4 note. Explanation in §7.

## 7. Explanation — the `RestSalesforce` adapter (Task 3)

**1. What changed.** The orchestrator can now read from (and reschedule in) a **real Salesforce org**
instead of only the in-memory fake — over the plain **Apex REST** class in `apps/salesforce-apex/`.
It stays off until the 3 Salesforce creds are set, so every test and a keyless boot are unchanged.

**2. Why it was needed.** Until now `app.state.salesforce` was hard-wired to `FakeSalesforce`. The
story needs the recovery pipeline to touch the actual service org. This is the deterministic read +
reschedule path (the LLM never invokes it) — distinct from the later Hosted-MCP copilot work.

**3. How it works, step by step.**
- `build_salesforce(settings)` returns `FakeSalesforce` when creds are blank, else `RestSalesforce` —
  the one swap line, same pattern as `build_vonage` / `build_gateway`.
- `RestSalesforce` logs in with **OAuth client-credentials** (server-to-server, no human): one POST
  to `/services/oauth2/token` returns an `access_token` + the org's `instance_url`, both cached in
  memory. On a `401` (expired token) it re-authenticates **once** and retries (OQ4).
- **Reads** GET `/services/apexrest/fieldflow/{appointment,customer,asset,technician}/{id}` and return
  the exact JSON shapes the fake returns (the Apex class mirrors them), so the graph is untouched. A
  `404` → `None` so an action tool can refuse.
- **Reschedule** is the one mutation. The slot's time only exists in its human label (e.g.
  `"TODAY 15:00-17:00"`), so the graph now passes that label through `reschedule.confirm`. The adapter
  converts it: parse the day word + `HH:MM-HH:MM`, build a timezone-aware datetime in `SF_TIMEZONE`
  (default `Asia/Kolkata`), convert to **UTC** and format as ISO-8601 with a `Z` suffix — the one
  unambiguous form Salesforce's Apex `JSON.deserialize(..., Datetime)` accepts (OQ2). Then POST
  `{appointmentId, startTime, endTime}`.

**4. Files / functions changed.**
- `app/tools/salesforce.py` — new `RestSalesforce` (token + httpx calls), `slot_label_to_times`
  helper, `build_salesforce` factory; `SalesforceTools.reschedule` + `FakeSalesforce.reschedule` gain
  an optional `slot_label` (the fake ignores it).
- `app/main.py` — the swap line: `app.state.salesforce = build_salesforce(settings)`.
- `app/tools/registry.py` — `reschedule_confirm` threads `slotLabel` to the adapter.
- `app/graph/build.py` — passes `slotLabel=chosen["label"]` into `reschedule.confirm`.
- `app/config.py` — `sf_timezone`, `sf_pubsub_enabled`, `sf_rest_armed` property; `sf_pubsub_armed`
  now also requires `sf_pubsub_enabled`.
- `pyproject.toml` — `tzdata` (zoneinfo needs the IANA db on Windows).
- `tests/test_salesforce_rest.py` (new, 12 tests via `httpx.MockTransport`); `tests/test_event_source.py`
  updated for the new Pub/Sub gate. `.env.example` documents the new vars.

**5. Important decisions.** Apex REST, not Hosted MCP, for this path — the LLM must never invoke a
mutation (the core guardrail). The Pub/Sub trigger got its own opt-in flag so arming reads can't start
the still-stubbed gRPC subscriber (OQ1). UTC-on-the-wire chosen over a floating local time so SF and
every other system agree on the one instant (OQ2). Rejected: adding real start/end times back at the
proposer (bigger change touching the graph) — parsing the label in the adapter is the smaller diff.

**6. Tests / verification.** `uv run pytest -q` → **91 passed** (was 79); `uv run ruff check .` →
clean; `uv run python -c "import app.main"` → OK. The new tests drive the real httpx code path with
canned responses matching the Apex class — no org, no network.

**7. Edge cases and limitations.** Live calls are **untested against a real org** — gated on the user
deploying the Apex class + confirming assumptions A1–A4 (README §4). The label parser assumes a
same-day window that doesn't cross midnight and `TODAY`/`TOMORROW` only (ponytail comment names the
ceiling). The live **reschedule** write is the one truly gated action — reads are safe to turn on
first.
