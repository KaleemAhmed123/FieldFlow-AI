# Context: Principles & Decisions

> **Living doc.** The engineering philosophy that keeps FieldFlow AI from becoming technology
> soup, plus the decisions already made and the ones still open. This is the doc to read when you
> want to know *why* the system is shaped the way it is.

## The principles (in priority order)

1. **AI proposes, policy decides, humans approve risk.** The single idea the whole system hangs
   on. If a design lets the LLM mutate state directly, it violates this.
2. **RCS is a control plane.** The customer *acts* in the thread. Any flow that pushes them to an
   app or a call for something RCS can carry is a design smell.
3. **Salesforce owns the domain; we own the case.** Don't reinvent work orders / technicians /
   inventory. Our storage is only conversation state, idempotency, audit, AI decisions, vectors.
4. **Every layer earns its place.** Seven technologies, each with a one-line justification
   (overview §"7 layers"). No layer "because it's impressive."
5. **Nothing lost, nothing twice, everything explainable.** The reliability contract.
6. **Deterministic over clever.** The boring validated function beats the clever prompt. The LLM
   is bounded to one decision / one retrieval / one response per step.
7. **Fake everything.** No real customer data in the POC — removes privacy/compliance concerns.
8. **Speed over production-grade complexity.** This is a POC to deliver *fast*. Deliberately cut
   production complexity when it isn't core to the demo story — e.g. skip inbound webhooks
   (simulate events via `/sim`), prefer managed free tiers over self-hosting, defer alembic/auth/
   dashboards. Add the hard parts only where they *are* the story (idempotency, policy, DLQ).

## Decisions already made

| Decision | Why | Rejected alternative |
|----------|-----|----------------------|
| **Field-service recovery** (appliance/AC) as the scenario | Strongest 2026 evidence; visually rich; maps perfectly to Salesforce FS; best "your fit" score | Delivery recovery · claims · healthcare · fraud (see [`../idea.md`](../idea.md) candidates) |
| **Salesforce owns domain + inventory** | FS model is already perfect; credible enterprise source of truth | Building our own domain/inventory tables |
| **Thin Service-Commerce**, not a storefront | We only need parts/quotes/orders/pay/refund | Bolting on a full unrelated commerce platform |
| **Commerce = reused patterns only** | Keep the story clean — a repair service, not a borrowed storefront | Presenting an unrelated product's domain as ours |
| **MCP read/action split** | Keeps dangerous ops as validated functions | Raw Salesforce API to the LLM |
| **RAG and MCP kept separate** | Knowledge vs live-data-and-actions are different problems | LlamaIndex as the orchestrator |
| **LangGraph as orchestrator** | Long-running, interruptible, resumable case state | n8n as the core transaction engine |
| **Transactional RCS agent, Android/India** | Only class available in India; fits the flow | Multi-use agent · iOS target |
| **₹0 local stack** | POC budget; everything self-hostable except RCS | Paid infra |
| **MCP-over-Salesforce co-owned** | You want hands-on on SF APIs/MCP | Handing all Salesforce to the other dev |
| **Service-Commerce = a module inside the orchestrator (Python)** | Fewer moving parts for a 2-person POC; still a clean internal package with its own APIs | Separate app (extra process + network hop) · keeping it in Node — revisit if it ever needs its own deploy |
| **Comprehensive, UI-rich Demo Control Panel** | The strongest live-demo surface for manager/Vonage | A minimal/scripted panel |
| **Managed free tiers** (Supabase DB, CloudAMQP queue, Groq/Gemini LLM) | Ship faster, ₹0, no infra to run or babysit | Self-hosting via local Docker |
| **LLM = both providers behind one switch** (`LLM_PROVIDER`) | Benchmark Groq vs Gemini free; keep the code simple | Committing to one provider now |
| **Inbound webhooks skipped** | POC speed — we fire events via `/sim`; no tunnel/host needed | Wiring Vonage/Razorpay inbound + a public URL |
| **Logfire for observability** (god-eye live tracing) | OTel-based, fits Python/FastAPI/Pydantic with almost no glue; one trace per case | Grafana-only dashboards · LangSmith (LLM-only) |

## What we deliberately will NOT build

Kubernetes · multiple clouds · full e-commerce storefront · technician mobile app · real route
optimization · full Salesforce Agentforce · multi-tenant SaaS · WhatsApp/voice (initially) ·
complex billing engine · real production payments.

> These don't improve the core demonstration. We prove **RCS + AI + Salesforce + MCP + RAG +
> Commerce + Payment + reliability** — we don't build a company. If one of these starts creeping
> in, stop and re-check against this list (risk R14).

## Open decisions (still to settle)

| # | Open question | Leaning | Settle by |
|---|---------------|---------|-----------|
| O1 | LLM provider / model | **DECIDED + BUILT (Step 5)** — fixed fallback ladder **Groq `openai/gpt-oss-120b` → Gemini `gemini-flash-latest` → deterministic** (not a switch; a provider is live if its key is set). Confidence is **evidence-weighted** (5 factors; LLM clamped so it can only lower, never inflate) with a **risk-tier floor** (`ALWAYS_HUMAN_REASONS`) — see [`context/02`](02-orchestration-and-policy.md). Free-tier model ids drift — verify per account. | — |
| O2 | Repo shape | **DECIDED** — monorepo: orchestrator (Python, **commerce as a module**) · control-panel (React) · contract package · infra. Scaffold a **thin spine first** (walking skeleton), then thicken. | — |
| O3 | How much of the demo control panel is real vs scripted | **DECIDED** — comprehensive, UI-rich; real state, real triggers; no faked telemetry | — |
| O4 | Reconciliation depth for the DLQ demo | Enough to show replay + resolve, not a full engine | P4 |
| O5 | Backend language | **DECIDED** — **Python** for both backends (orchestrator + commerce via FastAPI); **React** for the control panel | — |

Decisions get appended here as they're made (dated), never rewritten — same discipline as the
spec files.

## The problem statement (anchor everything to this)

> When a home-service appointment becomes at risk because of technician delays, inventory
> problems, asset complexity, or other operational exceptions, an AI recovery orchestrator gathers
> context from enterprise systems, reasons over service knowledge, validates possible actions
> against deterministic business policies, negotiates the best resolution with the customer
> through RCS, executes the resulting changes across Salesforce, inventory, commerce and payment
> systems, and remains resilient to duplicate events, failures, unavailable services and
> communication-channel limitations.

Not "AI chatbot using RCS." Not "Salesforce + MCP demo." Not "RCS rich-card demo." It is an
**AI-powered operational recovery system, with RCS as the customer's real-time control plane.**

---

*Last updated 2026-10-07 — kept in sync with the code as it lands.*
