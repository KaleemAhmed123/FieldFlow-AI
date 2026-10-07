# FieldFlow AI — The Idea (arranged research)

**Status:** reference · **Arranged:** 2026-10-06

This is the full research conversation, arranged into readable markdown. **Nothing has been
deleted** — the rejected candidate POCs (#2–#5) and the ranking are still here. Your own prompts
are kept in blockquotes marked **"You asked"**, with only obvious typos tidied. The untouched
raw original is at [`../../poc_idea.md`](../../poc_idea.md).

---

> **You asked (prompt 1):**
> I want you to look at my resume. I want you to grasp what I know and what I am capable of
> building, so we want to work on some complex scenario — not just a basic case study. Maybe we
> can integrate multiple platforms like Salesforce (there is a Salesforce dev in my team and I
> can do the commerce part), and an AI layer is a must, to have a decision layer. We can utilize
> LangGraph, MCP, LlamaIndex, vector RAG — all can be part of it. Salesforce can be optional too,
> or maybe we can change this after brainstorming. So come up with some problem of a different
> domain or something. Go ahead and research the problems people are facing as of October 2026,
> and how we can integrate an AI layer and then RCS messaging to finally interact and do the job.
>
> Do comprehensive research — take an hour or two, I have unlimited tokens, so scrape deep and
> come up with a problem worth solving that would give a great impression on the Vonage team,
> since they partnered with us so we could explore possibilities.

## My read of your capability

Your resume changes the type of POC we should build. You are already operating beyond CRUD/API
integration: you have built distributed, event-driven systems with RabbitMQ, idempotency,
reconciliation, dead-letter handling, Salesforce integration, AI extraction, RAG, human gates,
payments, commerce, and observability. You have also explicitly built systems where the model
is not trusted blindly and deterministic validation remains in control.

Your Eudoro work gives you a commerce/order/payments/event backbone, while Onlycouplez gives you
practical RAG, evaluation, privacy boundaries and AI safety experience.

Therefore, I would absolutely not build an "RCS chatbot". The POC should demonstrate an **AI
decision-and-execution system where RCS is the customer control surface**.

## What I researched as of October 6, 2026

The strongest recurring problem across current research is **fragmented operational systems +
customers expecting immediate resolution + AI being deployed without enough execution/control**.
A recent 2026 analysis cited by Tata Communications says CX improvement is lagging because AI
deployments remain siloed from data and operational systems; the recommendation is a contextual
intelligence/orchestration layer that connects intelligence to actual business actions.

That maps almost perfectly onto your skillset.

### The strongest current problem areas

| Problem | Current signal | AI req. | RCS value | Salesforce fit | Your fit |
|---------|----------------|---------|-----------|----------------|----------|
| **Field-service failures / appointment recovery** | Nearly half of appointments don't go as scheduled; technicians spend >7 hrs/week on admin | Very high | Very high | Excellent | 10/10 |
| Delivery exceptions / returns recovery | Delivery/returns are major purchase drivers; AI adoption high but exception handling weak | High | Very high | Good | 9.5/10 |
| Insurance claims orchestration | Claims remain fragmented; 22% use multiple channels for one query | Very high | Very high | Excellent | 9.5/10 |
| Healthcare access / scheduling | Timely appointments remain the biggest patient-access problem; auth/verification cause delays | Very high | High | Excellent | 8.8/10 |
| Fraud/scam intervention | Mobile increasingly central to scams and real-time intervention | Very high | High | Good | 8/10 |
| Travel disruption recovery | Disruption needs multi-system coordination and immediate customer action | High | Excellent | Moderate | 8.5/10 |

**Evidence highlights:**
- **Field service** — Salesforce's 2026 research across 6,500 service professionals in 40
  countries: nearly half of appointments don't go as scheduled, technicians lose 7+ hrs/week to
  admin, and 81% believe AI agents could improve efficiency.
- **E-commerce** — DHL's 2026 study (29,000 shoppers, 5,800 businesses, 29 countries): 7 in 10
  shoppers would abandon a brand over poor delivery/returns options; 9 in 10 businesses say
  delivery/returns matter to online sales. Bringg's 2026 last-mile research: AI adoption is high
  for routing/visibility but only 28% for exception handling, 26% carrier management, 25% billing
  reconciliation — exactly the ugly operational workflows your background fits.
- **Insurance** — Deloitte's 2026 analysis (~4,000 policyholders): many claims processes remain
  complex, fragmented, unclear; 22% use multiple channels for one query; only 36% auto / 31%
  homeowner customers get mobile updates. Deloitte points to AI + human judgment + better comms.
- **Healthcare** — Experian Health's 2026 survey: timely appointments remain the biggest
  patient-access problem; authorization and insurance verification cause delays. *But* I would
  not pick healthcare first — compliance, clinical safety and PHI add complexity that doesn't
  showcase Vonage better.

## My recommendation: build this

### AI Service Recovery Orchestrator
*"When field service goes wrong, the system fixes it."*

Don't make it specific to one company initially. Make the platform generic — telecom, HVAC,
appliance repair, internet installation, home services, industrial equipment, automotive
service, medical equipment, utilities — then demonstrate it with one concrete scenario such as
premium appliance / AC / telecom service.

**The problem:** a customer has a service appointment. Something goes wrong somewhere in the
operational chain. Instead of forcing the customer to call support, a network of AI + business
systems detects the problem, determines the best resolution, asks the customer for the minimum
required input through RCS, executes the resolution across Salesforce/commerce/inventory/
dispatch/payment systems, and keeps everyone synchronized.

That is dramatically more interesting than `Customer → RCS → AI → Answer`. Our system becomes:

```
                     BUSINESS EVENT
                           │
                           ▼
                    Salesforce / ERP
                           │
                     Event detected
                           │
                           ▼
               ┌─────────────────────┐
               │ AI Decision Engine  │
               │     LangGraph       │
               └──────────┬──────────┘
                          │
              ┌───────────┼─────────────┐
              ▼           ▼             ▼
          Salesforce   Inventory      Knowledge
          / CRM        / Commerce      RAG
              │           │             │
              └───────────┼─────────────┘
                          ▼
                    Decision Policy
                          │
                 ┌────────┴────────┐
                 ▼                 ▼
             Auto-execute      Human review
                 │                 │
                 └────────┬────────┘
                          ▼
                     RCS / Vonage
                          │
                          ▼
                       CUSTOMER
                          │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
          Reply        Location      Photo
             │            │            │
             └────────────┼────────────┘
                          ▼
                  AI / Workflow resumes
                          │
                          ▼
                   Execute changes
                          │
                          ▼
                  Salesforce / ERP
```

That is a real agentic operational system, not an AI demo.

### Concrete scenario

An appliance/AC repair company (extremely visual flow).

**09:00 — Salesforce has:** Customer Kaleem Ahmed · Asset Daikin AC · Work Order WO-18372 ·
Appointment 10:00–12:00 · Technician Ravi · Required skill: Daikin inverter diagnostics ·
Required part: PCB-492.

**09:25 — Salesforce receives an operational event:** technician's previous job +55 min delay.
At the same time: inventory PCB-492 unavailable.

A traditional system might simply leave the appointment broken. Our system sees appointment risk
+ technician delay + missing part + customer SLA + technician skills + inventory + historical
service data, and sends that context to the AI decision engine.

**The AI doesn't just answer.** LangGraph could execute:

```
START → Load Case → Load Customer Context → Load Asset History → Load Work Order →
Check Technician → Check Inventory → Retrieve Troubleshooting Knowledge →
Generate Resolution Options → Policy / SLA Validation
         ├── Low-risk  → auto action
         └── High-risk → human approval
                 └──────┬──────┘
                        ▼
                     Execute
```

This is exactly where LangGraph is appropriate: stateful orchestration, persistence,
interruptions and human-in-the-loop control for long-running workflows.

**The system might discover 4 possible resolutions:**
- **Option A** — Send another technician, ETA 11:00, cost +₹0.
- **Option B** — Reschedule tomorrow 10–12, cost +₹0.
- **Option C** — Remote diagnosis first, potentially avoid site visit.
- **Option D** — Replace PCB, part available at nearby warehouse, ETA tomorrow, ₹4,800.

But the LLM doesn't get to say "let's replace the PCB." We use your existing engineering
philosophy:

```
LLM → Candidate decisions → Deterministic policy engine → SLA check → Inventory check →
Customer entitlement → Price limits → Permission check → Execute
```

That is much more impressive to an enterprise audience.

### Then RCS becomes the actual customer interface

```
┌─────────────────────────────────┐
│ 🔧 Service update                │
│                                  │
│ Your technician is delayed       │
│ by approximately 45 minutes.     │
│                                  │
│ We found these options:          │
│ ┌─────────────────────────────┐ │
│ │ Today  11:00 – 13:00         │ │
│ │ Same technician   [ Choose ] │ │
│ └─────────────────────────────┘ │
│ ┌─────────────────────────────┐ │
│ │ Tomorrow  10:00 – 12:00      │ │
│ │ Earlier slot      [ Choose ] │ │
│ └─────────────────────────────┘ │
│ [ Speak to support ]             │
└─────────────────────────────────┘
```

RCS is excellent for this because it supports rich cards, carousels, suggested replies, and
device actions.

### Then make it much more complex

Customer chooses "11:00–13:00". The system updates: `Salesforce ServiceAppointment → Dispatch →
Technician → Customer`. Salesforce Field Service already models the exact concepts we need: Work
Orders, Service Appointments, Assets, Service Resources, Skills, Territories, etc. And
Salesforce's **Pub/Sub API** is designed for event-driven integration — an external app can
publish/subscribe to platform events and change-data-capture events. That gives your Salesforce
teammate a real engineering contribution, not just "we connected the REST API".

### Now introduce the commerce part

The technician arrives and discovers the PCB is actually damaged; uploads a photo of the PCB. The
customer is asked to upload a photo of the unit label. (RCS can receive inbound images, files and
locations as well as replies/buttons.)

Your AI pipeline: `Image → Vision model → Extract model number → Validate → RAG → Compatible
parts → Inventory → Pricing → Warranty → Decision`.

Suppose: Warranty YES · Part free · Inventory available in Noida warehouse · Delivery tomorrow.

```
┌───────────────────────────────┐
│ Replacement Part              │
│ PCB-492                       │
│ Covered under warranty  ₹0    │
│ Available tomorrow            │
│ [ Approve replacement ]       │
│ [ Ask technician ]            │
└───────────────────────────────┘
```

Customer taps **Approve replacement**. Commerce layer: `Reservation → Inventory hold →
Purchase/work-order line → Salesforce → Technician assignment → Appointment update`. This is
where your Eudoro experience becomes directly useful.

### Now add payment

For out-of-warranty work: Repair ₹4,800 · Diagnostic ₹500 · Tax ₹954 · Total ₹6,254.

```
Repair quote: ₹6,254
Includes: ✓ PCB  ✓ Labour  ✓ Installation
[ Review & Pay ]  [ Reject ]  [ Ask Question ]
```

The **Open URL** suggested action launches your secure payment page; Vonage/RCS supports native
URL, dialing, location and calendar actions. Your Razorpay knowledge becomes useful here.

### Then send the final service report through RCS

Particularly interesting for India: Google currently supports **PDFs in RCS rich cards** on
Google Messages in India. So: "Service completed. Your service report is ready. [ View Report ]"
with the PDF. The Vonage team sees an India-specific capability, not a theoretical feature.

### And now the really interesting part — we intentionally break things

- **Failure 1 — Vonage returns RCS rejected:** `RCS → rejected → SMS fallback`. Vonage supports
  RCS → SMS failover in the Messages API.
- **Failure 2 — Salesforce temporarily unavailable:** `Event → RabbitMQ → retry → backoff → DLQ
  → reconciliation`. Already an area your resume shows deeply.
- **Failure 3 — LLM produces a questionable recommendation:** `confidence < threshold → human
  approval`.
- **Failure 4 — Customer sends "Actually don't repair it, just refund me."** The graph loads
  existing state and decides whether refund is permitted.
- **Failure 5 — Customer sends the same reply twice:** `RCS message ID → deduplication key →
  already processed → ignore`.
- **Failure 6 — Customer's device doesn't support the desired RCS functionality:** capability
  check → YES/NO → RCS or fallback. Vonage provides individual and bulk capability checks.

### Now we have something much bigger than RCS

```
                     ┌───────────────────┐
                     │ Salesforce        │
                     │ CRM / Field Svc   │
                     └─────────┬─────────┘
                         Pub/Sub Events
                               ▼
                     ┌───────────────────┐
                     │ Event Gateway     │
                     │ Node.js           │
                     └─────────┬─────────┘
                            RabbitMQ
                               ▼
                  ┌─────────────────────────┐
                  │ LangGraph Orchestrator  │
                  │ Stateful Agent          │
                  │ Decision Engine         │
                  │ Human Interrupts        │
                  └───────────┬─────────────┘
          ┌───────────────────┼────────────────────┐
          ▼                   ▼                     ▼
   Salesforce MCP        Commerce MCP         Knowledge MCP
          │                   │                     │
     CRM/Field Svc      Inventory/Payments     LlamaIndex RAG
          └─────────┬─────────┘
                    ▼
               Policy Engine
          ┌─────────┴─────────┐
          ▼                   ▼
       Execute            Human approval
          └─────────┬─────────┘
                    ▼
            Vonage Messages API
                    ▼
            ┌──────────────┐
            │ RCS Customer │
            └──────┬───────┘
         replies / images / location / actions
                    ▼
              Back to LangGraph
```

MCP standardizes how AI systems access tools and data sources — think of Salesforce, commerce,
inventory and operational systems as controlled tools exposed to the agent, rather than stuffing
their APIs into every prompt.

### Where LlamaIndex fits

Not as the overall orchestrator. Use it for knowledge:

```
service manuals + warranty rules + SOPs/policies → LlamaIndex → retrieval/RAG → LangGraph state
```

Example: *"Does PCB-492 work with model XYZ-438?"* is a retrieval/grounding problem. *"Should we
repair, replace, reschedule or escalate?"* is an orchestration/decision problem. Keep them
separate.

### Where MCP fits

Create tools such as:

```
salesforce.getCustomer()   salesforce.getAsset()      salesforce.getWorkOrder()
salesforce.updateAppointment()
inventory.checkAvailability()   inventory.reservePart()
commerce.getQuote()   commerce.createOrder()   commerce.createPaymentLink()
routing.getETA()   routing.findTechnician()
knowledge.searchManual()   knowledge.searchWarrantyPolicy()
vonage.sendRCS()   vonage.sendCarousel()   vonage.sendFallback()
```

Then LangGraph reasons over a controlled tool surface — much cleaner than `LLM → huge prompt →
50 APIs`.

### Why Salesforce is worth adding

Not because it "looks impressive" — because it gives a credible enterprise source-of-truth:
Account, Contact, Asset, Case, Work Order, Service Appointment, Service Resource, Service
Territory, Service Contract. Those are actual Field Service concepts in Salesforce's current
model, and the Pub/Sub API provides a proper event-driven integration layer. The demo shows
`CRM → Event Bus → AI → Operational systems → RCS → Human → back into CRM`, rather than
`API → chatbot`.

### Why RCS is genuinely necessary here

The key question the Vonage team will subconsciously ask is *"Why RCS?"* — because the customer
needs to perform actions at moments when opening an app or calling support creates friction. RCS
provides appointment choice + rich cards + carousel + suggested replies + location sharing +
photos/videos/files + calendar actions + URLs/payment + native messaging. Vonage currently
exposes outbound RCS text/media/cards/carousels and inbound text/media/location/reply/button
events. That gives us an interactive transactional interface, not just a notification channel.

### India's advantage

Vonage's current coverage lists **India for Android RCS**, while iOS RCS coverage does not
currently include India. More importantly, Google's RCS docs specifically support **PDF
rich-card content in India on Google Messages**. So the POC targets **Android + Google Messages
+ Indian test numbers**, rather than an artificially universal first demo.

### One architectural constraint

For India, **Multi-use RCS agents are currently unavailable**. Transactional agents are globally
available; promotional use has additional Indian restrictions. That makes our POC cleaner — we
classify the agent as **Transactional** and keep the demo around existing service / appointment /
customer / work order / service recovery / completion / payment / documents. No promotional
messaging needed. Google's `messageTrafficType` model also distinguishes categories such as
TRANSACTION and SERVICEREQUEST, useful for a system like ours.

---

## Candidate #2: AI Delivery Exception & Returns Rescue

My second choice, possibly the best alternative given your Eudoro experience.

```
Order shipped → Carrier delay → AI detects SLA risk → Customer receives RCS →
"Your order will miss its promised date."
[ Deliver tomorrow ] [ Pickup nearby ] [ Change address ] [ Cancel ]
```

Then: `AI → Order DB → Carrier APIs → Inventory → Refund engine → RCS`. Could become far more
sophisticated: `package damaged → customer sends photo → vision model → fraud/risk model → order
history → carrier telemetry → policy/RAG → refund / replacement / investigation`.

Timely because 2026 research shows delivery/returns remain major pain points while AI adoption is
concentrated in route optimization rather than exception handling. **Score: 9.5/10.**

## Candidate #3: AI Claims Resolution Concierge

Fits your resume frighteningly well.

```
Claim detected → RCS → "Upload damage photos" → Customer sends images → Vision/OCR →
Policy RAG → Claim extraction → Fraud/risk signals → Missing-evidence detection →
AI determines next action → Salesforce case → Human adjuster when needed → RCS updates
```

Your Primble experience already includes OCR → extraction → deterministic-first processing →
evidence gating → remediation. Current insurance research validates fragmented claims
communication as a real problem. **Score: 9.5/10.** Downside: it overlaps with what you already
know, so it teaches the Vonage team less about your ability to enter a new domain.

## Candidate #4: AI Patient Access Orchestrator

```
Patient → RCS → "I need an appointment" → AI → Insurance verification → Provider availability →
Authorization status → RAG → Appointment selection → Calendar → Payment estimate → RCS
```

Healthcare has genuine 2026 problems around appointment access, authorization, insurance
verification and administrative burden. But keep it a future option — it puts us into safety,
privacy and clinical-risk territory unnecessarily.

## Candidate #5: AI Fraud Intervention

```
transaction → risk engine → AI evaluates context → RCS → "Did you authorize this?"
[ Yes ] [ No ] [ Freeze ] → banking workflow
```

Very strong technically, but financial fraud decisions are high-stakes and bring much more
regulatory/security pressure. I'd rank it below the others.

---

## What will impress Vonage the most

Not the number of technologies ("LangGraph + MCP + RAG + Salesforce + n8n + RCS") — that becomes
technology soup. The impressive thing is:

> "We selected a real operational problem, built an AI agent that reasons over enterprise
> context, constrained its authority using deterministic policies, exposed business systems as
> tools, allowed the customer to complete the workflow through RCS, and designed the whole thing
> to survive retries, duplicate events, unavailable systems, RCS capability differences and human
> escalation."

That is the story.

### The POC's 7 layers

```
1. EXPERIENCE       RCS
2. COMMUNICATION    Vonage Messages API
3. ORCHESTRATION    LangGraph
4. KNOWLEDGE        LlamaIndex + vector RAG
5. TOOLS            MCP
6. ENTERPRISE       Salesforce + Commerce + Inventory + Payment
7. RELIABILITY      RabbitMQ + idempotency + retries + DLQ + reconciliation + observability
```

Your experience covers almost every layer already.

### One architectural recommendation

Do **not** make n8n the core transaction engine. Use n8n around the edges (CRM notification,
scheduled jobs, email, Slack, admin workflows, prototype integrations, non-critical automation).
Keep the core path `RCS → API → RabbitMQ → LangGraph → deterministic services → transaction`,
because the POC must prove you can build a production-grade system, not wire together SaaS nodes.

### Every important RCS capability in one story

```
TEXT → RICH CARD → CAROUSEL → SUGGESTED REPLY → LOCATION ACTION → IMAGE (inbound) →
URL ACTION (payment) → CALENDAR ACTION → PDF (report/quote) → STATUS CALLBACK → FAILOVER (→SMS)
```

All real RCS primitives documented by Vonage/Google. The POC becomes almost a capability
showcase for Vonage itself.

### The hard engineering to show

✓ duplicate webhook ✓ duplicate customer reply ✓ delayed Salesforce event ✓ failed inventory API
✓ model uncertainty ✓ human approval ✓ RCS capability failure ✓ RCS rejection ✓ SMS fallback
✓ RabbitMQ retry ✓ dead-letter queue ✓ reconciliation ✓ distributed correlation ID ✓ audit trail
✓ AI decision trace ✓ cost/latency metrics.

### RCS is still evolving

Google's RCS for Business had active 2026 changes (persistent suggestions, India-specific
promotional limits; rich-card docs updated Aug 25, 2026). Vonage lists India Android coverage,
RCS capability checks, a default RCS channel rate limit of 75 req/s per API key, and RCS → SMS
failover. A good moment to build against it.

