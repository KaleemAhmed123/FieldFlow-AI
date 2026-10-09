# Context: System Overview

> **Living doc.** The shared mental model of FieldFlow AI — for the team and anyone new reading
> the codebase. It describes the whole target system. Built today: the walking-skeleton spine
> **plus the decision core** (real policy engine + full LangGraph flow with interrupt/resume +
> failure modes NFR-4/5/6, all mock-first — see [`../build-step-1.md`](../build-step-1.md)). The
> deeper layers (real tools, RAG, LLM, commerce) are planned. See [`../scaffold.md`](../scaffold.md)
> for exactly what runs now vs what's next.
>
> Requirements live in [`../srs.md`](../srs.md). Risks in [`../risks.md`](../risks.md). Who builds
> what in [`../roles.md`](../roles.md). Diagrams in [`../diagrams/`](../diagrams/).

## Product in one paragraph

**FieldFlow AI** is an AI field-service recovery system for home-services / appliance repair.
When a service appointment becomes **at risk** — technician running late, part missing, asset
more complex than booked — FieldFlow AI detects it from enterprise events, reasons over the full
operational context (customer, asset, warranty, technician, inventory, SLA, service knowledge),
validates every possible action against **deterministic business rules**, and negotiates the fix
with the customer entirely over **RCS** (Rich Communication Services — the upgraded SMS that
supports rich cards, carousels, buttons, image/location upload, payment links, calendar and PDF).
The customer picks a slot, shares location, uploads a photo of the unit, approves a quote and
pays — all inside the message thread. The system then executes the real changes across Salesforce
Field Service, inventory, a thin service-commerce layer and Razorpay, and stays consistent under
duplicate events, failures, unavailable systems and channel limits. Demo target: **Android +
Google Messages + India**, Transactional RCS agent, everything fake, ₹0 to run.

## The one idea that explains the whole system

**The AI proposes; deterministic policy decides; humans approve the risky calls. RCS is the
customer's control plane.**

Everything else follows from that one sentence:
- The **LLM never mutates anything directly** — it emits *candidate* resolutions and draft
  messages. A deterministic **Policy Engine** is the authority on what is allowed (see
  [`02-orchestration-and-policy.md`](02-orchestration-and-policy.md)).
- **MCP tools** are split into safe *read* tools and *controlled action* tools; the action tools
  are plain validated functions, not raw API handed to a model
  ([`03-knowledge-and-tools.md`](03-knowledge-and-tools.md)).
- **RCS is not a notification channel** — it is where the customer *acts*. If a step could be
  done over RCS, it is ([`04-rcs-experience.md`](04-rcs-experience.md)).
- **Salesforce owns the domain**, not us. We don't reinvent work orders, technicians or
  inventory ([`01-domain-and-data.md`](01-domain-and-data.md)).

If you remember only that sentence, you can predict where any new feature belongs.

## Architecture

See [`../diagrams/01-system-architecture.excalidraw`](../diagrams/01-system-architecture.excalidraw)
for the rich version. In text:

```
CUSTOMER (Android · Google Messages · RCS)
   │   ▲
   │   │ reply (card / carousel / PDF)
   ▼   │
VONAGE Messages API (RCS send + real inbound/status webhooks, 9b)  ·  FastAPI intake — /sim fires SF events
                                        │
                                     RabbitMQ  (retry · backoff · DLQ · idempotency)
                                        │
                                        ▼
                               LangGraph Orchestrator  (stateful · interrupts · resume)
             ┌──────────────────────────┼───────────────────────────┐
             ▼                          ▼                           ▼
       Policy Engine              MCP Tools (read+action)      LlamaIndex RAG
    (deterministic authority)           │                     (manuals · warranty · SOPs)
                              ┌──────────┴──────────┐                │
                              ▼                     ▼            pgvector
            Salesforce Field Svc · e-com     Service-Commerce
            (service domain)  (products+stock) (quotes/orders) ─▶ Razorpay (Test)

   Underneath:  PostgreSQL (state · idempotency · audit · AI decisions · pgvector)
                Logfire (live request/case traces — the god-eye view) · Prometheus (metrics, optional)
```

