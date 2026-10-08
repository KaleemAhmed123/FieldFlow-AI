# Context: Knowledge (RAG) & Tools (MCP)

> **Living doc.** Two separate concerns that are easy to confuse. **RAG = knowledge** (what's in
> the manuals). **MCP = live data + actions** (what's true right now, and what we may change).

## The one rule

**RAG answers "what is generally true?"; MCP answers "what is true right now, and may I change
it?"** Keep them apart:

- *"Does PCB-492 fit model XYZ-438? What's the repair SOP?"* → **RAG** (grounding/retrieval).
- *"How many PCB-492 are in Noida right now? Reserve one."* → **MCP** (live data + action).

Putting live inventory in RAG, or manuals in MCP, is the classic mistake. Don't.

---

## Part A — Knowledge (LlamaIndex + pgvector)

### What it solves

Salesforce knows the *data* ("Asset = Daikin AC, warranty active"). It does **not** know the
*knowledge*: service manuals, fault codes, repair procedures, warranty policy wording, technician
SOPs, safety steps, part compatibility, escalation rules. The AI needs that knowledge to reason.

### The pipeline

```
PDF manuals · warranty docs · SOPs · policy · part-compatibility tables · troubleshooting guides
        │
        ▼  chunk → embed → store
   pgvector (inside our PostgreSQL)
        │
        ▼  retrieve top-k for the current asset/question
   LangGraph node (retrieve_knowledge)
```

- **LlamaIndex** does the chunk/embed/retrieve. **pgvector** is the store (a Postgres extension —
  no separate vector DB to run; ₹0, local).
- Retrieval is **bounded** — one retrieval call per decision, not a chain. AI latency is a real
  risk (R9); knowledge lookups must not multiply.

### What it feeds

A retrieved chunk becomes a `knowledgeSource` in the decision trace, so the demo can show *"the
AI concluded 'likely control-board failure, PCB-492 compatible, warranty covered' grounded in
the Daikin XYZ-492 service manual and warranty policy v4."*

---

## Part B — Tools (MCP)

> **Built in Step 2 (2026-10-08, mock-first) — see [`../build-step-2.md`](../build-step-2.md).**
> The read/action surface below is live as an **in-process `Toolbox`** (`app/tools/registry.py`)
> over the fakes: granular Salesforce reads compose the context, `inventory.reserve` and
> `reschedule.confirm` are action tools that run the authority ladder and can refuse, and the
> decision trace's `toolsUsed` is real. `GET /tools` exposes the surface. It is MCP-*shaped*, not
> the wire protocol yet — a real hosted MCP client swaps into `build_toolbox()` at Step 9.
> `knowledge.*`, `workorder.close` and `reschedule.propose` are named seams, not built.
>
> **Commerce tools built in Step 6 (2026-10-08, mock-first) — see [`../build-step-6.md`](../build-step-6.md).**
> `commerce.create_quote`, `commerce.create_order`, `commerce.create_payment_link`,
> `commerce.capture_payment` and `commerce.refund` are live action tools over a `FakeRazorpay`
> gateway. The amount is set by a deterministic **price book** (the authority), not the LLM; capture
> is idempotent (no double-charge). Real Razorpay Test-Mode swaps in at the gated live step.

### What it solves

Instead of stuffing 50 raw APIs into a prompt, we expose business systems as a **small, controlled
tool surface**. Salesforce ships Hosted MCP servers free in Developer Edition; we also wrap
inventory and commerce as MCP tools. The graph reasons over this surface.

### The split that matters: read vs action

**Read tools** — safe, idempotent lookups. The model may call them freely.

```
salesforce.get_customer(customerId)
salesforce.get_asset(assetId)              -> { model, warrantyStatus, ... }
salesforce.get_work_order(workOrderId)
salesforce.get_appointment(appointmentId)
salesforce.get_technician(resourceId)      -> { skills, territory }
inventory.find_part(partNo)                -> [ { locationId, qty } ]
knowledge.search_manual(model, query)      -> [ chunk ]        (RAG behind an MCP tool)
knowledge.search_warranty_policy(assetId)  -> PolicyResult
```

**Controlled action tools** — validated functions that mutate. The model may *call* them, but the
**function decides the outcome** after running the authority ladder. Never raw Salesforce write
access to the LLM.

```
reschedule.propose(appointmentId)          -> [ SlotOption ]   (already policy-filtered)
reschedule.confirm(appointmentId, slotId)  -> Result           (atomic)
inventory.reserve(productItemId, qty)      -> Result           (atomic; may fail → NFR-5)
commerce.create_quote(workOrderId, lines)  -> Quote          (amount from the price book, BUILT)
commerce.create_order(quoteId)             -> Order           (BUILT)
commerce.create_payment_link(orderId)      -> { url }         (→ RCS Open-URL, BUILT)
commerce.capture_payment(paymentId)        -> Result          (idempotent; no double-charge, BUILT)
commerce.refund(orderId)                   -> Result          (a human approves refunds, BUILT)
workorder.close(workOrderId)               -> { serviceReportId }
```

(The illustrative signatures above are the intent; the shipped Step-6 shapes are in
[`../build-step-6.md`](../build-step-6.md). Payment completion is a normal `/sim/payment` step in the
POC, not an inbound webhook.)

(Full signatures are the contract in [`../roles.md`](../roles.md) §4.2 — both tracks build
against it.)

### Why MCP-over-Salesforce is co-owned

You want hands-on with the Salesforce APIs, Pub/Sub and hosted MCP; the SF dev knows the org. So
this layer is built together (see [`../roles.md`](../roles.md)). Read tools go live before any
action tool.

## Things that will look one way but aren't

- **An MCP action tool is not "let the model do it."** The model requests; the function validates
  and executes (or refuses). The authority lives in the function, not the prompt.
- **`knowledge.*` tools are RAG wearing an MCP coat.** They're read-only grounding. Don't give
  them side effects.
- **Hosted MCP respects Salesforce permissions** — the org's security still applies; MCP doesn't
  bypass it. Good: it means the tool surface can't exceed the integration user's rights.
- **Inventory read ≠ inventory truth at execution.** `find_part` can be stale by the time
  `reserve` runs; `reserve` is atomic and may fail. That gap is a feature we demo (NFR-5), not a
  bug to paper over.

---

*Last updated 2026-10-08 — Tools (MCP) surface built mock-first in Step 2; RAG live (Step 4);
commerce.* action tools built mock-first (Step 6).*