### My ranking

| | RCS | AI | Salesforce | Commerce | Wow |
|---|---|---|---|---|---|
| **Field Service** | ★★★★★ | ★★★★★ | ★★★★★ | ★★★★★ | **10/10** |
| Delivery Recovery | ★★★★★ | ★★★★★ | ★★★★☆ | ★★★★★ | 9.5/10 |
| Claims Concierge | ★★★★★ | ★★★★★ | ★★★★★ | ★★★★☆ | 9.5/10 |
| Healthcare Access | ★★★★☆ | ★★★★★ | ★★★★★ | ★★★☆☆ | 8.8/10 |
| Travel Recovery | ★★★★★ | ★★★★☆ | ★★★☆☆ | ★★★☆☆ | 8.5/10 |
| Fraud Intervention | ★★★★☆ | ★★★★★ | ★★★★☆ | ★★☆☆☆ | 8/10 |

### The one I would actually build

**AI Service Recovery Orchestrator** — a field-service system that autonomously detects broken
appointments, reasons across CRM + asset + technician + inventory + knowledge + SLA data,
negotiates the resolution with the customer through RCS, executes the resulting changes across
Salesforce/commerce/operations, and maintains consistency through an event-driven architecture.

The killer demo moment is not "look, RCS sends a rich card." It is:

