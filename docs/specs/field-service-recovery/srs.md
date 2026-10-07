# FieldFlow AI — Software Requirements Specification (SRS)

**Status:** Planning · **Started:** 2026-10-06 · **Last updated:** 2026-10-06
**Audience:** internal engineering (you + the Salesforce dev) **and** the Vonage partner team.

A note on tone: this doc is practical enough to build from and formal enough to hand to
Vonage. Every technical term is explained once, where it first appears.

---

## 1. Problem statement

> When a home-service appointment becomes at risk — a technician runs late, a part is missing,
> the asset turns out to be more complex than booked — the customer today has one option: call
> support and wait. The operational systems (CRM, inventory, dispatch) know something is wrong,
> but nobody connects that knowledge to an action the customer can take in the moment.

**Industry signal (2026):** Salesforce research across 6,500 service professionals in 40
countries found nearly **half of appointments don't go as scheduled**, technicians lose **7+
hours/week** to admin, and **81%** believe AI agents could improve efficiency. The recurring
theme across 2026 CX research is that AI is deployed *siloed* from operational systems — there
is no layer connecting intelligence to real business action.

FieldFlow AI is that layer.

## 2. What FieldFlow AI is (and is not)

- **It is:** an AI decision-and-execution system. The customer completes the recovery through
  RCS; the system executes real changes across enterprise systems and stays consistent under
  failure.
- **It is not:** an "RCS chatbot". The AI never has unchecked authority — it *proposes*,
  deterministic rules *decide*, humans approve the risky calls.

**Terms used throughout:**
- **RCS** (Rich Communication Services) — the upgraded SMS successor. Supports rich cards,
  carousels, buttons, image/location upload, calendar and URL actions. Our customer interface.
- **Vonage Messages API** — the service that sends/receives RCS (and SMS) and reports delivery.
- **LangGraph** — a framework for long-running, stateful AI workflows that can pause, wait for
  a human/customer, and resume. Our orchestrator.
- **RAG** (Retrieval-Augmented Generation) — letting the AI read from a document store
  (manuals, warranty policy) instead of guessing. Powered by **LlamaIndex** + a vector database.
- **MCP** (Model Context Protocol) — a standard way to expose business systems to the AI as a
  small, controlled set of tools, instead of dumping raw APIs into a prompt.
- **Salesforce Field Service** — Salesforce's built-in model for work orders, appointments,
  technicians, skills, territories and parts inventory. Our system of record.

## 3. Goals & success criteria

| # | Goal | How we know it's met |
|---|------|----------------------|
| G1 | Demonstrate an end-to-end recovery, driven through RCS | A failed appointment is fully recovered via RCS taps, with no phone call. |
| G2 | Prove the AI is *constrained*, not trusted blindly | Every mutation shows an AI suggestion → policy check → (human if risky) → execute trace. |
| G3 | Showcase Vonage RCS capabilities in one coherent story | The "Vonage wow" checklist (§8) is hit in a single customer journey. |
| G4 | Prove production-grade reliability | All 6 failure scenarios (§9) are demonstrated live and recover correctly. |
| G5 | Cost ₹0 to run | Entire stack runs locally / on free tiers; only RCS needs partner enablement. |

## 4. Scope

### In scope
- One concrete scenario: **AC / appliance repair** (visually rich, maps cleanly to Field Service).
- The full 13-stage customer journey (§8) over RCS on Android / Google Messages / India.
- Salesforce Field Service as the domain + inventory system of record.
- A thin service-commerce layer (parts, quotes, orders, payments, refunds).
- Razorpay **Test Mode** payments (simulated, no real money).
- Reliability layer: RabbitMQ queue, idempotency, retries, DLQ, reconciliation, observability.
- A small internal demo control panel to trigger failures live.

### Out of scope
Kubernetes · multiple clouds · full ecommerce storefront · technician mobile app · real route
optimization · full Salesforce Agentforce · multi-tenant SaaS · WhatsApp/voice (initially) ·
complex billing · real production payments.

## 5. Actors

| Actor | Role |
|-------|------|
| **Customer** | Receives RCS, taps options, uploads photo/location, approves & pays. |
| **Technician** | (Simulated) triggers the real-world events — delay, on-site findings. |
| **AI orchestrator** | Investigates, generates recovery options, drafts messages. |
| **Policy engine** | Deterministic authority — decides which options are legal/valid. |
| **Human agent** | Approves high-risk or low-confidence decisions. |
| **Enterprise systems** | Salesforce, inventory, commerce, payment — the systems of record. |

## 6. System overview — the 7 layers

```
1. EXPERIENCE       RCS
2. COMMUNICATION    Vonage Messages API
3. ORCHESTRATION    LangGraph
4. KNOWLEDGE        LlamaIndex + vector RAG (pgvector)
5. TOOLS            MCP
6. ENTERPRISE       Salesforce Field Service + Service-Commerce + Inventory + Razorpay
7. RELIABILITY      RabbitMQ + idempotency + retries + DLQ + reconciliation + observability
```

