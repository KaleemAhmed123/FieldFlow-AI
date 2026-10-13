# Context: System Overview

> **Living doc.** The shared mental model of FieldFlow AI — written so an AI agent gets the complete
> picture *and* a new teammate or manager can follow what this is and why it's hard. It describes the
> whole system, and the whole system is **built and running live**: the orchestrator is deployed on
> Render, the e-com inventory service on Vercel, and the full AI pipeline (RAG → LLM → policy → RCS)
> fires end-to-end — including a real Rich-messaging card delivered to a real Android phone. See
> [`../../../../playbook.md`](../../../../playbook.md) for every command and the exact build status;
> [`../scaffold.md`](../scaffold.md) is the original spine plan (kept for history).
>
> Requirements live in [`../srs.md`](../srs.md). Risks in [`../risks.md`](../risks.md). Who builds
> what in [`../roles.md`](../roles.md). Diagrams in [`../diagrams/`](../diagrams/).

## In plain words (read this first)

**The pain it kills.** In home-appliance repair, booked appointments go wrong all the time — the
technician runs late, the needed part isn't on the van, the unit is more broken than booked. Today a
human agent scrambles to recover each one: phone calls, SMS, checking stock, rebooking, chasing a
payment. It is slow, it drops cases, and it costs money on every exception. **FieldFlow AI runs that
whole recovery automatically**, and lets the customer fix everything from inside one chat thread —
pick a new slot, share location, photograph the unit, approve a quote, pay — with no app and no phone
call.

**Where the AI is — and where it deliberately isn't** (this is the heart of the system):
- The **AI reads the whole situation** (customer, asset, warranty, technician, live stock, and the
  service manuals via RAG) and **proposes** what to do plus how to explain it to the customer.
- The AI **never changes anything itself.** A deterministic **policy engine** — plain, auditable
  code, no model — decides what is actually *allowed*, and a **human approves** anything risky or
  low-confidence.
- So the clever part (the AI) is fenced in by the safe part (the policy + the human gate). That
  fence is what makes an AI system trustworthy enough to touch real operations and real money. It is
  the one idea the rest of this doc hangs on.

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

Rich diagrams live in [`../diagrams/`](../diagrams/) (see its
[`README`](../diagrams/README.md) for the full set). The most useful:
**[`01-system-architecture`](../diagrams/01-system-architecture.excalidraw)** (this, drawn),
**[`05-ai-decision-pipeline`](../diagrams/05-ai-decision-pipeline.excalidraw)** (where the AI is and
how it's bounded), **[`06-mcp-two-modes`](../diagrams/06-mcp-two-modes.excalidraw)** (deterministic
vs agentic tool use), and **[`08-deployment-topology`](../diagrams/08-deployment-topology.excalidraw)**
(what runs where). In text:

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
  long-running case state and pauses for the customer. `/sim/*` fires any event offline (tests, demos).
  **Vonage RCS inbound (customer taps) + status callbacks are real webhooks** — built and
  **live-verified** in [`../build-step-9b.md`](../build-step-9b.md); `/sim/*` stays as the offline
  twin. (Razorpay payment stays a `/sim/payment` poll — no Razorpay webhook.)
- **The live Salesforce trigger** is an **Apex record-trigger → HTTP callout** to the orchestrator's
  `/webhooks/sf/at-risk` endpoint. Because the orchestrator is already public on Render, no tunnel or
  gRPC stream is needed. The heavier **Salesforce Pub/Sub API** subscriber (gRPC event stream) is
  built as a seam but **deferred as debt** — the HTTP callout is simpler and was chosen as the real
  path (decision 2026-10-12).

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
> - **Layer 7 Logfire** is wired as the god-eye view (one `logfire.configure()` + auto-instrumentation).
>   **Reconciliation** ships as a simple pass (ponytail). Spec: [`../build-step-12-real-mcp-and-observability.md`](../build-step-12-real-mcp-and-observability.md).
>
> **Status (live-verified 2026-10-13):** the **e-com MCP server is live** (Vercel, `POST /api/mcp`
> → 200); the **SF Hosted MCP server + admin-copilot client are built mock-first** (8 read-only Apex
> tools deployed; live arming of the Hosted MCP server is gated/deferred). **Logfire is live on
> Render** (deps all green), and the simple reconciliation pass is shipped (`GET /reconcile`). The
> deterministic recovery pipeline's Salesforce reads/reschedule run over **Apex REST**, not MCP.

## Component → where it will live

> The system is built and deployed. This maps ownership and current state across it.

| Component | Owner | State / notes |
|-----------|-------|---------------|
| Vonage adapter (send/receive/failover/capability) | You | `FakeVonage` default; real `VonageMessagesClient` built and **live-fired to a real Android (2026-10-09)**. Only the billed live send needs arming. |
| Event intake + RabbitMQ topology | You | Correlation id stamped here. **Live SF trigger = Apex → HTTP callout to `/webhooks/sf/at-risk`**; **Vonage RCS inbound/status are real webhooks (9b)**; `/sim/*` is the offline twin. |
| LangGraph graph + Policy Engine | You | The decision core — built, with real interrupt/resume + NFR-4/5/6; Postgres checkpointer live on Render. |
| RAG index + retrieval (LlamaIndex/pgvector) | You | **Live** (Supabase pgvector, 209 chunks, Jina embed+rerank). Grounds every decision. |
| MCP client | You | Real MCP client built for the **admin copilot** path; the deterministic pipeline uses an in-process Toolbox + Apex REST. |
| MCP servers over Salesforce | You + SF Dev | SF Hosted MCP + 8 read-only Apex tools **built mock-first + deployed**; live arming **deferred**. Deterministic reads run over **Apex REST**, live. |
| Salesforce Field Service + at-risk trigger | SF Dev | Service domain (appointment/asset/customer/technician/warranty). Live trigger = Apex record-trigger → HTTP callout; gRPC Pub/Sub deferred. |
| E-com inventory service (products + stock + admin dashboard) | You | **Separate source (Decision A)** — owns product image + price + stock. **Next.js + Supabase, live on Vercel** (`field-flow-ai.vercel.app`), 86 parts seeded, own MCP server live; admin dashboard, no storefront. |
| Service-Commerce (parts/quotes/orders/pay/refund) | You | A module **inside** the orchestrator (Python). Built (Step 6): price-book authority + payment gateway behind a seam; quote → Approve & Pay → capture, idempotent (no double-charge). Real Razorpay **Test-Mode** built; only the one live Test fire is gated. |
| Razorpay Test-Mode integration | You | Open-URL/webview to a hosted page; real `RazorpayGateway` built + poll-confirm. |
| Observability (Logfire traces + Prometheus metrics) | You | Logfire **wired and live on Render** — the god-eye trace of every request and case. |
| Demo control panel | You | React panel; live failure triggers for the showcase. |
| Admin copilot (panel chat) | You | An MCP client — an LLM chat over SF Hosted MCP + the e-com MCP server, answering admins' open-ended queries. **Built mock-first** (8 read-only tools); reads freely, writes human-confirmed. The agentic use case that justifies real MCP. |

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

*Last updated 2026-10-13 — refreshed to match the live system: orchestrator on Render + e-com on
Vercel (both live-verified), full AI pipeline (RAG + LLM) live, Vonage RCS live-fired, failure demos
+ Logfire shipped, e-com MCP live, admin copilot built mock-first, and the live SF trigger switched to
an Apex HTTP callout (gRPC Pub/Sub deferred).*