```
Technician problem → AI detects operational failure → AI determines 3 valid resolutions →
RCS negotiates with customer → Customer sends image/location → AI retrieves domain knowledge →
Inventory + Salesforce + commerce consulted → Customer approves → Real transaction executed →
Salesforce updated → Technician updated → Payment/appointment/inventory synchronized →
PDF/report delivered → Everything observable + auditable
```

It makes RCS the missing interaction layer in an otherwise complete enterprise decision-and-
execution system.

---

> **You asked (prompt 2):**
> I want to solve this: **Field-service failures / appointment recovery** (Home Service and
> Appliance repair as one).
>
> **First** — constraints: since it's just a POC, everything needs to be free for testing;
> mention other friction I can't see.
>
> **Second** — these are must-haves in the flow and should justify why they're there, not just
> for the sake of it, especially RCS; most communication must be done with RCS:
> RCS · Vonage Messages API · LangGraph · LlamaIndex + vector RAG · MCP · Salesforce + Commerce +
> Inventory + Payment · RabbitMQ + idempotency + retries + DLQ + reconciliation + observability.
>
> **Third** — expected time, effort and overall complexity.
>
> **Fourth** — about platforms: does the Salesforce dev org have all the Field Service things you
> mentioned, and will we have to create an e-commerce platform? I already have the Eudoro platform
> — can I just integrate it (portray it as inventory/tools, though it's a customized-gifts
> platform), or should we build new, or skip it (maybe use Salesforce as inventory)? Does
> Salesforce support MCP, and how is AI helpful there — because that could be friction?
>
> **Fifth** — use cool actions: location sharing, payment (Razorpay), calendar, beautiful cards,
> and every amazing RCS action; we want an almost app-like experience, to impress Vonage partners.
>
> Answer this, and add stuff I should have asked too, so you know where we're going.

