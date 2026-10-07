# Context: Orchestration & Policy

> **Living doc.** The decision core: LangGraph holds the long-running case; the Policy Engine is
> the authority on what may happen. See the rich version in
> [`../diagrams/03-decision-authority.excalidraw`](../diagrams/03-decision-authority.excalidraw).

## The one rule

**The LLM proposes; deterministic policy decides; a human approves risk.** No mutation ever
skips the deterministic check. Phrase it as the **authority ladder**:

```
LEVEL 1 — DETERMINISTIC   Can this action legally/technically happen?
                          permission · SLA · inventory · price · appointment · technician · state · idempotency
LEVEL 2 — AI              What is probably happening? Which resolution is best? What's missing? How to explain it?
LEVEL 3 — HUMAN           Should we allow a high-risk / low-confidence decision?
```

Level 2 (AI) is sandwiched: it only ever runs *after* Level 1 says an action is possible, and its
risky outputs are gated by Level 3 before execution.

## Why LangGraph (not "we wanted LangGraph")

A recovery case is **not** one request/response. It is a case that:
- spans minutes-to-hours while new facts arrive (technician delay, then customer location, then a
  photo),
- must **pause and wait** for the customer to tap something,
- and must **resume exactly where it stopped** when they do.

LangGraph is a framework for exactly this: the graph state is **checkpointed** to Postgres, the
graph **interrupts** when it needs the customer/human, and **resumes** on the next event. Without
it you end up hand-rolling a state machine + a durable wait + resume logic — which is what
LangGraph already is.

## The graph (built in Step 1)

> This flow is **built and tested** (mock-first) as of 2026-10-07 — see
> [`../build-step-1.md`](../build-step-1.md). The LLM proposer, RAG and real tools are still mocked;
> the orchestration, policy and interrupt/resume are real.

```
appointment.at_risk
      │
      ▼
 load_case ──▶ load context (customer · appointment · technician · asset · warranty · inventory)
      │
      ▼
 retrieve_knowledge (RAG: manual · warranty policy · SOP)
      │
      ▼
 evaluate_sla
      │
      ▼
 generate_options            ← LEVEL 2 (AI proposes candidate resolutions)
      │
      ▼
 policy_validate  ◀──────────── LEVEL 1 (deterministic; removes illegal options)
      │
      ├── all auto-safe ─────▶ execute
      │
      └── risky / low-conf ──▶ human_approval  ← LEVEL 3 (interrupt; wait)
                                      │
                                      ▼
                                   execute
      │
      ▼
 offer_to_customer (RCS)  ← interrupt; wait for tap
      │
      ▼
 resume_on_reply ──▶ (reserve part · quote · payment · confirm · report)  — each a mutation
      │
      ▼
 verify ──▶ close
```

Every box that **mutates** (reschedule, reserve, quote, order, pay, close) routes through the
same sequence — see "every mutation" below.

## The Policy Engine — the authority

Plain deterministic code. Given *proposed* options + current context, it removes every option
that can't legally happen (each with a reason) and returns `APPROVED / PARTIAL / DENIED`; a
separate `needs_human()` is the confidence gate. Checks it applies today (Step 1): required skill ·
SLA window · working hours · customer entitlement (warranty) · inventory on hand · current case
state. Still to wire as the real tools land: technician availability · territory · travel time ·
price authority. Idempotency is enforced one level up, at the event.

The AI may generate an option that looks great and is illegal (wrong skill, outside SLA). Policy
removes it **before** the customer ever sees it. The customer is only ever offered valid options.

## Every mutation (the invariant that makes this enterprise-grade)

```
AI suggestion → Policy validation → Permission validation → Idempotency check
             → Transaction → Emit event → Audit (+ decision trace)
```

This sequence is identical for every write — rescheduling, reserving a part, creating a quote,
taking payment, closing the work order. If a new mutation is added and it doesn't follow this,
it's wrong. (This is the "conditional-update, never read-then-write" discipline, applied to
cross-system actions.)

## Interrupts & resume — the two waits

1. **Wait for the customer** — after offering options / requesting a photo / sending a quote, the
   graph interrupts and persists. The next inbound reply (matched by `correlationId`, resumed via
   `/sim/customer-reply` in the POC) continues it.
2. **Wait for a human** — when policy says "needs human" or AI confidence is below threshold, the
   graph interrupts for an operator decision (resumed via `/sim/approve`).

Both waits are durable via LangGraph's checkpointer. **Step 1 uses an in-memory checkpointer** —
real interrupt/resume in-process, but a restart loses paused cases. Swapping in the Postgres
checkpointer (so a crash mid-wait resumes rather than restarts) is a one-dependency change behind
`make_checkpointer()`.

## Things that will look one way but aren't

- **Confidence is a gate, not a vibe.** Below the threshold → Level 3 human, no exceptions. Don't
  let "the model seemed sure" bypass it (NFR-4).
- **A resumed reply can be stale.** If the case moved on (options changed) since the customer was
  asked, their old tap is **rejected** and current options are re-sent — conversation state is
  versioned (NFR-6). Don't treat every inbound reply as valid for the current state.
- **The graph does not call Vonage/Salesforce directly in node code** — it goes through the MCP
  tools and the Vonage adapter, so every external effect is auditable and mockable. *(Built in
  Step 2: nodes now call an in-process `Toolbox`; read tools compose context, action tools run the
  ladder and may refuse. See [`03-knowledge-and-tools.md`](03-knowledge-and-tools.md).)*

---

*Last updated 2026-10-08 — decision core built in Step 1; nodes call the Toolbox as of Step 2.*
