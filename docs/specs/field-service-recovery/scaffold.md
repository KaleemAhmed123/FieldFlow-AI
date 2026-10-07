# FieldFlow AI — Scaffold Plan

**Status:** Spine built & verified · **Started:** 2026-10-06 · **Last updated:** 2026-10-06

> The plan for the **first** code. Approve this before I write anything. Strategy (from the
> tech-lead pushback): **thin spine first** — prove the pipes end-to-end, then thicken node by
> node. Diagram: [`diagrams/04-scaffold-walking-skeleton.excalidraw`](diagrams/04-scaffold-walking-skeleton.excalidraw).

## 1. Decisions this builds on

- **Python/FastAPI** for all backend + APIs. **React** for the control panel.
- **Commerce = a module inside the orchestrator** (not a separate app).
- **Groq** free tier for the LLM (model TBD — benchmark later). Not in the walking skeleton.
- **Tool interface + mocks now**, real Salesforce/MCP + real Vonage later.
- **Demo-focused control panel v1.**
- Build a **thin spine** first; everything else is a later layer.

## 2. Repo layout (target for this scaffold)

```
fieldflow/
  apps/
    orchestrator/              # the Python brain (FastAPI + LangGraph)
      pyproject.toml
      app/
        main.py                # FastAPI app + lifespan (open/close queue, db)
        config.py              # pydantic-settings — env, validated at boot
        logging.py             # structlog JSON + correlation-id middleware
        queue/                 # aio-pika: connection, publisher, consumer
        graph/                 # LangGraph: state, nodes, build_graph()
        policy/                # policy engine (stub in spine)
        tools/
          vonage.py            # VonageClient protocol + FakeVonage
          salesforce.py        # SalesforceTools protocol + FakeSalesforce
          inventory.py         # (stub)
        commerce/              # COMMERCE MODULE: routers + service (stubs in spine)
        rag/                   # LlamaIndex (stub in spine)
        db/                    # SQLAlchemy 2.0 async models + session + alembic
        telemetry/             # prometheus-client metrics
        sim/                   # demo endpoints that fire fake events
      tests/                   # pytest (idempotency + spine e2e)
      .env.example
      Dockerfile
    control-panel/             # React + Vite + TS
      src/                     # case timeline, live status, decision trace, failure buttons
      .env.example
  packages/
    contract/                  # Pydantic models (events + tool signatures) + JSON Schema export
  infra/
    docker-compose.yml         # rabbitmq · postgres+pgvector · prometheus · grafana
    prometheus/  grafana/
  Makefile                     # make up / dev / test / lint
  README.md
```

## 3. What the walking skeleton actually does (the only thing that *runs* in v1)

```
[control panel button]  or  POST /sim/appointment-at-risk
        │  publishes contract event appointment.at_risk (with eventId + correlationId)
        ▼
   RabbitMQ
        ▼
   orchestrator consumer  ── idempotency check on eventId (dedup table)
        ▼
   LangGraph (2 nodes):  load_case (stub context) → offer_options (build fake carousel)
        ▼
   FakeVonage.send_card()  ── records the "sent" card (no real RCS)
        ▼
   Postgres: case_state + audit row + a stub decision trace
        ▼
   control panel shows: the case appears, its status, the "sent" card, the trace
```

**Done = verifiable:** fire the event → a case shows up in the panel with a "sent" card; fire the
**same** event twice → still **one** case, **one** card (idempotency). That's the spine proven.

## 4. What is explicitly NOT in the scaffold (later layers)

Real Groq calls · real RAG retrieval · real MCP/Salesforce · real Vonage · the other graph nodes
(location, photo/vision, quote, payment, confirm, report) · 5 of 6 failure demos · Grafana
dashboards beyond a couple of counters · payment/Razorpay · auth. Each is added once the spine runs.

## 5. Best practices baked in from line one (proposed defaults — say if you'd prefer otherwise)