Yes — I would lock the POC around **Field-Service Failure & Appointment Recovery** for Home
Services / Appliance Repair, with one important change: **Salesforce should own the field-service
domain and inventory** where possible; we build only a **thin repair-commerce/payment layer**,
not another e-commerce platform. Your Eudoro experience is reused as engineering patterns and
possibly selected services, not presented as an appliance-commerce system.

### 1. Can we build this for ₹0?

Almost entirely; RCS is the only unavoidable commercial dependency.

| Component | POC cost | Recommendation |
|-----------|----------|----------------|
| Salesforce Developer Edition | ₹0 | Use a Field Service-enabled Developer Edition |
| Salesforce Hosted MCP | ₹0 in DE | Use it — extremely valuable for the POC |
| Salesforce Field Service | ₹0 for the special DE | Use the **special Field Service DE**, not any generic DE |
| Vonage RCS | Possibly ₹0 initial credit, not inherently free | Your Vonage partnership is the critical dependency |
| Vonage Messages API | Free credit available | "Try it free"/no card advertised, but RCS still needs managed-account enablement |
| LangGraph | ₹0 | Local/open-source |
| LlamaIndex | ₹0 | Local/open-source |
| MCP | ₹0 | Open protocol + local/hosted servers |
| LLM | ₹0 possible | Local Ollama model for guaranteed zero API spend |
| Vector DB | ₹0 | PostgreSQL + pgvector locally |
| RabbitMQ | ₹0 | Docker locally; open source |
| Prometheus / Grafana | ₹0 | Docker |
| Loki | ₹0 | Optional |
| Razorpay | ₹0 | Test Mode; simulated, no real money |
| Public webhook | ₹0 | Cloudflare Quick Tunnel |
| Eudoro | ₹0 additional | Don't make it the domain model; reuse patterns |
| Hosting | ₹0 | Run everything locally |