Data path (core, synchronous-feeling but event-driven underneath):

```
Customer ─RCS→ Vonage ─webhook→ API Gateway ─→ RabbitMQ ─→ LangGraph
   └─ MCP tools (Salesforce / Inventory / Commerce)
   └─ LlamaIndex RAG (manuals / warranty / SOPs)
   └─ Policy engine (SLA / permissions / price / inventory)
        └─ execute → Salesforce + Commerce + Razorpay
             └─ reply → Vonage → RCS → Customer
```

### 6.1 Why each layer belongs (the justification Vonage will ask for)

- **RCS** — the customer must *act* at the exact moment opening an app or calling support
  creates friction. RCS turns the message thread into an interactive transactional surface:
  pick a slot, share location, upload a photo, approve a quote, pay, get a PDF — all inline.
- **Vonage Messages API** — sends/receives RCS, reports delivery/read, and does **RCS→SMS
  failover** and capability checks. This is the only layer that cannot be self-hosted.
- **LangGraph** — the real problem is a *long-running case* where new information arrives over
  time and some steps need a human/customer. LangGraph checkpoints state, pauses on an
  interrupt, and resumes — exactly what a recovery case needs. (Not "we wanted LangGraph".)
- **LlamaIndex + RAG** — Salesforce knows the *data* (asset = Daikin AC, warranty active) but
  not the *knowledge* (fault codes, repair SOP, part compatibility). RAG supplies that.
- **MCP** — exposes Salesforce/commerce/inventory as a small, controlled tool surface the AI
  can reason over, instead of stuffing 50 APIs into a prompt. Salesforce now ships Hosted MCP
  servers free in Developer Edition.
- **Salesforce Field Service** — already models Account, Asset, Case, WorkOrder,
  ServiceAppointment, ServiceResource, Skill, Territory, ServiceContract, WarrantyTerm, and a
  full inventory model (ProductItem, ProductTransfer, ProductConsumed…). We don't reinvent it.
- **Service-Commerce** — a tiny module (parts, quotes, orders, payments, refunds). Reuses proven
  transaction/idempotency/payment patterns, **not** an unrelated commerce domain.
- **Reliability layer** — this is what makes it credible as production, not a demo. See §9.

## 7. Why RCS specifically (the headline justification)

The demo deliberately exercises nearly every RCS primitive in one story, so RCS is *necessary*,
not decorative:

text update · rich card · carousel · suggested reply · suggested action · webview (Open URL) ·
share location · view location · dial · inbound image · calendar action · PDF rich card
(India / Google Messages) · delivery+read status callbacks · RCS→SMS failover · capability check.

If any of these were removed, the customer would be pushed back to a phone call or an app — the
exact friction FieldFlow AI exists to remove.

## 8. Functional requirements — the 13-stage journey

Each stage is a functional requirement. The **RCS primitive** column is what Vonage will want
to see. Scenario anchor: Work Order **WO-10281**, Daikin Inverter AC, today 10:00–12:00,
technician Rahul, Noida.

| ID | Stage | Behaviour | RCS primitive |
|----|-------|-----------|---------------|
| **FR-1** | Appointment created | Customer gets an appointment card with actions. | Rich card + suggested actions (View, Add to Calendar, Change Slot, Share Location) |
| **FR-2** | Failure happens | A simulated technician delay raises a Salesforce event `appointment.at_risk` onto RabbitMQ; LangGraph wakes. | (internal event) |
| **FR-3** | AI investigates | Graph loads appointment, technician, customer, asset, warranty, inventory; searches the service manual; evaluates SLA. | (internal) |
| **FR-4** | Options generated & validated | AI proposes recovery strategies; the **policy engine removes illegal ones** (skill, territory, travel time, working hours, SLA, entitlement, inventory, price authority). | (internal) |
| **FR-5** | Customer offered options | Valid slots sent as a swipeable carousel (2–10 cards). | **Carousel** |
| **FR-6** | Customer selects | Customer taps a slot; graph resumes. | Suggested reply / button |
| **FR-7** | Location shared | Customer shares GPS; backend computes technician ETA and confirms feasibility. | **Share location** → inbound location |
| **FR-8** | Evidence requested | Customer asked to photograph the AC model label; uploads it. | **Inbound image** |
| **FR-9** | Vision + RAG | OCR extracts the model; validated against the Salesforce Asset; LlamaIndex retrieves manual, warranty policy, part compatibility. AI concludes likely failure + compatible part. | (internal; LLM recommends, rules validate) |
| **FR-10** | Inventory check & reserve | MCP finds the part across depots; reserves 1 unit atomically. | (internal) |
| **FR-11** | Quote | Service-commerce builds a priced quote (part + labour + GST); sent as a card. | Rich card + actions (Approve & Pay / Ask / Decline) |
| **FR-12** | Payment | "Approve & Pay" opens a secure Razorpay Test-Mode page in a webview; success webhook updates order/payment state. | **Open URL / webview** |
| **FR-13a** | Confirmation | Customer gets a confirmation card: part reserved, technician, arrival window. | Rich card + actions (Track, Add to Calendar, **Dial** technician) |
| **FR-13b** | Service report | On work-order completion, a PDF service report is generated and delivered. | **PDF rich card** (India / Google Messages) |

