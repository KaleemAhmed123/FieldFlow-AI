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
- [ ] `RestSalesforce` adapter behind `build_toolbox` (reads live, then reschedule).
- [ ] New ECA (admin-based) + MCP client for SF Hosted MCP reads — recipe in [`hosted-mcp-setup.md`](hosted-mcp-setup.md).
- [ ] E-com MCP server (with the e-com build).
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