Salesforce provides free Developer Edition environments; Field Service core, its managed package
and mobile app are available in DE, and there is a special Field Service DE for exactly this kind
of testing. Salesforce's April 2026 update brought **Hosted MCP Servers into DE at no cost**.
Vonage is the one caveat: RCS is available only to managed accounts and needs your account
manager to activate Developer Mode — clear this first. RabbitMQ is free/open-source with an
official Docker image; Cloudflare Quick Tunnels give temporary public URLs without an
account/domain; Razorpay Test Mode is simulated.

### 2. The architecture I would build

```
CUSTOMER ─RCS→ VONAGE Messages API ─inbound/status webhooks→ API / Webhook Gateway ─→ RabbitMQ
   ─→ LangGraph (Conversation / Decision Orchestrator)
        ├── MCP Servers (Salesforce MCP · Inventory MCP · Commerce MCP)
        │       └─ Customer · Asset · Case · Work Order · Service Appointment ·
        │          Technician · Territory · Skills · Inventory → Repair Commerce → Razorpay Test
        ├── LlamaIndex + RAG
        └── Policy Engine (deterministic rules: risk / SLA / permissions)
```

Beneath everything:

```
RabbitMQ      → retry · DLQ · idempotency · events · async execution
PostgreSQL    → conversation state · workflow state · idempotency keys · audit trail · AI decisions
Prometheus/Grafana → latency · RCS delivery · AI latency · workflow failures · queue depth · recovery success
```

### 3. Why every technology belongs

**RCS — the customer interaction layer.** Must be primary, not an ornament. The customer performs
most meaningful actions over RCS: appointment selection, confirmation, rescheduling, technician
ETA, location sharing, photo upload, part approval, quote approval, payment initiation, calendar
creation, service report, human escalation. RCS supports rich cards, carousels, suggested
replies, Open URL/webview, dial, view/share location and calendar actions; rich cards can carry
**PDFs** (India / Google Messages). So instead of "Your appointment changed," we demonstrate the
full flow: beautiful cards → pick slot → share location → upload evidence → approve quote → open
payment → add to calendar → receive PDF report.

