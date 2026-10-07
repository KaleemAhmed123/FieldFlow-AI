# FieldFlow AI — Roles & Interface Contract

**Status:** Planning · **Started:** 2026-10-06 · **Last updated:** 2026-10-06

How the two of us build this in parallel without blocking each other, and the exact contract we
both build against.

---

## 1. The principle: not a wall, a shared track

You are the **lead and architect**, hands-on across AI, RCS and orchestration — **and** on the
Salesforce APIs, Pub/Sub and MCP. You want to get your hands dirty there too, and you guide
every step. The Salesforce dev **executes** the Field Service build and the commerce layer
under your direction. So this is a *shared* track with a clear contract, not a silo.

The contract in §4 is what makes "parallel" real: each side mocks the other and integrates late.

## 2. Ownership map

Legend: **D** = drives/owns · **G** = guides/reviews · **—** = not involved.

| Area | You | SF Dev | Notes |
|------|:---:|:------:|-------|
| Overall architecture & sequencing | **D** | G | You set direction. |
| Vonage RCS agent + Messages API integration | **D** | — | Agent config, cards, carousels, actions, webhooks, failover. |
| LangGraph orchestrator + policy engine | **D** | — | State machine, interrupts, deterministic authority. |
| LlamaIndex RAG (manuals, warranty, SOPs) | **D** | — | Knowledge layer. |
| MCP client (AI side) | **D** | G | How the agent calls tools. |
| MCP servers over Salesforce | **D** | **D** | **Shared** — you want hands-on; dev knows the org. Co-own. |
| Salesforce Field Service setup + data model | G | **D** | Dev executes; you review the object/event choices. |
| Salesforce Pub/Sub event publishing | G | **D** | Dev wires events; you consume them. |
| Service-commerce (parts/quotes/orders/payments/refunds) | G | **D** | Dev builds the thin service; reuses Eudoro patterns you point to. |
| Razorpay Test-Mode integration | **D** | G | You've got the Razorpay experience. |
| RabbitMQ + idempotency + retries + DLQ + reconciliation | **D** | — | Your reliability wheelhouse. |
| Observability (Prometheus/Grafana) | **D** | G | Dashboards fed by real callbacks. |
| Demo control panel + demo script | **D** | G | The live showcase surface. |

## 3. Field Service setup checklist (for the SF dev)

The dev is strong on general Salesforce but **new to Field Service**, so here's the concrete
order of operations so they're not hunting.

1. **Get the right org.** Sign up for the **special Field Service-enabled Developer Edition**
   (ships with the Field Service managed package + sample data) — *not* a generic DE. (Risk R3.)
2. **Enable Field Service** + install the managed package; confirm sample data loaded.
3. **Learn the object graph we actually use** (ignore the rest for now):
   - Domain: `Account`, `Contact`, `Asset`, `Case`, `WorkOrder`, `WorkOrderLineItem`,
     `ServiceAppointment`, `ServiceResource`, `ServiceResourceSkill`, `ServiceTerritory`,
     `Skill`, `SkillRequirement`, `ServiceContract`, `WarrantyTerm`, `ServiceReport`.
   - Inventory: `Product2`, `ProductItem`, `ProductItemTransaction`, `ProductRequest`,
     `ProductTransfer`, `ProductConsumed`, `Location` (depots/van).
4. **Seed the demo scenario** (all fake): WO-10281, Daikin Inverter AC asset, technician Rahul,
   today's appointment, Noida/Delhi depots with the stock levels from the SRS.
5. **Enable Pub/Sub API** and publish the events in §4.1 (platform events or CDC) when a work
   order / appointment changes.
6. **Enable Hosted MCP** in the DE and confirm the standard endpoints are reachable
   (`platform/sobject-reads`, etc.). This is where you and the dev co-work.
7. **Read-only first.** Expose read tools before any action tools; action tools are
   deterministic functions with validation (never raw API to the LLM).

## 4. The interface contract (build against this, both sides)

Lock this before parallel work. You build the AI/RCS side against a **fake** Salesforce/commerce;
the dev builds Salesforce/commerce against this **same** contract. Integration is then wiring,
not discovery.

### 4.1 Events (Salesforce → RabbitMQ → LangGraph)

Published by Salesforce Pub/Sub, normalized onto RabbitMQ. Every event carries a
`correlationId` and an `eventId` (used for idempotency).

