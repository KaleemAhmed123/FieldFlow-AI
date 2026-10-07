# Context: Reliability & Observability

> **Design-time.** The layer that makes FieldFlow AI credible as production, not a demo. The
> Vonage team will care about this more than another pretty card.

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

## Observability — real telemetry, not a fake dashboard

Prometheus scrapes; Grafana shows. Fed by **real Vonage status callbacks** (submitted, delivered,
read, rejected, undeliverable), so the numbers are true.

```
AI decisions   : auto-resolved · approval-required · human-escalation · rejected-by-policy · failed
RCS            : sent · delivered · read · rejected · fallback(→SMS)
Workflow       : latency · retries · DLQ depth · recovery time
```

Plus the **decision trace** per case: `{caseId, decision, reason[], knowledgeSources[],
toolsUsed[], confidence, policyResult}` — the "here's exactly why the AI chose this" artifact.
And a **correlation id** threads every log line, event, tool call, message and audit row for one
case, so a single case can be followed end to end.

## Things that will look one way but aren't

- **A DLQ message is not a failure we hide** — it's the proof we didn't lose work. The
  reconciliation step (replay / resolve) is part of the demo, not an embarrassment.
- **Idempotency is keyed on the provider's UUID**, not on our own guesswork about "have we seen
  something like this". Same UUID = same effect as once.
- **The dashboard is wired to live callbacks.** If someone points at a number, it's real — don't
  stub the telemetry for the demo, it undercuts the whole reliability story.
- **"Recovered" means state-consistent across systems**, not just "we sent an SMS". A recovery is
  done when Salesforce, inventory, commerce and the customer all agree.

---

*Design-time snapshot: 2026-10-06 — Kaleem Ahmed*