**LangGraph.** The problem isn't "ask an LLM what to say"; it's "maintain a long-running
operational case while multiple systems produce new information, decisions require state, and
some actions require human/customer approval." LangGraph's interrupt/persistence mechanism is
built for long-running, human-in-the-loop workflows: state can be checkpointed, paused and
resumed.

**LlamaIndex + vector RAG.** We need domain knowledge, not just DB data. Salesforce says
"Asset = Daikin AC, warranty active" but not the service manual, fault codes, repair procedures,
warranty policy, SOPs, safety instructions, part compatibility, escalation rules. RAG supplies
that: PDF manuals / warranty docs / SOPs / policy / catalogs / troubleshooting → chunk → embed →
pgvector → retrieval → LangGraph. Clean separation: **MCP = live data/tools, RAG = knowledge,
LangGraph = orchestration, Policy engine = authority.**

**MCP.** Salesforce now supports MCP directly in DE. Hosted MCP exposes Salesforce data/logic to
MCP clients while respecting Salesforce security/permissions. Endpoints include
`platform/sobject-reads`, `platform/sobject-all`, `platform/salesforce-api-context`. The Headless
360 MCP Server offers a small stable tool surface; custom Apex can be exposed as hosted MCP tools.
**Don't give the LLM unrestricted Salesforce access.** Instead:
- **Read tools:** `get_customer`, `get_asset`, `get_work_order`, `get_appointment`,
  `get_technician`, `get_inventory`.
- **Controlled action tools:** `propose_reschedule`, `confirm_reschedule`, `reserve_part`,
  `create_service_quote`, `create_payment_request`, `close_work_order`.
  Dangerous operations are deterministic functions with validation.

**AI is NOT the scheduler.** Don't do `LLM: "Move appointment to 3PM."` Instead: AI says "these
are the three viable recovery strategies" → Policy Engine checks technician availability,
territory, skill, SLA, entitlement, travel time, working hours, inventory, price authority →
valid options → customer. Salesforce/deterministic code remains the authority for whether a
proposed action is valid.

**Salesforce — use it heavily.** The Field Service model is almost suspiciously perfect:
Account, Contact, Asset, Case, WorkOrder, WorkOrderLineItem, ServiceAppointment, ServiceResource,
ServiceResourceSkill, ServiceTerritory, Skill, SkillRequirement, ServiceContract, WarrantyTerm,
ServiceReport, and more. We don't invent technician/appointment/asset/work-order tables.

**Salesforce as our inventory system** (even better): Product, ProductItem,
ProductItemTransaction, ProductRequest, ProductRequestLineItem, ProductTransfer, Shipment,
ProductConsumed, ReturnOrder, SerializedProduct. Inventory associates with physical locations and
quantities; consumption updates inventory. Demo stock:

```
Noida Warehouse: PCB-492 ×7 · Motor-X21 ×4 · Compressor ×2 · Filter-100 ×31
Delhi Warehouse: PCB-492 ×0 · Motor-X21 ×9 · Filter-100 ×17
```

So `inventory.findPart("PCB-492")` → Noida 7, Delhi 0, technician needs it tomorrow. More
credible than pretending Eudoro's gift inventory is appliance inventory.

**What about Eudoro?** Don't repurpose it as appliance commerce ("why is an appliance-repair
company using a customized-gifts engine?"). Reuse its engineering DNA — order workflow, payment
webhooks, idempotency, transactional boundaries, RabbitMQ, event contracts, seller/ledger logic,
observability, server-side validation — into a tiny **Service Commerce**: Products, Quotes,
Orders, Payments, Refunds. Maybe only `GET /parts/:id`, `POST /quotes`, `POST /orders`,
`POST /payments`, `POST /refunds`. No storefront, no seller UI, no customer e-commerce app, no
product customization.

**Final enterprise-system split:**

| Domain | System of record |
|--------|------------------|
| Customer, Asset, Service Case, Work Order, Appointment, Technician, Territory, Skills | Salesforce |
| Parts inventory | Salesforce Field Service |
| Knowledge | LlamaIndex + pgvector |
| Decision state | LangGraph / Postgres |
| Repair quotes/orders | Small Service-Commerce |
| Payment | Razorpay |
| Communication | Vonage RCS |
| Reliability | RabbitMQ |
| Observability | Prometheus/Grafana |
| AI tools | MCP |

**Salesforce events make integration better.** Don't poll — use the **Pub/Sub API** (platform
events + Change Data Capture, available in DE): `Salesforce → Pub/Sub API → Integration service →
RabbitMQ → LangGraph`.

### The complete "wow" customer journey (13 stages)

1. **Appointment created** — Salesforce WO-10281, Daikin Inverter AC, today 10–12, technician
   Rahul, Noida. Customer gets a card: *🔧 AC Service Appointment · Today 10:00 AM–12:00 PM ·
   Technician Rahul Kumar* with `[ View Appointment ] [ Add to Calendar ] [ Change Slot ]
   [ Share Location ]`. Calendar + location sharing are native RCS.
2. **Failure happens** — simulate previous appointment +50 min delay → Salesforce event
   `SERVICE_APPOINTMENT_AT_RISK` → RabbitMQ `{"event":"appointment.at_risk","appointmentId":
   "SA-19281"}` → LangGraph wakes.
3. **AI investigates** — Load Appointment → Technician → Customer → Asset → Warranty → Inventory →
   Search Service Manual → Evaluate SLA → Generate recovery strategies. Output: Option A tech
   arrives 11:00–13:00; Option B tech X 10:30–12:30; Option C reschedule tomorrow 09:00–11:00.
   Deterministic validation removes illegal options.
4. **Beautiful RCS carousel** — "Your appointment needs a small adjustment. We found 3 options":
   TODAY 11:00–13:00 same tech · TODAY 10:30–12:30 tech Arjun · TOMORROW 09:00–11:00 earlier.
   Vonage supports 2–10 cards per carousel.