**Cross-cutting functional requirement:**
- **FR-X (Decision trace):** every AI decision records `{caseId, decision, reason[],
  knowledgeSources[], toolsUsed[], confidence, policyResult}` so the demo can show *why* the AI
  chose what it chose.

## 9. Reliability / non-functional requirements (the failure demos)

These are **mandatory** — the Vonage team cares more about these than another pretty card.
Each is a live, triggerable scenario.

| ID | Scenario | Required behaviour |
|----|----------|--------------------|
| **NFR-1** | RCS unavailable / rejected | Automatic **RCS → SMS failover** via Vonage; workflow continues. |
| **NFR-2** | Duplicate webhook / duplicate customer reply | **Idempotency** on the RCS message UUID — second copy is ignored, no double action. |
| **NFR-3** | Salesforce temporarily down | Event not lost: **RabbitMQ retry → backoff → DLQ → reconciliation**. |
| **NFR-4** | AI low-confidence / risky recommendation | Routed to **human approval** before any execution. |
| **NFR-5** | Inventory changed between recommend and execute | **Atomic reserve** fails cleanly → graph resumes → recalculates options. |
| **NFR-6** | Customer replies against a stale workflow version | Conversation state versioned → **stale action rejected** → current options re-sent. |

**Other non-functional requirements:**
- **NFR-7 (Authority model):** three levels — (1) deterministic *can this legally happen?*,
  (2) AI *what's probably happening / best option?*, (3) human *allow high-risk?*. No mutation
  skips level 1.
- **NFR-8 (Latency):** AI calls are bounded — one decision call, one retrieval, one response
  generation. Everything else deterministic. No LLM→LLM→LLM chains in the hot path.
- **NFR-9 (Observability):** Prometheus/Grafana dashboards for AI decisions (auto / approval /
  escalation / rejected / failed), RCS delivery (sent / delivered / read / rejected / fallback),
  and workflow health (latency / retries / DLQ depth / recovery time). Fed by real Vonage status
  callbacks, not faked.
- **NFR-10 (Correlation):** a correlation ID threads every event, tool call, message and audit
  row for one case.

## 10. Data & privacy

- **Only fake data** — fake customers, addresses, assets, work orders, phone numbers, amounts.
  This removes privacy/compliance concerns entirely from the POC.
- Payments are Razorpay **Test Mode** — simulated, no money moves.
- Persistent state (conversation, workflow, idempotency keys, audit, AI decisions) lives in
  local PostgreSQL.

## 11. External dependencies & constraints

| Dependency | Constraint | Impact |
|-----------|------------|--------|
| **Vonage RCS** | Managed account + Developer Mode activation via account manager. | First thing to clear; blocks live RCS. |
| **India RCS** | Android-first in Vonage coverage; iOS not listed. | Demo target = Android + Google Messages. |
| **RCS agent config** | Use case + billing category **cannot be changed later**. | Choose **Transactional** carefully up front. |
| **Multi-use agents** | Not available in India. | Agent must be Transactional (fits the POC perfectly). |
| **Rich-card rendering** | Varies by device/client. | Test on the actual target device. |
| **Salesforce** | Use the **Field Service-enabled Developer Edition**, not a generic DE. | Avoids missing-feature surprises. |
| **Public webhook** | Vonage must reach localhost. | Cloudflare Quick Tunnel (no account/domain needed). |

Full severity/mitigation/owner tracking is in [`risks.md`](risks.md).

## 12. Assumptions

- The Vonage partnership clears RCS managed-account access (the critical path).
- The Field Service DE provides the objects and sample data we expect.
- Local hardware runs Docker (RabbitMQ, Postgres/pgvector, Prometheus, Grafana) comfortably.
- An LLM is available at ₹0 — local (Ollama) for guaranteed zero spend, or free API credit.

## 13. Glossary

**DLQ** — Dead-Letter Queue: where messages go after repeated processing failures, for later
reconciliation. **Idempotency** — processing the same message twice has the same effect as
once. **Pub/Sub API** — Salesforce's event stream for platform events and change-data-capture,
so we react to changes instead of polling. **pgvector** — a PostgreSQL extension that stores
embeddings for similarity search (the "vector database" for RAG). **Webview** — an in-message
browser surface opened by an Open-URL action (how the Razorpay page appears without leaving RCS).
