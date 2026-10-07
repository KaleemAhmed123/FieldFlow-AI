# Context: System Overview

> **Design-time.** FieldFlow AI is not built yet. This folder describes the system **we intend
> to build** — the shared mental model for the team and for your manager — not code that exists
> today. As code lands, each file flips from "intended" to "how it works on `main`", ONLYCOUPLEZ-
> style. Inspired by `ONLYCOUPLEZ/docs/context`.
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
VONAGE Messages API ──webhooks──▶ API/Webhook Gateway (Node)
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
                     Salesforce Field Svc    Service-Commerce
                     (CRM + inventory)        (quotes/orders) ─▶ Razorpay (Test)

   Underneath:  PostgreSQL (state · idempotency · audit · AI decisions · pgvector)
                Prometheus / Grafana (observability)
```

- **REST + webhooks** for Vonage inbound/status. **RabbitMQ** carries every event so nothing is
  lost under failure. **LangGraph** holds the long-running case state and pauses for the customer.
- **Salesforce Pub/Sub API** (its event stream) is the inbound trigger — we react to changes, we
  don't poll.

## The 7 layers (and why each earns its place)

| # | Layer | Tech | Why it's here (one line) |
|---|-------|------|--------------------------|
| 1 | Experience | **RCS** | The customer acts in the moment without an app or a call. |
| 2 | Communication | **Vonage Messages API** | Sends/receives RCS, reports delivery, does RCS→SMS failover. The only non-self-hostable layer. |
| 3 | Orchestration | **LangGraph** | A recovery case is long-running and needs human pauses — checkpoint, interrupt, resume. |
| 4 | Knowledge | **LlamaIndex + pgvector** | Salesforce has the data; RAG supplies the *knowledge* (fault codes, SOPs, compatibility). |
| 5 | Tools | **MCP** | Exposes business systems as a small controlled tool surface, not 50 raw APIs in a prompt. |
| 6 | Enterprise | **Salesforce FS + Service-Commerce + Razorpay** | Credible source of truth + a thin commerce seam for parts/quotes/pay. |
| 7 | Reliability | **RabbitMQ + idempotency + DLQ + reconciliation + observability** | Makes it credible as production, not a demo. |

Full justification: [`../srs.md`](../srs.md) §6.1. The anti-goal is **technology soup** — if a
layer can't answer "why am I here" in one line, it's cut (risk R13).

## Component → where it will live

> Repo is not scaffolded yet (that's the next task). This is the *intended* map.

| Component | Owner | Notes |
|-----------|-------|-------|
| Vonage adapter (send/receive/failover/capability) | You | Mockable from day one; real once RCS access clears. |
| Webhook gateway + RabbitMQ topology | You | Correlation id stamped here. |
| LangGraph graph + Policy Engine | You | The decision core. |
| RAG index + retrieval (LlamaIndex/pgvector) | You | Knowledge layer. |
| MCP client | You | How the graph calls tools. |
| MCP servers over Salesforce | You + SF Dev | **Co-owned** — you want hands-on here. |
| Salesforce Field Service + Pub/Sub events | SF Dev | Domain + inventory + event source. |
| Service-Commerce (parts/quotes/orders/pay/refund) | TBD (You?) | **Now a module inside the orchestrator** (Python), not a separate app. Reuses Eudoro *patterns*, not its domain. Ownership to confirm. |
| Razorpay Test-Mode integration | You | Open-URL/webview + webhook back. |
| Observability dashboards | You | Fed by real Vonage status callbacks. |
| Demo control panel | You | Live failure triggers for the showcase. |

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
- **Salesforce is the inventory system too** — we do *not* build a separate inventory store
  unless Field Service access blocks us.
- **Eudoro is a pattern donor, not the domain.** We reuse its idempotency / payment / event /
  reliability patterns. We do **not** present a gift-commerce engine as appliance commerce.
- **India = Android only** in Vonage coverage. An iOS demo will silently fail. Target is fixed.
- **No real data, ever.** Fake customers/assets/numbers/amounts. Removes privacy concerns whole.

---

*Design-time snapshot: 2026-10-06 — Kaleem Ahmed*