5. **Customer shares location** — taps *Share my location*; phone sends GPS → routing service →
   technician ETA → LangGraph → "We can still keep the 11–1 slot." RCS isn't just carrying text;
   the device participates in the workflow.
6. **Technician needs evidence** — "Before the technician arrives, please send a photo of the AC
   model label. [ Upload Photo ] [ Talk to Support ]". Customer sends photo → Image → OCR/vision →
   model extraction → product validation → Salesforce Asset → knowledge retrieval. Result:
   model Daikin XYZ-492, warranty active, likely part PCB-492.
7. **RAG** — LlamaIndex retrieves Daikin XYZ-492 Service Manual, Warranty Policy, PCB-492
   compatibility, Repair SOP. AI: likely failure control board, compatible part PCB-492, warranty
   covered, expected repair 45–60 min. Again: LLM recommends, rules validate.
8. **Inventory** — `inventory.find("PCB-492")` → Noida Depot 7, Technician Van 0, Delhi Depot 0.
   Decision: reserve 1 from Noida.
9. **Quote** — PCB-492 ₹4,500 + Labour ₹1,000 + GST ₹990 = ₹6,490. Card with
   `[ Approve & Pay ] [ Ask a Question ] [ Decline ]`.
10. **Razorpay** — taps *Approve & Pay*; RCS opens a secure Razorpay URL/webview. **RCS is not a
    native payment gateway** — the button launches your secure payment experience via Open
    URL/webview (full/half/tall modes). Razorpay → Test checkout → success/failure → webhook →
    RabbitMQ → order/payment state. Test mode = simulated.
11. **Confirmation** — *✅ Repair approved. Payment received. Part reserved PCB-492. Technician
    Rahul Kumar. Arrival 11:00–12:00.* `[ Track Technician ] [ Add to Calendar ]
    [ Call Technician ]`. Now we have calendar, location, dial, URL, cards, carousel, replies,
    media, PDF — one coherent journey.
12. **Service report** — technician completes job; Salesforce WorkOrder = Completed; system
    generates Service Report.pdf. *✅ Service Completed. [ View Service Report ]. Warranty 90
    days. [ Contact Support ]*. India PDF-rich-card capability shines here.
13. **Deliberately break the system** (mandatory):
    - **A — RCS unavailable:** RCS → rejected → SMS fallback (Vonage failover + workflow
      IDs/status callbacks).
    - **B — duplicate webhook:** message UUID → idempotency table → already processed → ignore.
    - **C — Salesforce unavailable:** RabbitMQ → retry → backoff → DLQ.
    - **D — AI uncertain:** confidence/policy → HUMAN REVIEW.
    - **E — inventory changed between recommend and execute:** reserve → atomic check →
      unavailable → graph resumes → recalculate options.
    - **F — user replies against a stale workflow version:** conversation state → current version
      → reject stale action → send current options. Demonstrates distributed state management.

### Why your resume is unusually relevant

- **Primble:** OCR, LLM extraction, deterministic-first processing, evidence gates, human
  remediation, async queues.
- **Reconciliation system:** Salesforce, SAP, e-commerce, idempotent UPSERT, OAuth, retries,
  cross-system acknowledgement.
- **ECOU:** AI entity extraction, catalog grounding, deterministic transformations, human
  confirmation, multi-channel messaging.
- **Eudoro:** payments, idempotency, RabbitMQ, DLQ, transactions, ledger, observability.
- **Humanitarian system:** state machines, authorization, auditing, document security, scope
  control.

### Expected effort

| Scope | Team | Effort |
|-------|------|--------|
| Basic RCS + Salesforce proof | You + SF dev | 4–6 working days |
| First end-to-end happy path | You + SF dev | 7–10 days |
| Full architecture + AI/RAG/MCP | 2 engineers | 2–3 weeks |
| Robust POC with failure demos | 2 engineers | 3–4 weeks |
| Polished Vonage showcase | 2–3 engineers | 4–5 weeks |
| Solo | You | ~5–7 weeks |

Rough split: Vonage/RCS onboarding 5–15% · Salesforce Field Service 15–20% · MCP 10% · LangGraph
15% · RAG/LlamaIndex 10% · Commerce/payment 10% · RabbitMQ/reliability 10% · RCS UX 10% ·
Demo/observability 5%. **The biggest uncertainty isn't coding — it's platform access/onboarding
and Salesforce Field Service setup.**

### The biggest hidden friction you should know now

1. **Vonage RCS access** — requires a managed account + Developer Mode activation via your
   account manager. Resolve first.
2. **RCS India is Android-first** in Vonage coverage (no iOS RBM). Official target = Android +
   Google Messages + India.
3. **Generic DE vs Field Service DE** — use the Field Service-enabled DE with the managed package
   and sample data; don't configure a random DE.
4. **Agent configuration** — use case, hosting region, billing category, country, brand,
   application, verification, launch. Some selections (use case, billing category) **cannot be
   changed later.**
5. **India doesn't support Multi-use RCS agents** — so the agent is **Transactional** (perfect
   for this POC).
6. **RCS isn't visually identical everywhere** — rendering/capabilities vary; test target
   devices.
7. **Payment isn't inside RCS** — it's RCS → Open URL/Webview → Razorpay. Show honestly.
8. **Public webhook** — Vonage must reach your service: localhost → Cloudflare Quick Tunnel →
   `https://xxxxx.trycloudflare.com` → Vonage.
9. **AI can be the slowest component** — avoid RCS → LLM → LLM → LLM → RCS. Bound to one decision
   call, one retrieval, one response generation; everything else deterministic.
10. **Don't put real customer info in the demo** — fake customers, addresses, assets, work
    orders, phone numbers, payment amounts. Avoids privacy/compliance issues entirely.

