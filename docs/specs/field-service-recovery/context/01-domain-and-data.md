# Context: Domain & Data

> **Design-time.** The domain model we build on. **Salesforce owns it** — we don't invent
> work-order / technician / asset / inventory tables. Our own storage is small and exists only
> for things Salesforce shouldn't hold: conversation state, idempotency, audit, AI decisions,
> and the knowledge vectors.

## The one rule

**Salesforce Field Service is the system of record for the domain. PostgreSQL is the system of
record for the *conversation and the AI*.** If a fact is about the business (who, what asset,
which appointment, how much stock), it lives in Salesforce. If a fact is about *this recovery
case* (what we asked the customer, what we decided, what we already processed), it lives in our
Postgres.

Mixing these up is the most likely early design mistake. A "current appointment time" is
Salesforce's. A "we sent the customer 3 slot options at 09:30 and they haven't replied" is ours.

## Salesforce Field Service — the objects we actually use

Ignore the rest of the (large) Field Service model; this is our working set.

### Domain

| Object | Role in FieldFlow |
|--------|-------------------|
| `Account` / `Contact` | The customer. |
| `Asset` | The unit being serviced (Daikin Inverter AC). Carries model + warranty linkage. |
| `Case` | The service request wrapper. |
| `WorkOrder` + `WorkOrderLineItem` | The job and its line items. **Work-order id = our correlation id** in the demo. |
| `ServiceAppointment` | The scheduled visit — the thing that goes "at risk". |
| `ServiceResource` | The technician. |
| `ServiceResourceSkill` + `Skill` + `SkillRequirement` | Does this tech have the skill the job needs? (policy input) |
| `ServiceTerritory` | Geography — feeds travel-time / feasibility checks. |
| `ServiceContract` + `WarrantyTerm` | Is the repair covered? (free vs paid path) |
| `ServiceReport` | The completion document → becomes the PDF sent over RCS. |

### Inventory (also Salesforce — no separate store)

| Object | Role |
|--------|------|
| `Product2` | The part type (PCB-492). |
| `ProductItem` | Stock of a part **at a location** (Noida depot: 7). |
| `Location` | Depot / technician van. |
| `ProductItemTransaction` · `ProductTransfer` · `ProductConsumed` · `ProductRequest` | Stock movement + consumption that updates inventory. |

Demo stock (all fake):

```
Noida Warehouse:  PCB-492 ×7 · Motor-X21 ×4 · Compressor ×2 · Filter-100 ×31
Delhi Warehouse:  PCB-492 ×0 · Motor-X21 ×9 · Filter-100 ×17
Technician Van:   PCB-492 ×0
```

## Our PostgreSQL — the small, deliberate store

Only what Salesforce shouldn't own. Everything here is keyed by **`correlationId`** (the recovery
case), the way ONLYCOUPLEZ keys everything by `coupleId`.

| Table (intended) | Key | Why it exists |
|------------------|-----|---------------|
| `case_state` | `correlationId` | LangGraph checkpoint — where the graph is, what it's waiting for, the conversation version. |
| `idempotency_keys` | message/event UUID | So a duplicate webhook or double customer tap is processed **once** (NFR-2). |
| `audit_log` | `correlationId` + ts | Append-only. Every mutation, tool call, message, policy result. |
| `ai_decisions` | `correlationId` | The decision trace: `{decision, reason[], knowledgeSources[], toolsUsed[], confidence, policyResult}`. |
| `memory_chunks` | (knowledge id) | pgvector embeddings of manuals/warranty/SOPs for RAG. Not case-keyed. |

**The one tenancy key: `correlationId`.** It is stamped at the webhook/event gateway, threaded
through RabbitMQ, LangGraph, every MCP tool call, every message and every audit row. If you can't
answer "which case does this belong to?" you're missing the correlation id.

## How the two stores meet

```
Salesforce (truth about the business)  ──MCP read tools──▶  LangGraph (holds case state in Postgres)
         ▲                                                          │
         └────────────── MCP action tools (validated) ─────────────┘
                         every mutation → emit event → audit row
```

- The graph **reads** Salesforce through MCP read tools when it needs current business facts (it
  does not cache them as truth).
- The graph **writes** to Salesforce only through MCP action tools, which run the authority
  ladder first (see [`02-orchestration-and-policy.md`](02-orchestration-and-policy.md)).

## Things that will look one way but aren't

- **`correlationId` is not a Salesforce field** — it's our case key. In the demo it equals the
  work-order id for legibility, but don't assume Salesforce "knows" it; we carry it.
- **Inventory counts are live, not cached.** The number the AI saw when proposing a part can be
  stale by execution time — that's exactly failure scenario NFR-5, handled by an atomic reserve,
  not by trusting the earlier read.
- **Warranty decides the *path*, not just a label.** Covered → free replacement flow; not covered
  → quote + payment flow. The branch is driven by Salesforce warranty data, validated by policy.

---

*Design-time snapshot: 2026-10-06 — Kaleem Ahmed*