| Concern | Proposed tool | Why |
|---------|---------------|-----|
| Deps / venv | **uv** | Fast, modern, single tool. (alt: poetry) |
| Lint + format | **ruff** + `ruff format` | One fast tool. |
| Config | **pydantic-settings** + `.env` | Validated at boot; fail fast; no secrets in code. |
| Logging | **structlog** JSON + **contextvars** correlation id | Every log/event/tool-call carries the case id. |
| Web | **FastAPI** + **uvicorn** | Async, Pydantic validation, auto `/docs`. |
| Queue | **aio-pika** | Async RabbitMQ; retry/DLQ topology. |
| DB | **SQLAlchemy 2.0 async** + **asyncpg** + **alembic** | pgvector-ready; migrations from day one. |
| Orchestration | **langgraph** (+ Postgres checkpointer later; memory in spine) | Durable, resumable case state. |
| Contract | **Pydantic v2** models; export **JSON Schema** | Both sides validate; React gets TS types from the schema. |
| Tests | **pytest** + **pytest-asyncio** | One idempotency test + one spine e2e test in v1. |
| Frontend | **React + Vite + TS**, **Tailwind + shadcn/ui**, **TanStack Query**, WebSocket | A standard, familiar React stack; live case updates. |
| Observability | **Logfire** (live OTel traces / god-eye view) + Prometheus (metrics, optional) | See [`context/05-reliability-and-observability.md`](context/05-reliability-and-observability.md). |
| Health & shutdown | FastAPI `/health` + `/ready`, graceful queue drain on SIGTERM | Feels real; safe restarts. |

**Deliberately skipped (POC):** Kubernetes, CI/CD, multi-env, auth hardening, pre-commit gates.

## 6. Build order after the spine

1. ✅ Spine (this scaffold).
2. ✅ Policy engine + the full LangGraph nodes (options → validate → interrupt/resume) — **Step 1**,
   see [`build-step-1.md`](build-step-1.md).
3. MCP tool-interface filled with FakeSalesforce data; read tools then action tools.
4. RAG (tiny pgvector corpus) feeding the decision.
5. Groq wired for the decision + explanation step (with a cached fallback for live demos).
6. Commerce module (quotes/orders) + Razorpay Test-Mode.
7. The 2 headline failure demos (RCS→SMS fallback, Salesforce-down/DLQ), then the rest.
8. Control panel richness + Grafana dashboards.
9. Swap mocks → real Vonage + real Salesforce/MCP.

## 7. Open micro-decisions (confirm before I build)

| # | Question | My proposal |
|---|----------|-------------|
| S1 | Who owns the **commerce module** now it's Python-in-orchestrator? | You (it's in your app) — SF Dev stays on Salesforce + co-owns MCP-over-SF. |
| S2 | Accept the **tooling defaults** in §5? | Yes, as listed. |
| S3 | **`git init`** the project now? (not currently a git repo) | Yes — scaffold onto a fresh repo with a sensible `.gitignore`. |

## 8. Updates

- **2026-10-06** — Plan created after the tech-lead pushback. Thin-spine-first strategy adopted;
  commerce became a module (was a separate app); MCP/Salesforce/Vonage mocked first.
- **2026-10-06** — **Spine built & verified.** `uv sync` OK; **ruff clean**; **2/2 pytest pass**
  (idempotency + spine e2e); `app.main` imports; LangGraph runs (carousel, 2 options). Repo is a
  git repo on `main` (no commits yet). Two pragmatic spine choices, to revisit: panel **polls**
  (WebSocket later); tables via **`create_all`** (alembic once schema settles). The live
  RabbitMQ hop is verified by `make up` + `make dev` + curl (manual), not by the tests.
- **2026-10-07** — **Step 1 built & verified** (build order #2). Real policy engine + full
  LangGraph flow with interrupt/resume + NFR-4/5/6, mock-first. **10/10 pytest pass**; **ruff
  clean**; `app.main` imports; default `/sim` event still a 2-option OPTIONS_SENT carousel. One
  choice to revisit: **in-memory checkpointer** (Postgres saver is a one-dep swap for
  restart-durable resume). Details in [`build-step-1.md`](build-step-1.md).
