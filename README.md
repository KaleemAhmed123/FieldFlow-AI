# FieldFlow AI

**AI field-service recovery — where AI proposes, deterministic policy decides, humans approve risk, and RCS is the customer's control plane.**

When a home-appliance repair goes wrong (technician late, part missing, unit worse than booked), FieldFlow AI detects it, reasons over the full enterprise context, validates every option against auditable business rules, and lets the customer fix it — pick a slot, share location, photograph the unit, approve a quote, pay — entirely inside one **RCS** chat thread. No app, no phone call. Then it executes the real changes across Salesforce, inventory and payments.

<p>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white">
  <img alt="LangGraph" src="https://img.shields.io/badge/LangGraph-stateful%20agent-1C3C3C">
  <img alt="LlamaIndex" src="https://img.shields.io/badge/LlamaIndex%20%2B%20pgvector-RAG-6E4AFF">
  <img alt="MCP" src="https://img.shields.io/badge/MCP-tool%20discovery-000000">
  <img alt="Vonage" src="https://img.shields.io/badge/Vonage-RCS%20Messages%20API-black">
  <img alt="Salesforce" src="https://img.shields.io/badge/Salesforce-Field%20Service-00A1E0?logo=salesforce&logoColor=white">
  <img alt="RabbitMQ" src="https://img.shields.io/badge/RabbitMQ-DLQ%20%2B%20idempotency-FF6600?logo=rabbitmq&logoColor=white">
  <img alt="Status" src="https://img.shields.io/badge/status-live%20end--to--end-success">
</p>

> **Live** — orchestrator on Render, e-com inventory on Vercel, full AI pipeline (RAG → LLM → policy → RCS) firing end-to-end, with a real RCS card delivered to a real Android phone.

---

## 🎥 Demo

https://github.com/user-attachments/assets/318a7e93-16e3-48dc-af10-f3a7f5105a8e

> The full loop: an at-risk appointment → AI investigates → policy filters options → customer picks a slot, shares location, uploads a photo, approves a quote and pays — all over RCS.

---

## What it does

- **Detects** an at-risk appointment from a Salesforce enterprise event.
- **Reasons** over the whole situation — customer, asset, warranty, technician, live stock, and the service manuals (via RAG) — and **proposes** fixes plus how to explain them.
- **Decides** safely: a deterministic policy engine (plain code, no model) removes every illegal option; a human approves anything risky.
- **Negotiates** the fix with the customer over **RCS** — rich cards, carousels, location, photo upload, pay link, PDF report — no app, no call.
- **Executes** the real changes: reschedule in Salesforce, reserve stock, raise a quote, capture payment — **idempotent and consistent** under duplicate events, failures and channel limits.

## The one idea (and why it matters for AI)

> **The AI proposes. Deterministic policy decides. A human approves risk. RCS is the control plane.**

The clever part (the AI) is **fenced in** by the safe part (policy + human gate). That fence is what makes an AI system trustworthy enough to touch real operations and real money — the **authority ladder**:

```
LEVEL 1 — DETERMINISTIC   Can this legally/technically happen?
                          permission · SLA · inventory · price · appointment · state · idempotency
LEVEL 2 — AI              What's happening? Which fix is best? What's missing? How to explain it?
LEVEL 3 — HUMAN           Allow a high-risk / low-confidence decision?
```

The LLM **never mutates state**. It emits *candidate* resolutions and draft messages only. Every decision is recorded as a **decision trace** — `{decision, reasons[], knowledgeSources[], toolsUsed[], confidence, policyResult}` — the "show your work" artifact.

## Architecture — 7 layers, each earning its place

```
CUSTOMER  (Android · Google Messages · RCS)
   │  ▲  taps a card / carousel / PDF
   ▼  │
VONAGE Messages API  (RCS send + real inbound & status webhooks)  ·  FastAPI intake
                                     │
                                  RabbitMQ   (retry · backoff · DLQ · idempotency)
                                     │
                                     ▼
                         LangGraph Orchestrator  (stateful · interrupt · resume)
          ┌──────────────────────────┼───────────────────────────┐
          ▼                          ▼                            ▼
    Policy Engine             MCP Tools (read + action)      LlamaIndex RAG
  (deterministic authority)          │                    (manuals · warranty · SOPs)
                           ┌─────────┴─────────┐                 │
                           ▼                   ▼              pgvector
         Salesforce Field Service · e-com   Service-Commerce
         (service domain)   (products+stock) (quotes/orders) ──▶ Razorpay (Test)

  Underneath:  PostgreSQL (state · idempotency · audit · AI decisions · pgvector)
               Logfire (live request/case traces — the god-eye view)
```

| # | Layer | Tech | Why it's here |
|---|-------|------|----------------|
| 1 | Experience | **RCS** | Customer acts in the moment — no app, no call. |
| 2 | Communication | **Vonage Messages API** | Sends/receives RCS, delivery status, RCS→SMS failover. |
| 3 | Orchestration | **LangGraph** | A recovery case is long-running — checkpoint, interrupt, resume. |
| 4 | Knowledge | **LlamaIndex + pgvector** | RAG supplies the *knowledge* (fault codes, SOPs, compatibility). |
| 5 | Tools | **MCP** | Business systems as a small controlled tool surface, not 50 raw APIs in a prompt. |
| 6 | Enterprise | **Salesforce FS · e-com · Service-Commerce · Razorpay** | Service domain + product/stock + a thin commerce seam for quotes/pay. |
| 7 | Reliability | **RabbitMQ · idempotency · DLQ · reconciliation · Logfire** | Makes it credible as production, not a demo. |

