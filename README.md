# FieldFlow AI

AI field-service recovery system. When a home-service / appliance-repair appointment goes wrong,
FieldFlow AI detects it, reasons over enterprise context, validates options against deterministic
rules, and lets the customer fix it through **RCS** — then executes the real changes.

**The one idea:** *AI proposes; deterministic policy decides; humans approve risk. RCS is the
customer control plane.*

Full docs: [`docs/specs/field-service-recovery/`](docs/specs/field-service-recovery/) —
SRS, risks, roles, context (7 files), diagrams, and the scaffold plan.

---

## Status: thin spine (walking skeleton)

Right now this proves the **pipes**, not the product: a fired event travels
`sim → RabbitMQ → idempotency → LangGraph → FakeVonage → Postgres → control panel`.
Everything AI / Salesforce / RCS is mocked. See
[`docs/specs/field-service-recovery/scaffold.md`](docs/specs/field-service-recovery/scaffold.md).

## Layout

```
apps/orchestrator/   Python · FastAPI + LangGraph (commerce is a module inside)
apps/control-panel/  React · Vite · Tailwind (demo UI)
packages/contract/   Pydantic models — the shared event/tool contract
infra/               docker-compose: RabbitMQ · Postgres+pgvector · Prometheus · Grafana
```

## Run it (walking skeleton)

Prereqs: Docker, [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
# 1. Start infra (RabbitMQ, Postgres, Prometheus, Grafana)
make up

# 2. Start the orchestrator (FastAPI on :8000, consumer runs inside it)
make dev

# 3. Start the control panel (Vite on :5173)
make panel

# 4. Fire the demo event — then watch the case appear in the panel
curl -X POST http://localhost:8000/sim/appointment-at-risk

# Fire the SAME event twice → still ONE case, ONE card (idempotency):
#   the response includes the eventId; re-POST it with that id and see status "duplicate".
```

- Orchestrator API docs: <http://localhost:8000/docs>
- RabbitMQ UI: <http://localhost:15672> (guest/guest) · Grafana: <http://localhost:3000> (admin/admin)

## Test & lint

```bash
make test   # pytest: idempotency + spine end-to-end (no infra needed — uses in-memory SQLite + fakes)
make lint   # ruff
```

## What's deliberately mocked (real later)

Vonage RCS, Salesforce/MCP, Groq LLM, RAG retrieval, Razorpay — all behind clean interfaces, so
they swap in without touching the flow. Build order is in `scaffold.md` §6.