```jsonc
// appointment.at_risk  — the trigger for a recovery case
{
  "eventId": "evt_8f2...",          // unique; dedup key
  "correlationId": "wo-10281",      // threads the whole case
  "event": "appointment.at_risk",
  "occurredAt": "2026-10-06T09:25:00+05:30",
  "appointmentId": "SA-19281",
  "workOrderId": "WO-10281",
  "reason": "technician_delay",     // technician_delay | part_missing | asset_complex | ...
  "detail": { "delayMinutes": 50 }
}
```

Other events, same envelope (`eventId`, `correlationId`, `event`, `occurredAt`, payload):

| Event | Payload keys | Raised when |
|-------|--------------|-------------|
| `appointment.rescheduled` | `appointmentId`, `newStart`, `newEnd`, `resourceId` | A slot change is committed in Salesforce. |
| `inventory.reserved` | `productItemId`, `locationId`, `qty`, `workOrderId` | A part is held. |
| `inventory.reserve_failed` | `productId`, `reason` | Stock gone between recommend and execute (NFR-5). |
| `workorder.completed` | `workOrderId`, `serviceReportId` | Job done; triggers PDF report (FR-13b). |
| `payment.succeeded` / `payment.failed` | `orderId`, `amount`, `providerRef` | Razorpay webhook result. |

### 4.2 MCP tools (LangGraph → enterprise systems)

**Read tools** (safe, idempotent):

```
salesforce.get_customer(customerId)            -> Customer
salesforce.get_asset(assetId)                  -> Asset { model, warrantyStatus, ... }
salesforce.get_work_order(workOrderId)         -> WorkOrder
salesforce.get_appointment(appointmentId)      -> ServiceAppointment
salesforce.get_technician(resourceId)          -> ServiceResource { skills, territory }
inventory.find_part(partNo)                    -> [ { locationId, qty } ]
knowledge.search_manual(model, query)          -> [ chunk ]          // RAG
knowledge.search_warranty_policy(assetId)      -> PolicyResult       // RAG
```

**Controlled action tools** (deterministic functions with validation — *not* raw API to the LLM):

```
reschedule.propose(appointmentId)              -> [ SlotOption ]     // policy-filtered
reschedule.confirm(appointmentId, slotId)      -> Result             // atomic
inventory.reserve(productItemId, qty)          -> Result             // atomic; may fail → NFR-5
commerce.create_quote(workOrderId, lines[])    -> Quote
commerce.create_order(quoteId)                 -> Order
commerce.create_payment_link(orderId)          -> { url }            // → RCS Open-URL
commerce.refund(orderId)                        -> Result
workorder.close(workOrderId)                   -> { serviceReportId }
```

**Contract rule:** every action tool runs the authority ladder before mutating — permission →
SLA → inventory → price → appointment/technician validity → idempotency → execute → emit event
→ audit. The LLM may *call* these tools but never decides their outcome; the function does.

### 4.3 RCS send surface (AI side owns, listed so the dev knows the shape)

```
vonage.send_card(to, card)                     // rich card + suggested actions
vonage.send_carousel(to, cards[])              // 2–10 slot options (FR-5)
vonage.send_text(to, text)
vonage.send_pdf_card(to, pdfUrl, caption)      // India / Google Messages (FR-13b)
vonage.check_capability(to)                    // before using a primitive (NFR → fallback)
vonage.send_with_fallback(to, rcsMsg, smsMsg)  // RCS → SMS failover (NFR-1)
```

## 5. How we work in parallel

1. **Both** agree §4 (this contract) — that's the one true blocking meeting.
2. **You** build AI/RCS/orchestration against a fake Salesforce+commerce that honours §4.
3. **Dev** builds Field Service + Pub/Sub + commerce to emit §4.1 and serve §4.2.
4. **Co-work** the MCP-over-Salesforce layer (shared ownership).
5. **Integrate** by swapping your fakes for the dev's real tools — a wiring step, because both
   sides already match the contract.

**Golden rules:** two people never edit the same file; the contract changes only by agreement
(any change gets a dated note here); each side verifies its own half against §4 before we wire.

## 6. Updates

- **2026-10-06** — Roles + contract created. You confirmed you want hands-on Salesforce/MCP, so
  MCP-over-Salesforce is co-owned, not handed off.
