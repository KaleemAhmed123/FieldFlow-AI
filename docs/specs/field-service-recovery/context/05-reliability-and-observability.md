# Context: Reliability & Observability

> **Living doc.** The layer that makes FieldFlow AI credible as production, not a demo. The
> Vonage team will care about this more than another pretty card. *(Spine: RabbitMQ + DLQ +
> idempotency are built; Logfire + the failure demos are planned next.)*

## The one rule

**Nothing is lost, nothing happens twice, and everything is explainable.** Every event survives a
failure (RabbitMQ + DLQ), every message/reply acts once (idempotency), and every decision/mutation
leaves a trace (audit + decision trace + dashboards).

## The reliability spine

```
inbound event / webhook
      │  (correlationId + eventId stamped here)
      ▼
   RabbitMQ ──▶ consumer ──▶ LangGraph
      │  on failure: retry → exponential backoff → DLQ → reconciliation
      ▼
   PostgreSQL  (durable case state · idempotency keys · audit · AI decisions)
```

- **RabbitMQ** carries every event so a downstream outage (e.g. Salesforce down) never drops
  work. Failed messages retry with backoff, then land in a **DLQ** (dead-letter queue) for
  **reconciliation** rather than vanishing.
- **PostgreSQL** holds the durable truth about the case (the LangGraph checkpoint), the
  idempotency keys, the append-only audit log, and the AI decision traces.

## The six failure demos (mandatory — these are the show)

| ID | Scenario | What the system does |
|----|----------|----------------------|
| **NFR-1** | RCS unavailable / rejected | Vonage **RCS → SMS failover**; the message still lands, workflow continues. |
| **NFR-2** | Duplicate webhook / double customer tap | **Idempotency** on the message/event UUID — the second copy is ignored; no double reschedule, no double charge. |
| **NFR-3** | Salesforce temporarily down | Event not lost: **retry → backoff → DLQ → reconciliation**; it completes when Salesforce returns. |
| **NFR-4** | AI low-confidence / risky recommendation | Routed to **human approval** before any execution (Level 3). |
| **NFR-5** | Inventory changed between recommend and execute | **Atomic reserve** fails cleanly → graph resumes → recalculates options → re-offers. |
| **NFR-6** | Customer replies against a stale workflow version | Conversation state is **versioned**; the stale tap is rejected and current options re-sent. |

Each is **triggerable live** from the demo control panel, so your manager (or Vonage) can break
the system on purpose and watch it recover.

## The authority levels (reliability's twin)

Reliability isn't only about retries — it's about not doing the wrong thing confidently. The
[`authority ladder`](02-orchestration-and-policy.md) (deterministic → AI → human) is a reliability
control: it prevents a plausible-but-wrong AI action from executing. NFR-4 is that control firing.

## Observability — a god-eye view, not a fake dashboard

The goal is total visibility: for **any** event or request we can see the full story live — every
step the case took, every tool call, every LLM call, every DB query, timing, and why the AI
decided what it did. Two complementary tools:

**1. Logfire — the live trace view (primary).**
[Pydantic Logfire](https://logfire.pydantic.dev) is our live tracing + cloud dashboard. It's
built on **OpenTelemetry** (the open standard for traces/metrics/logs) and made by the Pydantic
team, so it fits a Python/FastAPI/Pydantic stack with almost no glue. One `logfire.configure()`
plus its auto-instrumentation gives us, per request/case:

- the full **trace tree** — webhook/sim intake → RabbitMQ publish → consumer → each LangGraph
  node → every MCP tool call → every SQL query → the LLM call — each as a timed **span**;
- the **correlation id** attached to every span, so one case is one filterable trace end to end;
- **live tailing** — watch requests stream in and open any one to debug it, with errors and
  stack traces inline;
- our **decision trace** attached as span attributes, so "why did the AI choose this" sits right
  on the trace.

> Term: a **span** = one timed unit of work (a function, a query, an API call). A **trace** = all
> the spans for one request/case, as a tree. **OpenTelemetry (OTel)** = the vendor-neutral
> standard Logfire speaks, so we're not locked in — the same data can go elsewhere later.
> *(LangSmith is the LLM-specific alternative; Logfire wins here because it traces the whole
> system — queue, DB, HTTP, LLM — not just the model.)*

**2. Prometheus + Grafana — the metrics/counters (secondary, optional for the POC).**
Counts and rates over time, fed by **real Vonage status callbacks** (submitted, delivered, read,
rejected, undeliverable), so the numbers are true:

```
AI decisions   : auto-resolved · approval-required · human-escalation · rejected-by-policy · failed
RCS            : sent · delivered · read · rejected · fallback(→SMS)
Workflow       : latency · retries · DLQ depth · recovery time
```

**The decision trace** per case — `{caseId, decision, reason[], knowledgeSources[], toolsUsed[],
confidence, policyResult}` — is a must-have: it rides on the Logfire trace *and* is stored in
Postgres (`ai_decisions`), so "here's exactly why the AI chose this" is both live and durable.
The **correlation id** threads every log line, span, event, tool call, message and audit row, so
a single case is followed end to end — the god-eye view.

## Things that will look one way but aren't

- **A DLQ message is not a failure we hide** — it's the proof we didn't lose work. The
  reconciliation step (replay / resolve) is part of the demo, not an embarrassment.
- **Idempotency is keyed on the provider's UUID**, not on our own guesswork about "have we seen
  something like this". Same UUID = same effect as once.
- **The telemetry is real, not staged.** Logfire traces real execution and the metrics come from
  real Vonage callbacks. If someone points at a number or opens a trace, it's true — don't stub
  it for the demo, it undercuts the whole reliability story.
- **"Recovered" means state-consistent across systems**, not just "we sent an SMS". A recovery is
  done when Salesforce, inventory, commerce and the customer all agree.

---

*Last updated 2026-10-07 — kept in sync with the code as it lands.*