- **RabbitMQ** carries every event so nothing is lost under failure. **LangGraph** holds the
  long-running case state and pauses for the customer. For the POC, events are fired via `/sim`;
  the **Salesforce** inbound event is simulated via `/sim` (see [`../scaffold.md`](../scaffold.md)).
  **Vonage RCS inbound (customer taps) + status callbacks are real webhooks** — built in
  [`../build-step-9b.md`](../build-step-9b.md); `/sim/*` stays as the offline twin. (Razorpay payment
  stays a `/sim/payment` poll — no Razorpay webhook.)
- **Salesforce Pub/Sub API** (its event stream) is the intended inbound trigger — react to
  changes, don't poll. *Simulated via `/sim` in the POC.*

## The 7 layers (and why each earns its place)

| # | Layer | Tech | Why it's here (one line) |
|---|-------|------|--------------------------|
| 1 | Experience | **RCS** | The customer acts in the moment without an app or a call. |
| 2 | Communication | **Vonage Messages API** | Sends/receives RCS, reports delivery, does RCS→SMS failover. The only non-self-hostable layer. |
| 3 | Orchestration | **LangGraph** | A recovery case is long-running and needs human pauses — checkpoint, interrupt, resume. |
| 4 | Knowledge | **LlamaIndex + pgvector** | Salesforce has the data; RAG supplies the *knowledge* (fault codes, SOPs, compatibility). |
| 5 | Tools | **MCP** | Exposes business systems as a small controlled tool surface, not 50 raw APIs in a prompt. |
| 6 | Enterprise | **Salesforce FS + e-com inventory + Service-Commerce + Razorpay** | Service domain (SF) + product/stock (e-com) + a thin commerce seam for quotes/pay. |
| 7 | Reliability | **RabbitMQ + idempotency + DLQ + reconciliation + Logfire observability** | Makes it credible as production, not a demo. |

Full justification: [`../srs.md`](../srs.md) §6.1. The anti-goal is **technology soup** — if a
layer can't answer "why am I here" in one line, it's cut (risk R13).

> **Build decisions (2026-10-10) — making the stack honest (audit found 3 claimed-but-thin layers):**
> - **Layer 5 (MCP) becomes REAL**, not just MCP-shaped. **Driver:** a new **FieldFlow admin copilot**
>   — a chat on the control panel where an admin asks open-ended questions across Salesforce *and* the
>   e-com inventory. An open-ended agent can't hardcode every query→tool mapping; it must *discover and
>   pick* tools — exactly MCP's job (the one thing the deterministic pipeline didn't need). So:
>   **Salesforce Hosted MCP** (Headless 360) for SF + a small **e-com MCP server** for inventory,
>   consumed by a real MCP client (the copilot, and the orchestrator's read path). **Guardrail:** the
>   automated recovery pipeline keeps its policy ladder — MCP never fires a mutation unsupervised;
>   copilot writes stay human-confirmed. See [`03-knowledge-and-tools.md`](03-knowledge-and-tools.md) §B.
> - **Layer 7 Logfire** is being **properly wired** as the god-eye view (today it's only a config
>   placeholder; real observability is structlog + Prometheus). **Reconciliation** ships as a simple
>   pass (ponytail). Spec: [`../build-step-12-real-mcp-and-observability.md`](../build-step-12-real-mcp-and-observability.md).

## Component → where it will live

> The spine is scaffolded. This maps ownership across the full system.

| Component | Owner | Notes |
|-----------|-------|-------|
| Vonage adapter (send/receive/failover/capability) | You | Mocked today (FakeVonage); real once RCS access clears. |
| Event intake (`/sim`) + RabbitMQ topology | You | Correlation id stamped here. Salesforce inbound event simulated via `/sim`; **Vonage RCS inbound/status are real webhooks (9b)**. |
| LangGraph graph + Policy Engine | You | The decision core. |
| RAG index + retrieval (LlamaIndex/pgvector) | You | Knowledge layer. |
| MCP client | You | How the graph calls tools. |
| MCP servers over Salesforce | You + SF Dev | **Co-owned** — you want hands-on here. |
| Salesforce Field Service + Pub/Sub events | SF Dev | Service domain (appointment/asset/customer/technician/warranty) + the at-risk event source. |
| E-com inventory service (products + stock + admin dashboard) | You | **Separate source (Decision A)** — owns product image + price + stock. Real Node/Postgres service behind the `InventoryTools` seam; admin dashboard, no customer storefront. Stack/host TBD. |
| Service-Commerce (parts/quotes/orders/pay/refund) | You | A module **inside** the orchestrator (Python), not a separate app. **Built mock-first (Step 6):** price-book authority + `FakeRazorpay` behind a `PaymentGateway` seam; quote → Approve & Pay → capture, idempotent (no double-charge). Real Razorpay Test-Mode swaps in at the gated live step. |
| Razorpay Test-Mode integration | You | Open-URL/webview to a hosted page. |
| Observability (Logfire traces + Prometheus metrics) | You | God-eye view of every request and case. |
| Demo control panel | You | Live failure triggers for the showcase. |
| Admin copilot (panel chat) | You | **New (2026-10-10):** an MCP client — an LLM chat over SF Hosted MCP + the e-com MCP server, answering admins' open-ended queries. Reads freely; writes are human-confirmed. The agentic use case that justifies real MCP. |

## Glossary

- **At-risk appointment** — an appointment that won't go as scheduled (delay / missing part /
  complex asset). The trigger for a recovery case.
