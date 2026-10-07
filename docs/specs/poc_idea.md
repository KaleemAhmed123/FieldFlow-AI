I want you to look at my resume
I want you to grasp what I know and what I am capable of building so we wanna work on some complex screnario not just basic case study maybe we can integrate multiple platforms like salesforce there is a salesforce dev in my team and I can do the commerce part and AI layer is must to have a decision layer we can utilize langgrapg, MCP, llamaindex, vectore rag all can be part of it and salesforce can be optional too or maybe we can change this to after brainstorming so come up with some problem of different domain or something so yeah go ahead and do research on what are the problem people are facing as of october 2026 and how we can integrate AI layer and then RCS message to finally interact and do the job

Do a comprehensive research on it take 1 hour or two hour I have unlimited token so scrape deep and come up with some problem worth solving and which would give a great impression on vonage team since they partnered with us so we could explore possibilities

Worked for 49s
My read of your capability
Your resume changes the type of POC we should build. You are already operating beyond CRUD/API integration: you have built distributed, event-driven systems with RabbitMQ, idempotency, reconciliation, dead-letter handling, Salesforce integration, AI extraction, RAG, human gates, payments, commerce, and observability. You have also explicitly built systems where the model is not trusted blindly and deterministic validation remains in control.

Your Eudoro work gives you a commerce/order/payments/event backbone, while Onlycouplez gives you practical RAG, evaluation, privacy boundaries and AI safety experience.

Therefore, I would absolutely not build an "RCS chatbot". The POC should demonstrate an AI decision-and-execution system where RCS is the customer control surface.

What I researched as of October 6, 2026
The strongest recurring problem across current research is fragmented operational systems + customers expecting immediate resolution + AI being deployed without enough execution/control. A recent 2026 analysis cited by Tata Communications says CX improvement is lagging because AI deployments remain siloed from data and operational systems; the recommendation is a contextual intelligence/orchestration layer that connects intelligence to actual business actions.

That maps almost perfectly onto your skillset.

The strongest current problem areas
Problem Current signal AI requirement RCS value Salesforce fit Your fit
Field-service failures / appointment recovery Nearly half of appointments don't go as scheduled; technicians spend >7 hrs/week on admin Very high Very high Excellent 10/10
Delivery exceptions / returns recovery Delivery/returns are major purchase drivers; AI adoption is high but exception handling remains weak High Very high Good 9.5/10
Insurance claims orchestration Claims remain fragmented; 22% use multiple channels for one query Very high Very high Excellent 9.5/10
Healthcare access / scheduling Timely appointments remain the biggest patient access problem; authorization/verification cause delays Very high High Excellent 8.8/10
Fraud/scam intervention Mobile is increasingly central to scams and real-time intervention Very high High Good 8/10
Travel disruption recovery Disruption requires multi-system coordination and immediate customer action High Excellent Moderate 8.5/10
The field-service problem has particularly strong evidence: Salesforce's 2026 research across 6,500 service professionals in 40 countries found nearly half of appointments don't go as scheduled, technicians lose more than seven hours per week to administrative work, and 81% believe AI agents could improve their efficiency.

E-commerce is also compelling: DHL's 2026 study covered 29,000 shoppers and 5,800 businesses across 29 countries; seven in ten shoppers said they would abandon a brand if the delivery/returns options weren't what they wanted, while nine in ten businesses said delivery and returns are important to online sales.
Bringg's 2026 last-mile research is particularly interesting for us: AI adoption is relatively high for routing and visibility but only 28% for exception handling, 26% for carrier management, and 25% for billing reconciliation—exactly the ugly operational workflows where your engineering background is strongest.

Insurance is another excellent problem: Deloitte's 2026 analysis of nearly 4,000 policyholders found many claims processes remain complex, fragmented and unclear; 22% of auto/home customers still use multiple channels to resolve one query, while only 36% of auto and 31% of homeowner customers receive updates through mobile apps. Deloitte explicitly points to AI + human judgment + better communications as the solution.

Healthcare has enormous pain too—Experian Health's 2026 survey found timely appointments remain the biggest patient access problem, while authorization and insurance verification continue to cause delays.
But I would not choose healthcare as our first POC because compliance, clinical safety and PHI create a lot of complexity that doesn't necessarily demonstrate Vonage better.

My recommendation: build this
AI Service Recovery Orchestrator
"When field service goes wrong, the system fixes it."
Don't make it specific to one company initially.

Make the platform generic:

Telecom
HVAC
Appliance repair
Internet installation
Home services
Industrial equipment
Automotive service
Medical equipment
Utilities
Then demonstrate it with one concrete scenario such as premium appliance / AC / telecom service.

The problem:

A customer has a service appointment. Something goes wrong somewhere in the operational chain. Instead of forcing the customer to call support, a network of AI + business systems detects the problem, determines the best resolution, asks the customer for the minimum required input through RCS, executes the resolution across Salesforce/commerce/inventory/dispatch/payment systems, and keeps everyone synchronized.

That is dramatically more interesting than:

Customer → RCS → AI → Answer
Our system becomes:

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

That is a real agentic operational system, not an AI demo.

Concrete scenario
Let's use an appliance/AC repair company for the demo because it gives us an extremely visual flow.

09:00
Salesforce has:

Customer:
Kaleem Ahmed

Asset:
Daikin AC

Work Order:
WO-18372

Appointment:
10:00–12:00

Technician:
Ravi

Required skill:
Daikin inverter diagnostics

Required part:
PCB-492
09:25
Salesforce receives an operational event:

Technician's previous job:
+55 min delay
At the same time:

Inventory:
PCB-492 unavailable
Now the traditional system might simply leave the appointment broken.

Our system sees:

Appointment risk +
Technician delay +
Missing part +
Customer SLA +
Technician skills +
Inventory +
Historical service data
and sends this context to the AI decision engine.

The AI doesn't just answer
LangGraph could execute:

START
│
▼
Load Case
│
▼
Load Customer Context
│
▼
Load Asset History
│
▼
Load Work Order
│
▼
Check Technician
│
▼
Check Inventory
│
▼
Retrieve Troubleshooting Knowledge
│
▼
Generate Resolution Options
│
▼
Policy / SLA Validation
│
├───────────────┐
▼ ▼
Low-risk High-risk
auto action human approval
│ │
└───────┬───────┘
▼
Execute
This is exactly where LangGraph is appropriate: it provides stateful orchestration, persistence, interruptions and human-in-the-loop control for long-running workflows.

The system might discover 4 possible resolutions
Option A
Send another technician
ETA 11:00
Cost +₹0

Option B
Reschedule
Tomorrow 10–12
Cost +₹0

Option C
Remote diagnosis first
Potentially avoid site visit

Option D
Replace PCB
Part available at nearby warehouse
ETA tomorrow
₹4,800
But the LLM doesn't get to say:

"Let's replace the PCB."

We use your existing engineering philosophy:

LLM
↓
Candidate decisions
↓
Deterministic policy engine
↓
SLA check
↓
Inventory check
↓
Customer entitlement
↓
Price limits
↓
Permission check
↓
Execute
That is much more impressive to an enterprise audience.

Then RCS becomes the actual customer interface
The customer receives something like:

┌─────────────────────────────────┐
│ 🔧 Service update │
│ │
│ Your technician is delayed │
│ by approximately 45 minutes. │
│ │
│ We found these options: │
│ │
│ ┌─────────────────────────────┐ │
│ │ Today │ │
│ │ 11:00 – 13:00 │ │
│ │ Same technician │ │
│ │ │ │
│ │ [ Choose ] │ │
│ └─────────────────────────────┘ │
│ │
│ ┌─────────────────────────────┐ │
│ │ Tomorrow │ │
│ │ 10:00 – 12:00 │ │
│ │ Earlier slot │ │
│ │ │ │
│ │ [ Choose ] │ │
│ └─────────────────────────────┘ │
│ │
│ [ Speak to support ] │
└─────────────────────────────────┘
RCS is excellent for this because it supports rich cards, carousels, suggested replies, and device actions.

Then make it much more complex
Customer chooses:

"11:00–13:00"

The system updates:

Salesforce ServiceAppointment
↓
Dispatch
↓
Technician
↓
Customer
Salesforce Field Service already models the exact concepts we need: Work Orders, Service Appointments, Assets, Service Resources, Skills, Territories, etc.

And Salesforce's Pub/Sub API is designed specifically for event-driven integration, allowing an external application to publish/subscribe to platform events and change-data-capture events. Salesforce even gives maintenance-service and product-order integration as examples.

That gives your Salesforce teammate a real engineering contribution, rather than "we connected Salesforce REST API".

Now introduce the commerce part
The technician arrives.

He discovers:

PCB is actually damaged.
The technician uploads:

photo of PCB
Customer gets:

Please upload a photo of the unit label.
RCS can receive inbound images, files and locations as well as replies/buttons.

Your AI pipeline:

Image
↓
Vision model
↓
Extract model number
↓
Validate
↓
RAG
↓
Compatible parts
↓
Inventory
↓
Pricing
↓
Warranty
↓
Decision
Suppose:

Warranty:
YES

Part:
Free

Inventory:
Available in Noida warehouse

Delivery:
Tomorrow
RCS:

┌───────────────────────────────┐
│ Replacement Part │
│ │
│ PCB-492 │
│ Covered under warranty │
│ ₹0 │
│ │
│ Available tomorrow │
│ │
│ [ Approve replacement ] │
│ [ Ask technician ] │
└───────────────────────────────┘
Customer taps:

Approve replacement

Now your commerce layer:

Reservation
↓
Inventory hold
↓
Purchase/work order line
↓
Salesforce
↓
Technician assignment
↓
Appointment update
This is where your Eudoro experience becomes directly useful.

Now add payment
For out-of-warranty work:

Repair:
₹4,800

Diagnostic:
₹500

Tax:
₹954

Total:
₹6,254
RCS:

Repair quote: ₹6,254

Includes:
✓ PCB
✓ Labour
✓ Installation

[ Review & Pay ]
[ Reject ]
[ Ask Question ]
Open URL suggested action launches your secure payment page; Vonage/RCS supports native URL, dialing, location and calendar actions.

Your existing Razorpay knowledge becomes useful here too.

Then send the final service report through RCS
This is actually particularly interesting for India.

Google currently supports PDFs in RCS rich cards specifically on Google Messages in India.

So:

Service completed

Your service report is ready.

[ View Report ]
with the PDF.

Now the Vonage team gets to see an India-specific capability that isn't just a theoretical feature.

And now the really interesting part
We intentionally break things.

Failure 1
Vonage returns:

RCS rejected
System:

RCS
↓
rejected
↓
SMS fallback
Vonage explicitly supports message failover such as RCS → SMS in the Messages API.

Failure 2
Salesforce is temporarily unavailable.

We don't lose the event.

Event
↓
RabbitMQ
↓
retry
↓
backoff
↓
DLQ
↓
reconciliation
That's already an area your resume demonstrates deeply.

Failure 3
LLM produces a questionable recommendation.

Policy layer:

confidence < threshold
↓
human approval
Failure 4
Customer sends:

"Actually don't repair it, just refund me."

The graph loads existing state and decides whether refund is permitted.

Failure 5
Customer sends the same reply twice.

Idempotency:

RCS message ID
↓
deduplication key
↓
already processed
↓
ignore
Failure 6
Customer's device does not support the desired RCS functionality.

Capability check:

Capability check
│
┌────┴────┐
▼ ▼
YES NO
│ │
RCS fallback
Vonage provides individual and bulk RCS capability checks.

Now we have something much bigger than RCS
The final system becomes:

                     ┌───────────────────┐
                     │ Salesforce        │
                     │ CRM / Field       │
                     │ Service           │
                     └─────────┬─────────┘
                               │
                         Pub/Sub Events
                               │
                               ▼
                     ┌───────────────────┐
                     │ Event Gateway     │
                     │ Node.js           │
                     └─────────┬─────────┘
                               │
                            RabbitMQ
                               │
                               ▼
                  ┌─────────────────────────┐
                  │ LangGraph Orchestrator  │
                  │                         │
                  │ Stateful Agent         │
                  │ Decision Engine        │
                  │ Human Interrupts       │
                  └───────────┬─────────────┘
                              │
          ┌───────────────────┼────────────────────┐
          ▼                   ▼                    ▼

Salesforce MCP Commerce MCP Knowledge MCP
│ │ │
▼ ▼ ▼
CRM/Field Inventory/ LlamaIndex
Service Payments RAG
│ │
└────────┬───────────┘
▼
Policy Engine
│
┌─────────┴─────────┐
▼ ▼
Execute Human
│ approval
└─────────┬─────────┘
▼
Vonage Messages API
│
▼
┌──────────────┐
│ RCS Customer │
└──────┬───────┘
│
replies / images /
location / actions
│
▼
Back to LangGraph
MCP is useful here because it standardizes the way AI systems access tools and data sources; think of your Salesforce, commerce, inventory and operational systems as controlled tools exposed to the agent rather than stuffing their APIs into every prompt.

Where LlamaIndex fits
I would not use LlamaIndex as the overall orchestrator.

Use it primarily for:

                         Knowledge
                            │
          ┌─────────────────┼──────────────────┐
          ▼                 ▼                  ▼
    service manuals     warranty rules     SOPs/policies
          │                 │                  │
          └─────────────────┼──────────────────┘
                            ▼
                       LlamaIndex
                            │
                       retrieval/RAG
                            │
                            ▼
                     LangGraph state

For example:

"Does PCB-492 work with model XYZ-438?"

That's a retrieval/grounding problem.

"Should we repair, replace, reschedule or escalate?"

That's an orchestration/decision problem.

Keep those separate.

Where MCP fits
Create tools such as:

salesforce.getCustomer()
salesforce.getAsset()
salesforce.getWorkOrder()
salesforce.updateAppointment()

inventory.checkAvailability()
inventory.reservePart()

commerce.getQuote()
commerce.createOrder()
commerce.createPaymentLink()

routing.getETA()
routing.findTechnician()

knowledge.searchManual()
knowledge.searchWarrantyPolicy()

vonage.sendRCS()
vonage.sendCarousel()
vonage.sendFallback()
Then LangGraph can reason over a controlled tool surface.

That is much cleaner than:

LLM
↓
huge prompt
↓
50 APIs
Why Salesforce is worth adding
I would absolutely include Salesforce, given that you already have a Salesforce developer on the team.

Not because "Salesforce looks impressive".

Because it gives us a credible enterprise source-of-truth:

Account
Contact
Asset
Case
Work Order
Service Appointment
Service Resource
Service Territory
Service Contract
Those are actual Field Service concepts in Salesforce's current model.

And Pub/Sub API provides a proper event-driven integration layer.

That means your demo shows:

CRM → Event Bus → AI → Operational systems → RCS → Human → back into CRM

rather than:

API → chatbot

Why RCS is genuinely necessary here
This is the key question the Vonage team will subconsciously ask:

"Why RCS?"

We need a strong answer.

Because the customer needs to perform actions at moments when opening an application or calling support creates friction.

RCS provides:

appointment choice +
rich cards +
carousel +
suggested replies +
location sharing +
photos/videos/files +
calendar actions +
URLs/payment +
native messaging
Vonage currently exposes outbound RCS text/media/cards/carousels and inbound text/media/location/reply/button events.

That gives us an interactive transactional interface, not just a notification channel.

And India actually has an interesting advantage
Vonage's current coverage page lists India for Android RCS, while its listed iOS RCS coverage does not currently include India.

More importantly, Google's current RCS documentation specifically supports PDF rich-card content in India on Google Messages.

So for our POC we should target:

Android

- Google Messages
- Indian test numbers
  rather than trying to make the first demo artificially universal.

One important constraint for our architecture
For India, Multi-use RCS agents are currently unavailable. Transactional agents are globally available, while promotional use has additional Indian restrictions.

That actually makes our recommended POC cleaner.

We classify the primary agent as:

TRANSACTIONAL
and keep the entire demo around:

existing service
existing appointment
existing customer
existing work order
service recovery
service completion
payment
documents
We don't need promotional messaging at all.

Google's current messageTrafficType model also distinguishes categories such as TRANSACTION and SERVICEREQUEST, which is useful for a system like ours.

Candidate #2: AI Delivery Exception & Returns Rescue
This is my second choice and possibly the best alternative because of your Eudoro experience.

Order shipped
↓
Carrier delay
↓
AI detects SLA risk
↓
Customer receives RCS
↓
"Your order will miss its promised date."
↓
[ Deliver tomorrow ]
[ Pickup nearby ]
[ Change address ]
[ Cancel ]
Then:

AI
↓
Order DB
↓
Carrier APIs
↓
Inventory
↓
Refund engine
↓
RCS
Could become far more sophisticated:

package damaged
↓
customer sends photo
↓
vision model
↓
fraud/risk model
↓
order history
↓
carrier telemetry
↓
policy/RAG
↓
refund / replacement / investigation
This is especially timely because 2026 research shows delivery/returns remain major customer pain points while AI adoption is disproportionately concentrated in route optimization rather than exception handling.

Score: 9.5/10.

Candidate #3: AI Claims Resolution Concierge
This one fits your resume frighteningly well.

Claim detected
↓
RCS
↓
"Upload damage photos"
↓
Customer sends images
↓
Vision/OCR
↓
Policy RAG
↓
Claim extraction
↓
Fraud/risk signals
↓
Missing evidence detection
↓
AI determines next action
↓
Salesforce case
↓
Human adjuster when needed
↓
RCS updates
Your Primble experience already includes OCR → extraction → deterministic-first processing → evidence gating → remediation.

And current insurance research strongly validates fragmented claims communication as a real problem.

Score: 9.5/10.

The downside: it overlaps with things you already know, so it teaches the Vonage team less about your ability to enter a new domain.

Candidate #4: AI Patient Access Orchestrator
Patient
↓
RCS
↓
"I need an appointment"
↓
AI
↓
Insurance verification
↓
Provider availability
↓
Authorization status
↓
RAG
↓
Appointment selection
↓
Calendar
↓
Payment estimate
↓
RCS
Healthcare has genuine 2026 problems around appointment access, authorization, insurance verification and administrative burden.

But I would keep it as a future option, not the first POC. It puts us into safety, privacy and clinical-risk territory unnecessarily.

Candidate #5: AI Fraud Intervention
Interesting architecture:

transaction
↓
risk engine
↓
AI evaluates context
↓
RCS
↓
"Did you authorize this?"
↓
[ Yes ]
[ No ]
[ Freeze ]
↓
banking workflow
Very strong technically, but financial fraud decisions are high-stakes and would put much more regulatory/security pressure on the demo.

I'd rank it below the others.

What I think will impress Vonage the most
Not the number of technologies.

Not saying:

"We used LangGraph + MCP + RAG + Salesforce + n8n + RCS."

That can easily become technology soup.

The impressive thing is this:

"We selected a real operational problem, built an AI agent that reasons over enterprise context, constrained its authority using deterministic policies, exposed business systems as tools, allowed the customer to complete the workflow through RCS, and designed the whole thing to survive retries, duplicate events, unavailable systems, RCS capability differences and human escalation."

That is the story.

The POC should have 7 layers

1. EXPERIENCE
   RCS

2. COMMUNICATION
   Vonage Messages API

3. ORCHESTRATION
   LangGraph

4. KNOWLEDGE
   LlamaIndex + vector RAG

5. TOOLS
   MCP

6. ENTERPRISE SYSTEMS
   Salesforce + Commerce + Inventory + Payment

7. RELIABILITY
   RabbitMQ + idempotency + retries + DLQ +
   reconciliation + observability
   And your existing experience covers almost every layer already.

One architectural decision I strongly recommend
Do not make n8n the core transaction engine.

Use n8n around the edges:

CRM notification
scheduled jobs
email
Slack
admin workflows
prototype integrations
non-critical automation
Keep the core path:

RCS
↓
API
↓
RabbitMQ
↓
LangGraph
↓
deterministic services
↓
transaction
because your POC is supposed to prove that you can build a production-grade system, not merely wire together SaaS nodes.

What makes this especially good for Vonage
We can deliberately demonstrate almost every important RCS capability in a single coherent story:

TEXT
"Your appointment needs attention."

      ↓

RICH CARD
Service information

      ↓

CAROUSEL
Available appointment slots

      ↓

SUGGESTED REPLY
"Tomorrow 10 AM"

      ↓

LOCATION ACTION
"Share my location"

      ↓

IMAGE
Customer sends equipment photo

      ↓

URL ACTION
Payment / secure detail page

      ↓

CALENDAR ACTION
Add confirmed appointment

      ↓

PDF
Service report / quote

      ↓

STATUS CALLBACK
Delivered / read

      ↓

FAILOVER
RCS → SMS
These are all real RCS primitives documented by Vonage/Google.

That turns the POC into almost a capability showcase for Vonage itself.

And we can demonstrate the hard engineering
The demo should intentionally show:

✓ duplicate webhook
✓ duplicate customer reply
✓ delayed Salesforce event
✓ failed inventory API
✓ model uncertainty
✓ human approval
✓ RCS capability failure
✓ RCS rejection
✓ SMS fallback
✓ RabbitMQ retry
✓ dead-letter queue
✓ reconciliation
✓ distributed correlation ID
✓ audit trail
✓ AI decision trace
✓ cost/latency metrics
This plays directly into the things already visible in your resume: idempotency, reconciliation, DLQs, circuit breakers, state machines, human oversight and production observability.

One more thing: RCS itself is still evolving
This isn't a stagnant protocol we're designing around. Google's RCS for Business documentation had active 2026 changes including persistent suggestions and India-specific promotional limits, and its rich-card documentation was updated August 25, 2026.

Vonage currently lists India Android coverage, RCS capability checks, a default RCS channel rate limit of 75 requests/second per API key, and RCS → SMS failover.

So this is a good moment to build against it rather than treating it as an obsolete SMS replacement.

My ranking
RCS AI Salesforce Commerce Wow
────────────────────────────────────────────────────────────
Field Service ★★★★★ ★★★★★ ★★★★★ ★★★★★ 10/10
Delivery Recovery ★★★★★ ★★★★★ ★★★★☆ ★★★★★ 9.5/10
Claims Concierge ★★★★★ ★★★★★ ★★★★★ ★★★★☆ 9.5/10
Healthcare Access ★★★★☆ ★★★★★ ★★★★★ ★★★☆☆ 8.8/10
Travel Recovery ★★★★★ ★★★★☆ ★★★☆☆ ★★★☆☆ 8.5/10
Fraud Intervention ★★★★☆ ★★★★★ ★★★★☆ ★★☆☆☆ 8/10
The one I would actually build
AI Service Recovery Orchestrator — a field-service system that autonomously detects broken appointments, reasons across CRM + asset + technician + inventory + knowledge + SLA data, negotiates the resolution with the customer through RCS, executes the resulting changes across Salesforce/commerce/operations, and maintains consistency through an event-driven architecture.

The killer demo moment is not "look, RCS sends a rich card."

It is:

Technician problem
↓
AI detects operational failure
↓
AI determines 3 valid resolutions
↓
RCS negotiates with customer
↓
Customer sends image/location
↓
AI retrieves domain knowledge
↓
Inventory + Salesforce + commerce consulted
↓
Customer approves
↓
Real transaction executed
↓
Salesforce updated
↓
Technician updated
↓
Payment / appointment / inventory synchronized
↓
PDF/report delivered
↓
Everything observable + auditable
That is the level of POC I would take to Vonage. It makes RCS the missing interaction layer in an otherwise complete enterprise decision-and-execution system, while giving you, the Salesforce developer, and the Vonage team meaningful technical territory to explore.

This might also interest you.

Ad
I wanna solve this Field-service failures / appointment recovery (Home Service and Appliance repair as one).

First:
Constraints since it is just gonna be a POC so everything needs to be free for testing and mention other friction if I can not see it

Second:

1. EXPERIENCE
   RCS

2. COMMUNICATION
   Vonage Messages API

3. ORCHESTRATION
   LangGraph

4. KNOWLEDGE
   LlamaIndex + vector RAG

5. TOOLS
   MCP

6. ENTERPRISE SYSTEMS
   Salesforce + Commerce + Inventory + Payment

7. RELIABILITY
   RabbitMQ + idempotency + retries + DLQ +
   reconciliation + observability

These things are must in flow and should justify why they are there not just for the sake of being there especially RCS and also most of the communication needs to be done with RCS.

Third:
Expected time and effort and the complexity overall

forth:
about platforms does salesforce dev org has all what you mentioned the field service things and will we have to create a ecommerce platform ? I already have Eudoro platform so can I just integrate it (can we portray it as inventory or tools though it is a platform for customized gifts or should we build new or can we skip maybe we can use salesforce as inventory) and another things does salesforce support MCP and overall how AI is helpful there because that can be a friction so..

fifth:
Make sure to use cool actions like we have almost all location sharing, payment (Razorpay), calendar, beautiful cards and so on, all possible amazing actions by RCS we wanna give almost app like experience. Basically an attempt to impress Vonage partners

So yeah answer this stuff and there is more to it you should know where we are going so add stuff that I should have asked too
…

Worked for 56s
Yes. I would lock the POC around Field-Service Failure & Appointment Recovery for Home Services / Appliance Repair, but I would make one important change to the architecture: Salesforce should own the field-service domain and inventory where possible; we should build only a thin repair-commerce/payment layer, not another ecommerce platform. Your Eudoro experience should be reused as engineering patterns and possibly selected services, not presented as an appliance-commerce system.

1. First: can we actually build this for ₹0?
   Almost entirely; RCS is the only unavoidable commercial dependency.

Component POC cost Recommendation
Salesforce Developer Edition ₹0 Use a Field Service-enabled Developer Edition
Salesforce Hosted MCP ₹0 in Developer Edition Use it; this is extremely valuable for the POC
Salesforce Field Service ₹0 for the special Developer Edition Use the special Field Service DE, not blindly any generic DE
Vonage RCS Potentially ₹0 for initial POC credit, but not inherently free Your company/Vonage partnership is the critical dependency
Vonage Messages API Free credit available Vonage currently advertises free credit/no card, but RCS still requires managed-account enablement
LangGraph ₹0 Local/open-source
LlamaIndex ₹0 Local/open-source
MCP ₹0 Open protocol + local/hosted servers
LLM ₹0 possible Local Ollama model for guaranteed zero API spend
Vector DB ₹0 PostgreSQL + pgvector locally
RabbitMQ ₹0 Docker locally; RabbitMQ is open source
Prometheus ₹0 Docker
Grafana ₹0 Docker
Loki ₹0 Optional
Razorpay ₹0 Test Mode; simulated transactions, no actual money
Public webhook ₹0 Cloudflare Quick Tunnel for development
Eudoro ₹0 additional Don't make it the domain model; reuse architecture/patterns
Hosting ₹0 Run the entire POC locally
Salesforce explicitly provides free Developer Edition environments, and current Salesforce documentation says Field Service core, its managed package, and mobile app are available in Developer Edition. There is also a special Field Service Developer Edition intended for exactly this kind of development/testing.
Salesforce's April 2026 update also brought Hosted MCP Servers into Developer Edition at no cost.