### How to handle AI uncertainty — three levels of authority

```
LEVEL 1 — DETERMINISTIC : Can this action legally/technically happen?
          permission · SLA · inventory · price · appointment · technician · state · idempotency
LEVEL 2 — AI            : What is probably happening? Which resolution is best?
          What info is missing? How should we explain this?
LEVEL 3 — HUMAN         : Should we allow a high-risk decision?
```

So: `AI suggests → Policy validates → Human if required → Execute`. Aligned with your existing
"blank-over-wrong", evidence-gated, human-override approach.

### What I would NOT include

Kubernetes · multiple cloud providers · full e-commerce storefront · full technician mobile app ·
real route optimization · full Salesforce Agentforce · multi-tenant SaaS · WhatsApp initially ·
voice initially · complex billing engine · real production payment. We prove RCS + AI + Salesforce
+ MCP + RAG + Commerce + Payment + reliability — not build a company.

### What I would add that you didn't ask for (essential)

**A. Decision Trace** — every AI decision records:

```json
{
  "caseId": "WO-10281",
  "decision": "RESCHEDULE",
  "reason": ["technician delayed", "customer SLA allows 2h window", "alternative technician unavailable"],
  "knowledgeSources": ["sla-policy-v4"],
  "toolsUsed": ["salesforce.getAppointment", "salesforce.getTechnician", "inventory.getAvailability"],
  "confidence": 0.91,
  "policyResult": "APPROVED"
}
```

So you can literally show "here's why the AI made this decision."

**B. AI Decision Dashboard** (Grafana) — AI decisions (auto-resolved / approval required / human
escalation / rejected by policy / failed); RCS (sent / delivered / read / rejected / fallback);
Workflow (latency / retries / DLQ / recovery time). Fed by real Vonage status callbacks
(submitted, delivered, read, rejected, undeliverable) — real telemetry, not a fake dashboard.

**A demo control panel** — a tiny internal React page:

```
┌─────────────────────────────────────────────┐
│ FIELD SERVICE AI CONTROL CENTER               │
│ WO-10281                                      │
│  ● Appointment Risk    ● AI Investigation     │
│  ● Customer Contacted  ● Customer Selected 11-1│
│  ● Part Reserved       ● Payment Approved      │
│  ● Technician Dispatched ● Service Completed   │
│ AI Decision: "Reschedule to 11-1"             │
│ Why: technician delayed · alt resource avail  │
│      · SLA preserved                          │
│ [Simulate Technician Delay]                   │
│ [Simulate Inventory Failure]                  │
│ [Simulate Salesforce Down]                    │
│ [Simulate RCS Rejection]                      │
└─────────────────────────────────────────────┘
```

Turns the demo into something the Vonage team can control live.

### Target architecture (restated)

```
RCS CUSTOMER ─TEXT/CARD/IMAGE/LOCATION→ VONAGE Messages API ─webhook/events→ Node Gateway
  → RabbitMQ → LangGraph (state + orchestration + interruptions + decision workflow)
       ├── Salesforce MCP → Field Service → Inventory
       ├── LlamaIndex RAG → Manuals/SOPs
       └── Commerce MCP → Quotes/Orders → Razorpay Test Payment
```

And every mutation: `AI suggestion → Policy validation → Permission validation → Idempotency
check → Transaction → Event → Audit`.

### The "Vonage wow" checklist

✓ Branded RCS agent ✓ Rich card ✓ Carousel ✓ Suggested reply ✓ Suggested action ✓ Webview
✓ Calendar ✓ Share location ✓ View location ✓ Dial support ✓ Customer photo ✓ Customer response
✓ PDF service report ✓ RCS delivery callback ✓ AI reasoning ✓ RAG ✓ Salesforce ✓ MCP ✓ Inventory
✓ Commerce ✓ Razorpay test payment ✓ Human approval ✓ RabbitMQ ✓ Idempotency ✓ Retry ✓ DLQ
✓ Reconciliation ✓ RCS capability check ✓ RCS → SMS fallback ✓ Observability ✓ Decision trace.

### One decision to make now

Do **not** use Eudoro as the appliance-commerce platform. Use Salesforce (Field Service +
Inventory) + a tiny Service-Commerce service (Parts/Quotes/Orders) + Razorpay (payment). Reuse
Eudoro's transaction patterns, idempotency, payment integration, event design and reliability
code — not its domain model. Then you can say: *"We used Salesforce as the field-service system
of record, our own service-commerce layer for parts/quotes, and Vonage as the customer
interaction channel."* Much more believable.

### The actual problem statement

> When a home-service appointment becomes at risk because of technician delays, inventory
> problems, asset complexity, or other operational exceptions, an AI recovery orchestrator
> gathers context from enterprise systems, reasons over service knowledge, validates possible
> actions against deterministic business policies, negotiates the best resolution with the
> customer through RCS, executes the resulting changes across Salesforce, inventory, commerce and
> payment systems, and remains resilient to duplicate events, failures, unavailable services and
> communication-channel limitations.

Not "AI chatbot using RCS." Not "Salesforce + MCP demo." Not "RCS rich-card demo." It is an
**AI-powered operational recovery system, with RCS as the customer's real-time control plane.**

### The next artifact

Before writing code, lock down a POC specification containing the exact domain model, event
catalog, Salesforce objects, MCP tools, LangGraph state machine, RAG documents, RCS
message-by-message conversation, failure matrix, APIs, repositories/services, and a 10–15 minute
Vonage demo script — so the project doesn't become an uncontrolled collection of technologies.
*(This is now split across [`srs.md`](srs.md), [`risks.md`](risks.md) and [`roles.md`](roles.md),
with architecture/diagrams/scaffold coming next.)*