- **Recovery case** — one long-running workflow instance for one at-risk appointment, keyed by a
  **correlation id** (the work-order id in the demo).
- **Policy Engine** — deterministic code that decides whether a proposed action is legal/valid.
  The *authority*. The LLM is not.
- **Authority ladder** — Level 1 deterministic ("can this legally happen?") → Level 2 AI ("what's
  best?") → Level 3 human ("allow the risky one?").
- **RCS primitive** — one RCS capability: card, carousel, suggested reply, Open-URL/webview,
  share/view location, calendar, dial, inbound image, PDF card, status callback, SMS failover.
- **Transactional agent** — the RCS agent class for service messages (not promotional). The only
  class available in India; perfect for this POC.
- **MCP read tool / action tool** — read tools are safe lookups; action tools are validated
  mutating functions. The model may *call* an action tool but never decides its outcome.
- **Decision trace** — the recorded `{decision, reason[], knowledgeSources[], toolsUsed[],
  confidence, policyResult}` for every AI decision. The "show your work" artifact for the demo.

## Status flags (things that will look one way but aren't)

- **RCS does not process payments.** "Approve & Pay" opens a Razorpay page via Open-URL/webview.
  RCS carries the button, not the card number. Show this honestly (risk R7).
- **The AI is not the scheduler.** It never says "move it to 3 PM." It proposes options; the
  policy engine + Salesforce decide validity. Anyone wiring "let the LLM reschedule" is wrong.
- **Inventory is a SEPARATE e-com source, not Salesforce** (Decision A, 2026-10-10). The e-com
  owns product image + price + stock; Salesforce owns the service domain. See
  [`01-domain-and-data.md`](01-domain-and-data.md).
- **Commerce reuses patterns, not a domain.** The service-commerce layer borrows proven
  idempotency / payment / event / reliability patterns. We do **not** bolt an unrelated commerce
  engine onto appliance repair.
- **India = Android only** in Vonage coverage. An iOS demo will silently fail. Target is fixed.
- **No real data, ever.** Fake customers/assets/numbers/amounts. Removes privacy concerns whole.

---

*Last updated 2026-10-10 — Decision A (inventory = separate e-com source) + Step 9c (the at-risk
flow triggered by a real Salesforce Platform Event, mock-first).*