> Anti-goal: *technology soup*. If a layer can't answer "why am I here" in one line, it's cut.

## RCS as the control plane (not a notification channel)

**The rule:** if a step *can* be done over RCS, it is. Every primitive maps to a real customer action.

| RCS primitive | What the customer does |
|---------------|------------------------|
| Rich card + actions | View appointment · Add to calendar · Change slot |
| **Carousel** (2–10 cards) | Pick one of several valid recovery slots |
| **Share location** (inbound) | Phone sends GPS → we compute technician ETA |
| **Inbound image** | Upload a photo of the unit label → vision + RAG |
| Quote card + **Open-URL webview** | Approve & Pay via the secure Razorpay page (RCS never sees card data) |
| **PDF rich card** (India) | Open the service report in-thread |
| **RCS → SMS failover** | Message still arrives if RCS is unavailable |

**The journey:** at-risk event → AI investigates → policy filters options → **carousel** of valid slots → tap → **share location** → **upload photo** → vision + **RAG** identify model/part → stock **reserved atomically** → **quote** → **pay** (webview) → **confirmation + calendar + PDF** report.

## Tech stack

- **Orchestrator** — Python · FastAPI · **LangGraph** (Postgres checkpointer) · async SQLAlchemy
- **AI** — **Groq** `gpt-oss-120b` → Gemini fallback → deterministic · **LlamaIndex** RAG · Jina embed + rerank · **pgvector** (209 chunks)
- **Tools** — **MCP** client + servers (Salesforce Hosted MCP + e-com MCP server) for the admin copilot
- **Messaging** — **Vonage Messages API** (RCS) · real inbound & status webhooks
- **Enterprise** — **Salesforce Field Service** (Apex record-trigger → HTTP callout) · **Razorpay** Test-Mode
- **E-com inventory** — **Next.js 15 + React 19 + Supabase** (live on Vercel, 86 parts, own MCP server)
- **Control panel** — React + Vite + Tailwind
- **Reliability / Ops** — **RabbitMQ** (retry · backoff · DLQ) · idempotency · reconciliation · **Logfire** traces
- **Infra** — Supabase (Postgres + pgvector) · CloudAMQP · Render · Vercel — all managed, env-driven

## What's real vs. mocked (honest POC scope)

**Real & live-verified:** LangGraph orchestration + interrupt/resume · Policy engine · RAG on real pgvector · LLM proposer · Salesforce reads/reschedule over Apex REST · **Vonage RCS card delivered to a real Android (2026-10-09)** · e-com inventory + its MCP server (Vercel) · Logfire · reconciliation · idempotency + DLQ.

**POC stand-ins (labelled in the decision trace):** photo-OCR, Share-Location ETA math, the PDF report body. The RCS primitives that carry them are real. Live billed sends (Vonage, Razorpay) are built and **gated** behind one arming switch. All customer data is **fake** — zero privacy exposure.

## Repo layout

```
apps/orchestrator/     Python · FastAPI + LangGraph (commerce is a module inside)
apps/ecom/             Next.js + Supabase inventory service + MCP server (Vercel)
apps/control-panel/    React · Vite · Tailwind (demo UI + admin copilot chat)
apps/salesforce-apex/  Apex trigger + 8 read-only MCP-shaped tools
packages/contract/     Pydantic models — the shared event/tool contract
infra/                 docker-compose: RabbitMQ · Postgres+pgvector · Prometheus · Grafana
docs/specs/field-service-recovery/   SRS · risks · roles · 7 context docs · diagrams
```

## Run it

Every command, curl, env and demo step lives in **[`playbook.md`](playbook.md)** (single source of truth). The short version:

```bash
make up      # infra: RabbitMQ · Postgres+pgvector · Prometheus · Grafana
make dev     # orchestrator (FastAPI :8000, consumer inside)
make panel   # control panel (Vite :5173)
curl -X POST http://localhost:8000/sim/appointment-at-risk   # fire the demo event
make test    # idempotency + spine end-to-end (in-memory, no infra needed)
```

Fire the same event twice → still **one** case, **one** card (idempotency).

## Deep dive

Start at **[`docs/specs/field-service-recovery/context/00-overview.md`](docs/specs/field-service-recovery/context/00-overview.md)**, then the 7 context docs (domain, orchestration & policy, knowledge & tools, RCS, reliability, principles). Requirements in [`srs.md`](docs/specs/field-service-recovery/srs.md), risks in [`risks.md`](docs/specs/field-service-recovery/risks.md), diagrams in [`diagrams/`](docs/specs/field-service-recovery/diagrams/).

---

<sub>A portfolio POC: real engineering on the hard parts (idempotency, policy authority, DLQ, decision trace, observability), managed free tiers everywhere, everything fake, ₹0 to run.</sub>
