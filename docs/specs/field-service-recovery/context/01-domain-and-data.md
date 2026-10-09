# Context: Domain & Data

> **Living doc.** The domain model we build on. **Salesforce owns it** — we don't invent
> work-order / technician / asset / inventory tables. Our own storage is small and exists only
> for things Salesforce shouldn't hold: conversation state, idempotency, audit, AI decisions,
> and the knowledge vectors.

## The one rule

**Three systems of record, no overlap (Decision A, 2026-10-10):**
- **Salesforce Field Service** owns the **service domain** — customer, asset, warranty,
  appointment, technician.
- **The e-com inventory service** owns **product data** — image, price, stock.
- **Our PostgreSQL** owns the **conversation and the AI** — what we asked, what we decided, what we
  already processed.

If a fact is about the service visit (who, what asset, which appointment) it's Salesforce's. If it's
about a product (image, price, how much stock) it's the e-com's. If it's about *this recovery case*
(the options we sent, the version, the decision trace) it's ours.

Mixing these up is the most likely early design mistake. A "current appointment time" is
Salesforce's. A "PCB-492 costs ₹4,800 and 7 are in Noida" is the e-com's. A "we sent the customer 3
slot options at 09:30 and they haven't replied" is ours.

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

### Inventory — a SEPARATE e-com source (Decision A, 2026-10-10)

> **Changed 2026-10-10.** Inventory was previously documented as living in Salesforce Field Service.
> **Decision A** moves it to a **separate e-com inventory service** that owns **product image +
> price + stock**; Salesforce owns only the service domain (appointment, asset, customer,
> technician, warranty). Salesforce FS *does* have an inventory model (`ProductItem`/`Location`), so
> this is a deliberate design choice, not a capability gap — it matches the real-world shape where
> stock lives in a commerce/ERP system, and it matches the code, where [`inventory.py`] is already a
> seam separate from [`salesforce.py`]. The e-com build (admin dashboard, no customer storefront) is
> a real Node/Postgres service, swapped in behind the `InventoryTools` seam. Stack/host TBD.

| Concept (in the e-com source) | Role |
|--------|------|
| Product | The part type (PCB-492) — carries **image URL + price (paise) + warranty-covered flag**. |
| Stock at location | Quantity of a part **at a location** (Noida depot: 7). |
| Location | Depot / technician van. |
| Reservation (atomic) | The `reserve` action decrements stock under a check — no oversell (NFR-5). |

The orchestrator never talks to this store directly — only through the `InventoryTools` seam
(`find_part` read, `reserve` action), today `FakeInventory`, later the e-com HTTP API.

Demo stock (all fake):

```
Noida Warehouse:  PCB-492 ×7 · Motor-X21 ×4 · Compressor ×2 · Filter-100 ×31
Delhi Warehouse:  PCB-492 ×0 · Motor-X21 ×9 · Filter-100 ×17
Technician Van:   PCB-492 ×0
```

## Our PostgreSQL — the small, deliberate store

Only what Salesforce shouldn't own. Everything here is keyed by **`correlationId`** (the recovery
case) — the one tenancy key that scopes every case-related record in the system.

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

## How the stores meet

```
Salesforce (service domain) ─┐
                             ├─MCP read tools──▶  LangGraph (holds case state in Postgres)
e-com (product + stock)    ──┘                          │
         ▲                                              │
         └────────────── MCP action tools (validated) ──┘
                         every mutation → emit event → audit row
```

- The graph **reads** Salesforce (appointment/asset/customer/technician) and the e-com (product
  image/price/stock) through MCP read tools when it needs current facts — it does not cache them as
  truth.
- The graph **writes** (reschedule → Salesforce, reserve → e-com) only through MCP action tools,
  which run the authority ladder first (see [`02-orchestration-and-policy.md`](02-orchestration-and-policy.md)).

## Things that will look one way but aren't

- **`correlationId` is not a Salesforce field** — it's our case key. In the demo it equals the
  work-order id for legibility, but don't assume Salesforce "knows" it; we carry it.
- **Inventory counts are live, not cached.** The number the AI saw when proposing a part can be
  stale by execution time — that's exactly failure scenario NFR-5, handled by an atomic reserve,
  not by trusting the earlier read.
- **Warranty decides the *path*, not just a label.** Covered → free replacement flow; not covered
  → quote + payment flow. The branch is driven by Salesforce warranty data, validated by policy.

---

*Last updated 2026-10-10 — Decision A: inventory moved to a separate e-com source (image + price +
stock); Salesforce owns the service domain only.*