Vonage is the one caveat: its current RCS docs say RCS is available only to managed accounts and that you need your account manager to activate Developer Mode; meanwhile its pricing page currently advertises "Try it free" with free credit and no card.
Since your company is already partnering/discussing partnership with Vonage, this should be the first dependency we clear.

For all the local infrastructure, RabbitMQ is explicitly free/open source and has an official Docker image; Cloudflare Quick Tunnels provide temporary public URLs without a domain or account, which is perfect for Vonage webhooks during development.
Razorpay Test Mode is also simulated and does not deduct real money.

2. The architecture I would actually build
   CUSTOMER
   │
   │ RCS
   ▼
   ┌─────────────────┐
   │ VONAGE │
   │ Messages API │
   └────────┬────────┘
   │
   inbound/status
   webhooks
   │
   ▼
   ┌────────────────────┐
   │ API / Webhook │
   │ Gateway │
   └─────────┬──────────┘
   │
   RabbitMQ
   │
   ▼
   ┌──────────────────────┐
   │ LangGraph │
   │ Conversation / │
   │ Decision Orchestrator│
   └──────────┬───────────┘
   │
   ┌───────────────┼────────────────┐
   │ │ │
   ▼ ▼ ▼
   MCP Servers LlamaIndex Policy Engine
   │ + RAG │
   ┌──────┼───────┐ │ deterministic rules
   │ │ │ │ │
   ▼ ▼ ▼ ▼ │
   Salesforce Inventory Commerce risk/SLA/
   MCP MCP MCP permissions
   │
   ├── Customer
   ├── Asset
   ├── Case
   ├── Work Order
   ├── Service Appointment
   ├── Technician
   ├── Territory
   ├── Skills
   └── Inventory
   │
   ▼
   Repair Commerce
   │
   Razorpay
   Test Mode
   And beneath everything:

RabbitMQ
├── retry
├── DLQ
├── idempotency
├── events
└── asynchronous execution

PostgreSQL
├── conversation state
├── workflow state
├── idempotency keys
├── audit trail
└── AI decisions

Prometheus/Grafana
├── latency
├── RCS delivery
├── AI latency
├── workflow failures
├── queue depth
└── recovery success 3. Why every technology actually belongs
RCS — the customer interaction layer
This must be the primary interface, not an ornament.

The customer should perform most meaningful actions through RCS:

appointment selection
appointment confirmation
rescheduling
technician ETA
location sharing
photo upload
part approval
quote approval
payment initiation
calendar creation
service report
human escalation
RCS supports rich cards, carousels, suggested replies, open URL/webview, dial, view location, share location and calendar actions.
Rich cards can also contain PDF files, and PDF rich cards are currently supported in India on Google Messages, which gives us a particularly good India-specific demo opportunity.

So instead of:

RCS → "Your appointment changed."
we demonstrate:

RCS
↓
"Your appointment needs attention."
↓
beautiful cards
↓
customer selects new slot
↓
customer shares location
↓
customer uploads evidence
↓
customer approves quote
↓
customer opens payment
↓
customer adds appointment to calendar
↓
customer receives PDF report
That is why RCS is justified.

4. LangGraph — why we need it
   The problem isn't:

"Ask an LLM what to say."

The actual problem is:

"Maintain a long-running operational case while multiple systems produce new information, decisions require state, and some actions require human/customer approval."

Example:

WORK_ORDER_DELAYED

      ↓

load state

      ↓

customer context

      ↓

appointment context

      ↓

technician context

      ↓

inventory

      ↓

SLA

      ↓

knowledge/RAG

      ↓

generate recovery options

      ↓

policy validation

      ├── safe → execute
      │
      └── uncertain → human approval

      ↓

RCS

      ↓

customer selects

      ↓

resume graph

      ↓

execute

      ↓

verify

      ↓

close
LangGraph's interrupt/persistence mechanism is specifically intended for long-running workflows and human-in-the-loop execution: graph state can be checkpointed, paused, and resumed later.

This is much stronger justification than "we wanted to use LangGraph."

5. LlamaIndex + vector RAG — what problem does it solve?
   We need domain knowledge, not just database data.

Salesforce might say:

Asset = Daikin AC
Model = XYZ-123
Warranty = Active
But it doesn't necessarily contain:

Service manual
Fault codes
Repair procedures
Warranty policy
Technician SOP
Safety instructions
Part compatibility
Escalation rules
So:

Customer/asset data +
Enterprise records +
Knowledge base
↓
AI decision context
LlamaIndex becomes the knowledge retrieval layer:

PDF manuals
Warranty documents
SOPs
Policy docs
Product catalogs
Troubleshooting guides
↓
chunk
↓
embed
↓
pgvector
↓
retrieval
↓
LangGraph
This gives us a clean separation:

MCP = live operational data/tools

RAG = domain knowledge

LangGraph = orchestration

Policy engine = authority
That separation is exactly what I want.

6. MCP — this is where your POC can become much more interesting
   And yes, Salesforce now supports MCP directly in Developer Edition.

Salesforce's 2026 Developer Edition includes Hosted MCP Servers at no cost. Hosted MCP can expose Salesforce data and logic to MCP-compatible clients while respecting Salesforce security and permissions.

Salesforce currently provides hosted MCP endpoints including:

platform/sobject-reads
platform/sobject-all
platform/salesforce-api-context
for Developer Edition and other production orgs.

And Salesforce has gone further: its Headless 360 MCP Server can provide access to Salesforce operations through a small stable tool surface; custom Apex can also be exposed as hosted MCP tools.

This gives us a very clean architecture:

                    LANGGRAPH
                       │
                 MCP CLIENT
                       │
        ┌──────────────┼───────────────┐
        ▼              ▼               ▼

Salesforce MCP Inventory MCP Commerce MCP
│ │ │
▼ ▼ ▼
Salesforce Inventory DB Repair Commerce
Important:
Don't give the LLM unrestricted Salesforce API access.

Instead:

READ TOOLS

get_customer
get_asset
get_work_order
get_appointment
get_technician
get_inventory

CONTROLLED ACTION TOOLS

propose_reschedule
confirm_reschedule
reserve_part
create_service_quote
create_payment_request
close_work_order
The dangerous operations should be deterministic functions with validation.

7. AI is NOT the scheduler
   This is one of the most important architectural decisions.

Don't do:

LLM:
"Move appointment to 3PM."
Instead:

AI
↓
"These are the three viable recovery strategies."
↓
Policy Engine
↓
check:

- technician availability
- territory
- skill
- SLA
- customer entitlement
- travel time
- working hours
- inventory
- price authority
  ↓
  valid options
  ↓
  customer
  Salesforce Field Service already models work orders, service appointments, service resources, skills, territories and scheduling concepts.

So AI should reason about the problem while Salesforce/deterministic code remains the authority for whether a proposed action is valid.

That is far safer and technically more defensible.

8. Salesforce: yes, use it heavily
   The Field Service model is almost suspiciously perfect for this POC.

Salesforce has:

Account
Contact
Asset
Case
WorkOrder
WorkOrderLineItem
ServiceAppointment
ServiceResource
ServiceResourceSkill
ServiceTerritory
Skill
SkillRequirement
ServiceContract
WarrantyTerm
ServiceReport
and many additional inventory/scheduling entities.

That means we don't need to invent:

Technician table
Appointment table
Asset table
WorkOrder table
Salesforce already has the domain.

9. Salesforce can also be our Inventory system
   This is an even better discovery.

Salesforce Field Service has a real inventory model:

Product
ProductItem
ProductItemTransaction
ProductRequest
ProductRequestLineItem
ProductTransfer
Shipment
ProductConsumed
ReturnOrder
SerializedProduct
Inventory can be associated with physical locations and product quantities, and product consumption can update inventory.

So I would not build another inventory system unless Field Service access becomes a blocker.

Our demo can have:

Noida Warehouse
│
├── PCB-492 7
├── Motor-X21 4
├── Compressor 2
└── Filter-100 31

Delhi Warehouse
│
├── PCB-492 0
├── Motor-X21 9
└── Filter-100 17
Then AI can ask:

inventory.findPart()

→ PCB-492
→ Noida: 7
→ Delhi: 0
→ technician needs it tomorrow
That is much more credible than pretending Eudoro's gift inventory is appliance inventory.

10. What about Eudoro?
    Don't directly repurpose it as appliance commerce.
    That would create unnecessary conceptual friction:

"Why is an appliance-repair company using a customized-gifts commerce engine?"

Instead:

Reuse Eudoro's engineering DNA.
Your resume gives us:

order workflow
payment webhooks
idempotency
transactional boundaries
RabbitMQ
event contracts
seller/ledger logic
observability
server-side validation.
We can extract the useful patterns into a tiny:

Service Commerce
Products
Quotes
Orders
Payments
Refunds
Maybe only:

GET /parts/:id
POST /quotes
POST /orders
POST /payments
POST /refunds
That's enough.

No storefront.

No seller UI.

No customer ecommerce app.

No product customization.

No unnecessary complexity.

11. The final enterprise-system split
    This is what I recommend:

Domain System of record
Customer Salesforce
Asset Salesforce
Service Case Salesforce
Work Order Salesforce
Appointment Salesforce
Technician Salesforce
Territory Salesforce
Skills Salesforce
Parts inventory Salesforce Field Service
Knowledge LlamaIndex + pgvector
Decision state LangGraph/Postgres
Repair quotes/orders Small Service Commerce
Payment Razorpay
Communication Vonage RCS
Reliability RabbitMQ
Observability Prometheus/Grafana
AI tools MCP
That's a very clean architecture.

12. Salesforce events make the integration much better
    Don't have our backend constantly poll Salesforce.

Use Salesforce's event infrastructure.

Salesforce Pub/Sub API supports publishing/subscribing to platform events and Change Data Capture and is available in Developer Edition. Salesforce explicitly describes maintenance-service and product-order integrations as examples of event-driven use cases.

So:

Salesforce
│
│ WorkOrder / Appointment event
▼
Salesforce Pub/Sub API
│
▼
Integration service
│
▼
RabbitMQ
│
▼
LangGraph
Now this feels like an actual enterprise architecture.

13. The complete "wow" customer journey
    This is the flow I would build for the demo.

Stage 1 — Appointment created
Salesforce:

Work Order:
WO-10281

Asset:
Daikin Inverter AC

Appointment:
Today 10–12

Technician:
Rahul

Location:
Noida
Customer gets:

🔧 AC Service Appointment

Today
10:00 AM – 12:00 PM

Technician:
Rahul Kumar

[ View Appointment ]
[ Add to Calendar ]
[ Change Slot ]
[ Share Location ]
Calendar action and location sharing are native RCS capabilities.

14. Stage 2 — Failure happens
    Simulate:

Previous appointment:
+50 minutes delay
Salesforce event:

SERVICE_APPOINTMENT_AT_RISK
RabbitMQ receives:

{
"event": "appointment.at_risk",
"appointmentId": "SA-19281"
}

LangGraph wakes up.

15. Stage 3 — AI investigates
    Graph:

Load Appointment
↓
Load Technician
↓
Load Customer
↓
Load Asset
↓
Load Warranty
↓
Load Inventory
↓
Search Service Manual
↓
Evaluate SLA
↓
Generate recovery strategies
Output:

Option A
Technician arrives 11:00–13:00

Option B
Technician X can arrive 10:30–12:30

Option C
Reschedule tomorrow 09:00–11:00
Deterministic validation removes illegal options.

16. Stage 4 — beautiful RCS carousel
    Your appointment needs a small adjustment.

We found 3 options:

← ┌─────────────────────┐
│ TODAY │
│ 11:00 – 13:00 │
│ Same technician │
│ │
│ [ Select ] │
└─────────────────────┘

┌─────────────────────┐
│ TODAY │
│ 10:30 – 12:30 │
│ Technician: Arjun │
│ │
│ [ Select ] │
└─────────────────────┘

┌─────────────────────┐
│ TOMORROW │
│ 09:00 – 11:00 │
│ Earlier slot │
│ │
│ [ Select ] │
└─────────────────────┘ →
Vonage supports 2–10 cards per carousel.

17. Stage 5 — customer shares location
    Customer taps:

Share my location

Now the user's phone sends location back to the agent.

Your backend:

Customer GPS
↓
Routing service
↓
Technician ETA
↓
LangGraph
Now the system can say:

"We can still keep the 11–1 slot."
This is an extremely good demonstration because RCS isn't merely carrying text; the customer's device is participating in the workflow.

18. Stage 6 — technician needs evidence
    Customer receives:

Before the technician arrives,
please send a photo of the AC model label.

[ Upload Photo ]
[ Talk to Support ]
Customer sends photo.

Your AI pipeline:

Image
↓
OCR / vision
↓
Model extraction
↓
Product validation
↓
Salesforce Asset
↓
Knowledge retrieval
Then:

Model:
Daikin XYZ-492

Warranty:
Active

Likely part:
PCB-492 19. Stage 7 — RAG
LlamaIndex retrieves:

Daikin XYZ-492 Service Manual

- Warranty Policy
- PCB-492 Compatibility
- Repair SOP
  AI produces:

Likely failure:
Control board

Compatible part:
PCB-492

Warranty:
Covered

Expected repair:
45–60 min
Again:

LLM recommends. Rules validate.

20. Stage 8 — inventory
    MCP:

inventory.find("PCB-492")
Salesforce:

Noida Depot:
7 units

Technician Van:
0 units

Delhi Depot:
0 units
Decision:

Reserve 1 from Noida Depot.
Salesforce inventory objects can model exactly this sort of stock by location and product movement.

21. Stage 9 — quote
    Commerce service:

PCB-492 ₹4,500
Labour ₹1,000
GST ₹990
─────────────────────
Total ₹6,490
RCS:

┌─────────────────────────────┐
│ 🔧 Repair Quote │
│ │
│ PCB replacement │
│ │
│ Part ₹4,500 │
│ Labour ₹1,000 │
│ GST ₹990 │
│ │
│ TOTAL ₹6,490 │
│ │
│ [ Approve & Pay ] │
│ [ Ask a Question ] │
│ [ Decline ] │
└─────────────────────────────┘ 22. Stage 10 — Razorpay
Customer taps:

Approve & Pay

RCS opens a secure Razorpay URL/webview.

Important technical nuance:

RCS itself does not become a native payment gateway.

The "Pay" button launches your secure payment experience using RCS's Open URL/Webview capability. Google documents Open URL and webview actions, including full/half/tall display modes.

Razorpay remains:

Razorpay
↓
Test checkout
↓
Payment success/failure
↓
Webhook
↓
RabbitMQ
↓
Order/payment state
Test mode uses simulated payments and doesn't deduct real money.

23. Stage 11 — confirmation
    RCS:

✅ Repair approved

Payment received.

Part reserved:
PCB-492

Technician:
Rahul Kumar

Arrival:
11:00–12:00

[ Track Technician ]
[ Add to Calendar ]
[ Call Technician ]
Now we have:

calendar
location
dial
URL
cards
carousel
replies
media
PDF
all in one coherent journey.

24. Stage 12 — service report
    Technician completes job.

Salesforce:

WorkOrder = Completed
System generates:

Service Report.pdf
Customer receives:

✅ Service Completed

Your AC repair is complete.

Service report:
[ View Service Report ]

Warranty:
90 days

[ Contact Support ]
In India, the PDF-rich-card capability on Google Messages is particularly useful here.

25. Stage 13 — deliberately break the system
    This is mandatory for your POC.

A Vonage team will care much more about this than another pretty card.

Failure A — RCS unavailable
RCS
↓
rejected
↓
SMS fallback
Vonage directly supports channel failover such as RCS → SMS and provides workflow IDs/status callbacks for the chain.

Failure B — duplicate webhook
message UUID
↓
idempotency table
↓
already processed
↓
ignore
Failure C — Salesforce unavailable
RabbitMQ
↓
retry
↓
backoff
↓
DLQ
Failure D — AI uncertain
confidence / policy
↓
HUMAN REVIEW
Failure E — inventory changed between recommendation and execution
reserve
↓
atomic check
↓
inventory unavailable
↓
graph resumes
↓
recalculate options
Failure F — user replies after the original workflow changed
Conversation State
↓
Current version
↓
reject stale action
↓
send current options
That last one is particularly good because it demonstrates distributed state management, not just AI.

26. Your existing resume is unusually relevant here
    Your Primble work already has:

OCR
LLM extraction
deterministic-first processing
evidence gates
human remediation
async queues
Your reconciliation system already has:

Salesforce
SAP
ecommerce
idempotent UPSERT
OAuth
retries
cross-system acknowledgement
Your ECOU work already has:

AI entity extraction
catalog grounding
deterministic transformations
human confirmation
multi-channel messaging
Eudoro gives you:

payments
idempotency
RabbitMQ
DLQ
transactions
ledger
observability
And your humanitarian system gives you:

state machines
authorization
auditing
document security
scope control
That is exactly the background required for this POC.

27. Expected effort
    I'd estimate:

Scope Team Effort
Basic RCS + Salesforce proof You + Salesforce dev 4–6 working days
First end-to-end happy path You + Salesforce dev 7–10 days
Full architecture + AI/RAG/MCP 2 engineers 2–3 weeks
Robust POC with failure demos 2 engineers 3–4 weeks
Polished Vonage showcase 2–3 engineers 4–5 weeks
Solo You ~5–7 weeks
Roughly:

Vonage/RCS onboarding 5–15%
Salesforce Field Service 15–20%
MCP integration 10%
LangGraph 15%
RAG/LlamaIndex 10%
Commerce/payment 10%
RabbitMQ/reliability 10%
RCS UX 10%
Demo/observability 5%
The biggest uncertainty isn't coding.

It's platform access/onboarding and Salesforce Field Service setup.

28. The biggest hidden friction you should know now
1. Vonage RCS access
   Current Vonage documentation says RCS requires a managed account and Developer Mode activation through your account manager.

This is the first thing I'd resolve with Vonage.

2. RCS India is Android-first in Vonage's current coverage
   Vonage currently lists India for Android RCS but not iOS RCS through RBM.

So:

Our official demo target = Android + Google Messages + India.

3. Generic Salesforce DE vs Field Service DE
   Don't waste time configuring a random Developer Edition and assuming every Field Service feature is there.

Use the Field Service-enabled Developer Edition; Salesforce explicitly provides a free special DE with the Field Service managed package and sample data.

4. Agent configuration becomes annoying
   RCS agent:

Use case
Hosting region
Billing category
Country
Brand
Application
Verification
Launch
Some selections cannot be changed later, including use case and billing category.

5. India doesn't support Multi-use RCS agents
   Current Vonage documentation says Multi-use isn't available in India.

Therefore our agent should be Transactional.

That's actually perfect for this POC.

6. RCS isn't visually identical everywhere
   Rich-card rendering and capabilities vary by client/device; Google explicitly recommends testing target devices.

7. Payment isn't actually inside RCS
   It's:

RCS
↓
Open URL / Webview
↓
Razorpay
That distinction should be shown honestly in the architecture.

8. Public webhook
   Vonage needs to reach your service.

For POC:

localhost
↓
Cloudflare Quick Tunnel
↓
https://xxxxx.trycloudflare.com
↓
Vonage
Cloudflare explicitly provides Quick Tunnels for testing without an account/domain.

9. AI can become the slowest component
   The workflow must not become:

RCS
↓
LLM
↓
LLM
↓
LLM
↓
RCS
We should keep AI calls bounded:

one decision call
one retrieval
one response generation
Everything else deterministic.

10. Don't put real customer information into the demo
    Use:

fake customers
fake addresses
fake assets
fake work orders
fake phone numbers
fake payment amounts
This avoids privacy/compliance issues entirely.

29. How I would handle AI uncertainty
    Use three levels of authority:

LEVEL 1 — DETERMINISTIC

Can this action legally/technically happen?

permission
SLA
inventory
price
appointment
technician
state
idempotency

LEVEL 2 — AI

What is probably happening?

Which resolution is best?

What information is missing?

How should we explain this?

LEVEL 3 — HUMAN

Should we allow a high-risk decision?
So:

AI suggests
↓
Policy validates
↓
Human if required
↓
Execute
This is exactly aligned with your existing "blank-over-wrong", evidence-gated and human-override approach.

30. What I would NOT include
    This is important because your instinct will probably be to add everything.

Don't add:

Kubernetes
multiple cloud providers
full ecommerce storefront
full technician mobile app
real route optimization
full Salesforce Agentforce
multi-tenant SaaS
WhatsApp initially
voice initially
complex billing engine
real production payment
They don't improve the core demonstration.

We need to prove:

RCS

- AI
- Salesforce
- MCP
- RAG
- Commerce
- Payment
- reliability
  not build a company.

31. What I would add that you didn't explicitly ask for
    These are essential.

A. Decision Trace
Every AI decision should have:

{
"caseId": "WO-10281",
"decision": "RESCHEDULE",
"reason": [
"technician delayed",
"customer SLA allows 2h window",
"alternative technician unavailable"
],
"knowledgeSources": [
"sla-policy-v4"
],
"toolsUsed": [
"salesforce.getAppointment",
"salesforce.getTechnician",
"inventory.getAvailability"
],
"confidence": 0.91,
"policyResult": "APPROVED"
}

This is incredible for the demo because you can literally show:

"Here's why the AI made this decision."

B. AI Decision Dashboard
Grafana:

AI decisions
├── automatically resolved
├── customer approval required
├── human escalation
├── rejected by policy
└── failed

RCS
├── sent
├── delivered
├── read
├── rejected
└── fallback

Workflow
├── latency
├── retries
├── DLQ
└── recovery time
Vonage status callbacks expose states such as submitted, delivered, read, rejected and undeliverable, so this becomes real operational telemetry rather than a fake dashboard.

32. A demo control panel would be extremely useful
    Build a tiny internal React page:

┌─────────────────────────────────────────────┐
│ FIELD SERVICE AI CONTROL CENTER │
├─────────────────────────────────────────────┤
│ │
│ WO-10281 │
│ │
│ ● Appointment Risk │
│ ● AI Investigation │
│ ● Customer Contacted │
│ ● Customer Selected 11-1 │
│ ● Part Reserved │
│ ● Payment Approved │
│ ● Technician Dispatched │
│ ● Service Completed │
│ │
│ AI Decision │
│ "Reschedule to 11-1" │
│ │
│ Why │
│ • technician delayed │
│ • alternate resource available │
│ • SLA preserved │
│ │
│ [Simulate Technician Delay] │
│ [Simulate Inventory Failure] │
│ [Simulate Salesforce Down] │
│ [Simulate RCS Rejection] │
└─────────────────────────────────────────────┘
This turns the demo into something the Vonage team can control live.

33. Our target architecture should therefore be
    ┌─────────────────────┐
    │ RCS CUSTOMER │
    └──────────┬──────────┘
    │
    TEXT / CARD / IMAGE / LOCATION
    │
    ▼
    ┌─────────────────────┐
    │ VONAGE │
    │ Messages API │
    └──────────┬──────────┘
    │
    webhook/events
    │
    ▼
    ┌─────────────────────┐
    │ Node Gateway │
    └──────────┬──────────┘
    │
    RabbitMQ
    │
    ▼
    ┌──────────────────────────┐
    │ LangGraph │
    │ │
    │ State + orchestration │
    │ interruptions │
    │ decision workflow │
    └────────────┬─────────────┘
    │
    ┌──────────────────────┼─────────────────────┐
    │ │ │
    ▼ ▼ ▼
    Salesforce MCP LlamaIndex RAG Commerce MCP
    │ │ │
    ▼ ▼ ▼
    Field Service Manuals/SOPs Quotes/Orders
    │ │
    ▼ ▼
    Inventory Razorpay
    │
    ▼
    Test Payment
    And:

                  EVERY MUTATION

AI suggestion
↓
Policy validation
↓
Permission validation
↓
Idempotency check
↓
Transaction
↓
Event
↓
Audit
That is the engineering philosophy I would make visible throughout the demo.

34. The "Vonage wow" checklist
    The final demo should ideally hit these in one continuous story:

✓ Branded RCS agent
✓ Rich card
✓ Carousel
✓ Suggested reply
✓ Suggested action
✓ Webview
✓ Calendar
✓ Share location
✓ View location
✓ Dial support
✓ Customer photo
✓ Customer response
✓ PDF service report
✓ RCS delivery callback
✓ AI reasoning
✓ RAG
✓ Salesforce
✓ MCP
✓ Inventory
✓ Commerce
✓ Razorpay test payment
✓ Human approval
✓ RabbitMQ
✓ Idempotency
✓ Retry
✓ DLQ
✓ Reconciliation
✓ RCS capability check
✓ RCS → SMS fallback
✓ Observability
✓ Decision trace
Vonage currently supports the relevant RCS interaction primitives, including cards/carousels, suggestions, webviews, location, calendar and dial actions.

35. One decision I would make now
    Do not use Eudoro as the appliance-commerce platform.

Use:

Salesforce
↓
Field Service + Inventory

Tiny Service-Commerce service
↓
Parts / Quotes / Orders

Razorpay
↓
Payment
Reuse Eudoro's transaction patterns, idempotency, payment integration, event design and reliability code, not its domain model. That keeps the story clean and lets you say:

"We used Salesforce as the field-service system of record, our own service-commerce layer for parts/quotes, and Vonage as the customer interaction channel."

That is much more believable.

36. And I would make this our actual problem statement
    When a home-service appointment becomes at risk because of technician delays, inventory problems, asset complexity, or other operational exceptions, an AI recovery orchestrator gathers context from enterprise systems, reasons over service knowledge, validates possible actions against deterministic business policies, negotiates the best resolution with the customer through RCS, executes the resulting changes across Salesforce, inventory, commerce and payment systems, and remains resilient to duplicate events, failures, unavailable services and communication-channel limitations.

That's the POC.

Not:

"AI chatbot using RCS."

Not:

"Salesforce + MCP demo."

Not:

"RCS rich card demo."

It is an AI-powered operational recovery system, with RCS acting as the customer's real-time control plane.

The next artifact we should create
Before writing code, the next thing to lock down is a POC specification containing the exact domain model, event catalog, Salesforce objects, MCP tools, LangGraph state machine, RAG documents, RCS message-by-message conversation, failure matrix, APIs, repositories/services, and a 10–15 minute Vonage demo script. That will prevent the project from becoming an uncontrolled collection of technologies.
