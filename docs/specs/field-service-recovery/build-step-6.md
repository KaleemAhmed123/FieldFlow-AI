# Build Step 6 — Commerce module (quotes/orders) + Razorpay Test-Mode

**Status:** SHIPPED mock-first 2026-10-08 (54 pytest green, ruff clean, `import app.main` OK; the
live Razorpay Test-Mode call is step 9, gated) · **Created:** 2026-10-08 · **Last updated:** 2026-10-08

> Goal: when a recovery needs **paid work** (a part not covered by warranty), the system builds a
> **quote**, the customer **approves + pays** over RCS (a Razorpay page behind an "Approve & Pay"
> button), we create the **order**, take the **payment**, and confirm — all while the one rule
> holds: **AI proposes, deterministic policy decides, a human approves risk, tools act and may
> refuse.** Build order #6 ([`scaffold.md`](scaffold.md) §6: "Commerce module (quotes/orders) +
> Razorpay Test-Mode"). **Mock-first** — `FakeRazorpay` behind a `PaymentGateway` seam; no live
> Razorpay call and no new dep until the user says go.

---

## 1. Task

- **Name:** Commerce module (parts → quote → order → payment → confirm) + Razorpay Test-Mode, mock-first.
- **"Done" looks like:**
  - A `FakeRazorpay` behind a `PaymentGateway` interface (same seam pattern as `FakeVonage` and the
    LLM proposer ladder). The real Razorpay client swaps in at one line, no caller changes.
  - A commerce branch in the existing graph: **chargeable repair → quote → (human gate if
    high-value) → order + payment link → customer "Approve & Pay" over RCS → payment captured →
    confirm → close.**
  - **Every money mutation (quote, order, payment, refund) climbs the same authority ladder** and
    follows the "every mutation" invariant in [`context/02`](context/02-orchestration-and-policy.md):
    policy/price → permission → idempotency → transaction → emit → audit + decision trace.
  - **Payment idempotency (no double-charge on a retry/duplicate webhook)** — a hard requirement,
    treated like NFR-2.
  - Env knobs in `.env`/`.env.example` (`RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, commerce
    thresholds). Blank keys → `FakeRazorpay` (same convention as the LLM/Jina keys).
  - **All 47 existing tests stay green** (the commerce branch only fires for a chargeable job, so
    the default warranty-covered demo is untouched). New tests for the quote/payment flow + the
    no-double-charge guard.

## 2. What you asked for (your words, so nothing is lost to scrollback)

- `FakeRazorpay` behind a `PaymentGateway` interface — same seam as `FakeVonage` / the proposer
  ladder, so unit tests stay offline and the real client swaps in at one line.
- A commerce flow that fits the graph: parts price → QUOTE → customer approves over RCS → create an
  ORDER → take PAYMENT (Razorpay test) → confirm. **Decide which steps are graph nodes vs
  commerce-service calls.**
- **CRITICAL:** every payment/order mutation MUST climb the authority ladder and follow the "every
  mutation" invariant. **Payment idempotency (no double-charge) is a hard requirement — like NFR-2.**
  The LLM may propose a quote amount but **policy/price authority decides**; a human approves
  high-value or refund actions (risk-tiering, like Step 5).
- Env knobs: `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, any amount thresholds.
- Keep all 47 tests green with the fake; add tests for the quote/payment flow + the
  idempotency/no-double-charge guard.
- House rules: **plan first, write it here, list open questions with recommendations, WAIT for the
  explicit go.** Surface the user's action items (they have Razorpay TEST keys in another project —
  they'll COPY them into `.env`, only needed for the one gated live call at the end) and the junior
  delegation map. Mock-first; no live call / no new deps until go. Update `playbook.md` + this file's
  Explanation in the same change when we ship. Ask before editing any `context/**` doc.

## 3. Open questions — ANSWERED 2026-10-08 (still awaiting the explicit "go build")

**Answers locked:** OQ1 → **one tap** ("Approve & Pay"). OQ2 → **out-of-warranty is the authority,
but tied to the reason scenarios** (see the map below) so payment is driven by the event's `reason`
+ warranty, not a one-off appointment. OQ3 → **minimal refund tool + test, no graph branch.** OQ4 →
**two-layer idempotency.** The defaults named at the end of this section stand.

**OQ2 resolution — the scenario → flow map (chargeable rule):** a job is chargeable when the chosen
option needs a **part** AND **either** the asset is **out of active warranty** **or** the reason is
**`additional_fault_found`** (a newly found fault is outside the original warranty scope → customer
pays). The `reason` is already on the event + warranty is in context, so **no new event field**.

| Reason (archetype) | Needs part? | Warranty | Flow |
|---|---|---|---|
| `technician_delay`, `traffic_weather`, `technician_no_show`, `customer_access_issue` (delay) | no | — | free: reschedule → close |
| `part_missing`, `wrong_part_shipped` (parts) | yes | active | free (covered): reserve → close |
| `additional_fault_found` (parts) | yes | any | **PAID: quote → Approve&Pay → capture → close** |
| any parts/complex reason fired on `SA-OOW` (out-of-warranty asset) | yes | expired | **PAID** |
| `asset_complex`, `safety_risk`, `warranty_dispute` (complex) | — | — | human approval first (Step 5), then the archetype's flow above |

Demo two ways: fire `reason=additional_fault_found` on the default appointment, **or** fire any
parts reason on `appointmentId=SA-OOW` (the new out-of-warranty fake asset).

---

### The original open questions (kept for the record)

> Plain-English note on two terms used below:
> - **Node** = one step in the LangGraph flow (a box in the diagram). It can pause ("interrupt").
> - **Action tool** = a validated function in the Toolbox that *mutates* and can *refuse*; the model
>   may call it but the function decides the outcome (runs the deterministic ladder).

**OQ1 — "Approve the quote" and "pay": one customer tap, or two?**
- **My recommendation: ONE tap — an "Approve & Pay ₹X" card** whose button is the Razorpay Open-URL
  link. Approving *is* paying.
- **Why:** it's how RCS + Razorpay actually work (context/00: *"approves a quote and pays — all
  inside the message thread"*, *"Approve & Pay opens a Razorpay page"*). It also means **one** new
  customer interrupt instead of two, so fewer moving parts. Creating a Razorpay **order** before
  payment is correct (an order always precedes a payment in Razorpay), so nothing is lost.
- *Alternative (rejected unless you want it):* a separate "Approve quote" tap, then a "Pay" tap —
  two interrupts, more nodes, no extra realism.

**OQ2 — What makes a job *chargeable* (so the commerce branch fires at all)?**
- **My recommendation: warranty is the authority.** A part is chargeable when the asset is **not
  under active warranty**. I'll add **one out-of-warranty appointment** to `FakeSalesforce` (e.g.
  `SA-OOW` → asset `AST-OOW`, warranty `expired`). You demo the paid flow by firing with
  `appointmentId=SA-OOW` and a parts reason; the default `SA-19281` (warranty active) keeps the
  free/existing flow and the 47 tests untouched.
- **Why:** warranty entitlement is already a real policy check (context/02). This keeps warranty as
  the lever, needs no new event field, and reuses the existing `appointmentId` knob in `/sim`.
- *Alternative (rejected):* a `chargeable: true` flag on the event — simpler to type but makes
  chargeability an input, not a policy decision. Weaker story.

**OQ3 — Refund: build it, or just leave the seam?**
- **My recommendation: a minimal `commerce.refund` action tool + one test, but NO refund branch in
  the graph.** `commerce.refund` always routes to a human (risk-tiering), validates the order is
  paid, and calls `FakeRazorpay.refund` (idempotent). No graph node because there's no demo scenario
  that triggers a refund mid-flow.
- **Why:** `commerce.refund` is a named seam in context/03; a tool + test keeps it honest and
  demoable via `/tools` without building an unused flow (YAGNI on the branch).
- *Alternatives:* (a) **defer refund entirely** (not even the tool) — leanest; (b) **full refund
  flow** (a graph branch + a trigger) — more than the demo needs.

**OQ4 — Context-doc update (gated by your "ask first" rule).**
- **My recommendation: after Step 6 ships,** update [`context/03`](context/03-knowledge-and-tools.md)
  (mark `commerce.*` + `workorder.close` as built, not just named seams) and one line in
  [`context/00`](context/00-overview.md). **Not now, and only on your yes.**

### Choices I'm taking as obvious defaults (named out loud, not blocking — tell me to change any)

- **Human gate = reuse `/sim/approve`.** High-value quotes and refunds pause at a new `quote_approval`
  interrupt (status `AWAITING_QUOTE_APPROVAL`), resumed by the **existing** `/sim/approve` operator
  endpoint. No new approval endpoint.
- **High-value threshold** = `COMMERCE_HIGH_VALUE_PAISE` env knob, default **₹5,000** (500000 paise).
  At/above it, the quote routes to a human before any payment link is offered.
- **Payment idempotency = two layers** (both tiny, together they *are* NFR-2 for money):
  1. **Gateway-level:** `FakeRazorpay.capture(paymentId)` is idempotent — a repeat returns the same
     receipt with `alreadyCaptured=True` and charges **once**. (This is the real Razorpay mechanism:
     you capture a specific payment id once.)
  2. **Envelope-level:** the `/sim/payment` call carries an `eventId`; the resume path dedupes it
     against the `IdempotencyKey` table (exactly like `handle_event` does for at-risk events), so
     firing the same payment twice doesn't even re-run the graph. *(Shipped as `/sim/payment` — a
     normal /sim step like `/sim/customer-reply`, no inbound webhook; the user's POC rule.)*
- **Money is integer paise, never float.** Razorpay works in paise; floats lose money. The card shows
  rupees (₹X.XX) for display only. (Correctness — not simplified away.)
- **Price book lives in code** (a small dict, like the per-reason confidence priors), **the authority
  that decides the amount.** The LLM may *suggest* a number; the price book computes the real charge
  and the suggestion is ignored/clamped. Labour fee + currency + high-value threshold are env knobs.
- **No `razorpay` pip dep and no live call until your go** — same gate as the Step 5 live Groq call.

## 4. Plan

### 4.1 Where commerce fits the graph (the text flow diagram)

The commerce branch hangs off `execute`, *after* the reschedule is confirmed. A free/warranty job
flows exactly as today (`execute → verify → close`); a chargeable job detours through commerce.

```
 ... offer_to_customer → await_reply → execute (reschedule confirmed)
                                           │
                                   route_commerce?
                         ┌─────────────────┴───────────────────────┐
             not chargeable                                   chargeable (chosen option needs a part
             (covered / delay)                                 AND [asset out of warranty OR
                 │                                              reason == additional_fault_found])
                 │                                                  │
                 ▼                                                  ▼
             verify → close                                   build_quote        [MUTATION: quote]
             (today's path, 47 tests                          price authority decides the amount
              unchanged)                                      (LLM may suggest; price book decides)
                                                                    │
                                                            high-value? ──yes──▶ quote_approval
                                                                    │              (interrupt, Level-3
                                                                    │               human; /sim/approve)
                                                                    │              rejected ─▶ close
                                                                    │ no / approved
                                                                    ▼
                                                           create_payment          [MUTATION: order]
                                                           commerce.create_order + create_payment_link
                                                           (FakeRazorpay → hosted URL)
                                                                    │
                                                                    ▼
                                                           offer_payment (RCS "Approve & Pay ₹X"
                                                           card → Open-URL to the Razorpay page)
                                                                    │
                                                                    ▼
                                                           await_payment (interrupt; wait for the
                                                           customer to pay — resumed via /sim/payment)
                                                                    │
                                                                    ▼
                                                           settle_payment          [MUTATION: payment]
                                                           commerce.capture_payment (IDEMPOTENT —
                                                           no double-charge); failed ─▶ offer_payment
                                                                    │ captured
                                                                    ▼
                                                              verify → close (PAID)
```

**Which steps are graph nodes vs commerce-service calls (your explicit ask):**

| Concern | Lives in | Why |
|---------|----------|-----|
| Orchestration, interrupts, routing (`route_commerce`, the two waits) | **graph nodes** | sequencing + pauses are the graph's job |
| Price authority, build the quote, build the order, create the payment link, capture, refund | **Toolbox action tools** (`commerce.*`) calling the **commerce service** | they *mutate* + run the deterministic ladder + may refuse; the model never decides the outcome |
| Idempotency (gateway + envelope), audit rows, decision-trace rows, emit | **service layer** (`case_service`) | keeps graph nodes DB-free + enforces the "every mutation" invariant once, centrally |
| Razorpay itself | **`PaymentGateway` seam** (`FakeRazorpay` now, real later) | mock-first; one-line swap |

### 4.2 Files to touch (and the one rule each obeys)

**New:**
- `app/commerce/razorpay.py` — `PaymentGateway` Protocol + `FakeRazorpay` (in-memory; idempotent
  `capture` keyed by paymentId; `create_payment_link`, `refund`). Mirrors `tools/vonage.py`.
- `app/commerce/service.py` — the **price book** (the deterministic amount authority), `build_quote`,
  `create_order`, `Quote`/`Order` shapes (plain dicts/dataclasses). No DB, no network.
- `tests/test_commerce.py` — price authority, the paid flow to PAID/CLOSED, high-value → human,
  refund, and the **no-double-charge** guard. Plus a `FakeRazorpay` idempotency unit test.

**Changed:**
- `app/commerce/__init__.py` — flesh out the thin router (keep the existing stub endpoint; optionally
  add a read `/commerce/quote/{id}` for the panel). Keep the router thin; logic lives in `service.py`.
- `app/tools/registry.py` — register `commerce.create_quote`, `commerce.create_order`,
  `commerce.create_payment_link`, `commerce.capture_payment`, `commerce.refund` as **action tools**
  that run the ladder (price authority, amount > 0, order belongs to this case, not already paid/
  refunded) and return a `ToolResult` that may refuse. `build_toolbox(..., commerce)` grows one param.
- `app/graph/build.py` — the new nodes (`build_quote`, `quote_approval`, `create_payment`,
  `offer_payment`, `await_payment`, `settle_payment`), the `route_commerce` conditional off `execute`,
  and the trace enrichment (quote lines, amount, price authority, paymentLinkId, paymentId,
  captured). The LLM still only proposes.
- `app/services/case_service.py` — extend `_PAUSED_STATUS` / `_DECISION_STATUS` / `_AUDIT_KIND` for
  the commerce statuses; add **envelope idempotency to the payment resume** (optional
  `idempotency_key` on `resume_case`; a duplicate returns the case unchanged — NFR-2 for money).
- `app/sim/routes.py` — `POST /sim/payment` (a normal /sim step, like `/sim/customer-reply`; the
  POC fires every event via /sim, no inbound webhooks): `{correlationId, paymentId, status, eventId}`
  resumes `await_payment`.
- `app/tools/salesforce.py` — add the out-of-warranty appointment/asset (`SA-OOW`/`AST-OOW`) per OQ2
  (one of the two chargeable demos; the other is `reason=additional_fault_found` on the default appt).
- `app/config.py` + `.env.example` — `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `COMMERCE_CURRENCY`
  (INR), `COMMERCE_LABOUR_PAISE`, `COMMERCE_HIGH_VALUE_PAISE` (default 500000 = ₹5,000).
- `app/main.py` — build `FakeRazorpay` + commerce service, pass into `build_toolbox`.
- `tests/conftest.py` — a `commerce`/`razorpay` fixture + wire into the `toolbox`/`graph` fixtures.
- `playbook.md` — the paid-flow demo curls + env (on ship).

### 4.3 Build order (mock-first; the gated live call is dead last)

1. Config + `.env.example` knobs (no `razorpay` dep yet — gated).
2. `PaymentGateway` + `FakeRazorpay` (+ its idempotency unit test).
3. Commerce `service.py`: price book authority + `build_quote`/`create_order` (+ price test).
4. Register `commerce.*` action tools in the Toolbox (ladder + refusals).
5. Graph nodes + `route_commerce` + trace enrichment; keep the non-chargeable path identical.
6. `case_service` status/audit wiring + `/sim/payment` envelope idempotency.
7. `/sim/payment`; out-of-warranty fake data.
8. `test_commerce.py` (full paid flow + no-double-charge + high-value human gate + refund). **All 47
   existing green + new ones green; ruff clean; `import app.main` OK.**
9. **(GATED — needs your go + your copied TEST keys)** add `razorpay` dep, implement the real
   `RazorpayGateway` (create order + payment link), one live test-mode payment confirmed back
   through `/sim/payment` (we keep the /sim step — no inbound webhook unless you later choose to
   accept real Razorpay callbacks). Then update `playbook.md` + this file's Explanation.

### 4.4 Alternatives rejected

- **Commerce as a separate app/service** — the whole project decided commerce is a *module inside the
  orchestrator* (scaffold §1, context/00). Rejected.
- **Commerce as its own event + consumer path** (`quote.required`) — more machinery; the existing
  graph already has the context + interrupts. Rejected; hang it off `execute`.
- **LLM sets the price** — breaks the one rule (model proposes, deterministic decides). The price book
  is the authority; the LLM number is ignored/clamped.
- **Float money** — loses paise. Integer paise only.
- **Real `razorpay` SDK now** — mock-first; added only at the gated live step.
- **Webhook-signature verification in the fake** — not meaningful offline; it lands with the real
  gateway at step 9's live call.

## 5. Tasks (ticked as I go — nothing ticked until you approve the plan)

- [x] 1. Config + `.env.example` commerce/Razorpay knobs (no dep yet).
- [x] 2. `PaymentGateway` + `FakeRazorpay` + idempotent-capture unit test (+ a `__main__` self-check).
- [x] 3. Commerce `service.py` price book authority + `build_quote`/`create_order` + price test.
- [x] 4. `commerce.*` action tools in the Toolbox (ladder + refusals); `build_toolbox` param.
- [x] 5. Graph: `route_commerce` + the 6 commerce nodes + trace enrichment; non-chargeable path identical.
- [x] 6. `case_service` status/audit wiring + payment-webhook envelope idempotency.
- [x] 7. `/sim/payment-webhook` + out-of-warranty fake appointment/asset (`SA-OOW`/`AST-OOW`).
- [x] 8. `test_commerce.py` + conftest fixtures; **54 green** (47 prior + 7), ruff clean, import OK.
- [ ] 9. **(GATED — your go + copied TEST keys)** real Razorpay dep + gateway + ONE live test-mode
  payment; then playbook + this Explanation get the live note.

## 6. Updates

- **2026-10-08** — Plan created (sections 1–5). Collapsed "approve + pay" into one RCS tap (OQ1);
  warranty decides chargeability via a new out-of-warranty fake appointment (OQ2); refund = a minimal
  tool + test, no graph branch (OQ3); two-layer payment idempotency and integer-paise money taken as
  defaults.
- **2026-10-08 (OQs answered)** — OQ1 one tap · OQ3 minimal refund tool+test · OQ4 two-layer
  idempotency, all as recommended. **OQ2 refined by the user:** chargeability is tied to the existing
  10-reason scenarios, not a single special appointment — a job is PAID when the chosen option needs
  a part AND (asset out of warranty OR `reason == additional_fault_found`). Driven by the event's
  `reason` + warranty in context; **no new event field**. Scenario→flow map added to §3.
  `route_commerce` implements exactly that rule. **Still no code — waiting on the explicit "go build."**
- **2026-10-08 (shipped mock-first)** — User approved the plan + the ₹5,000 threshold. Implemented
  steps 1–8 offline. **54 pytest green** (47 prior + 7 new commerce), ruff clean, `import app.main`
  OK, both module self-checks pass. No `razorpay` dep added, no live call (step 9, gated). Two small
  decisions made during the build, named here because they refine the plan:
  1. **`Card` gained a `payUrl` field** (contract) so the "Approve & Pay" button has an Open-URL
     target. It's optional/nullable, so existing cards and the schema export are unaffected.
  2. **The high-value gate reads `settings` live in the edge lambda**, so the threshold is tunable
     per run (and the test monkeypatches it) without rebuilding the graph.
  The LLM did **not** gain a "propose an amount" path — it already proposes *which part* in its
  option, and the price book prices it; that satisfies "LLM proposes, policy decides" for money
  without touching the Step 5 proposer (YAGNI).
- **2026-10-08 (post-review tweaks)** — Per the user: (1) **renamed `/sim/payment-webhook` →
  `/sim/payment`** and dropped all "webhook" framing — payment completion is a normal /sim step
  (like `/sim/customer-reply`); no inbound webhook in the POC. (2) **Expanded the price book** to six
  example parts with different values (₹900–₹12,500) so demos can show cheap parts, the ₹5k human
  gate, and a far-over-gate compressor. (3) Playbook now documents **Swagger UI at `/docs`** (fire
  endpoints from the browser instead of curl) + a "how to read this playbook" note. (4) context/02
  already had the gate; **context/03 + context/00 updated** to mark `commerce.*` built. Still 54
  green, ruff clean.

## 7. Explanation

### 1. What changed
A **commerce branch** now hangs off the graph: when a repair needs paid work, the system builds a
**quote**, the customer **approves + pays** over RCS (one "Approve & Pay ₹X" card whose button opens a
Razorpay page), we create the **order**, **capture** the payment, and close. New `app/commerce/`
code: a `PaymentGateway` seam with `FakeRazorpay`, and a `CommerceService` holding the **price book**
(the amount authority). Five new `commerce.*` action tools, six new graph nodes, a `/sim/payment`
endpoint (a normal /sim step, no inbound webhook), and an out-of-warranty demo appointment.

### 2. Why it was needed
The demo's story includes a chargeable repair, and the enterprise-grade claim rests on money being
handled correctly: the LLM must not set prices, every money step must climb the authority ladder, and
a retried payment webhook must **never charge twice**. Build order #6.

### 3. How it works, step by step
1. A customer picks a slot; `execute` reserves the part and reschedules (unchanged).
2. **`route_commerce`** (inside `execute`): if the chosen option needs a part AND the asset is out of
   warranty OR `reason == additional_fault_found`, it detours to `build_quote`; otherwise straight to
   `verify → close` (the old, free path — all 47 prior tests untouched).
3. **`build_quote`** calls `commerce.create_quote`; the **price book** computes the amount (part price
   + labour). The LLM never sets it.
4. If the quote is **≥ ₹5,000**, the graph pauses at **`quote_approval`** (`AWAITING_QUOTE_APPROVAL`)
   for an operator, resumed by the existing `/sim/approve`. A rejection closes the case.
5. **`create_payment`** calls `commerce.create_order` then `commerce.create_payment_link`
   (FakeRazorpay → a hosted URL). **`offer_payment`** sends the "Approve & Pay ₹X" card (its `payUrl`
   is the Razorpay link). **`await_payment`** interrupts (`PAYMENT_PENDING`) and waits.
6. The customer **completes payment**, fired via `/sim/payment` (a normal /sim step, like
   `/sim/customer-reply` — no inbound webhook). **`settle_payment`** calls
   `commerce.capture_payment` (idempotent) → `verify → close` (`PAID`→`CLOSED`). A failed payment
   re-offers the card.
7. The decision trace carries `commerce.{quote, order, paymentLink, payment}` — show-your-work for money.

### 4. Files / functions changed
- **`app/commerce/razorpay.py`** (new): `PaymentGateway` Protocol + `FakeRazorpay` —
  `create_payment_link`, **idempotent** `capture` (keyed by paymentId), `refund`.
- **`app/commerce/service.py`** (new): `PRICE_BOOK_PAISE` (the authority), `CommerceService`
  (`price_part`, `build_quote`, `create_order`), `rupees()` display helper.
- **`app/tools/registry.py`**: `build_toolbox(..., commerce, gateway)`; five `commerce.*` action
  tools that run the ladder (price/amount checks) and may refuse.
- **`app/graph/build.py`**: `_is_chargeable`, `_commerce_trace`, `route_commerce` in `execute`, and
  nodes `build_quote`/`quote_approval`/`create_payment`/`offer_payment`/`await_payment`/
  `settle_payment` + their edges.
- **`app/services/case_service.py`**: commerce statuses in `_PAUSED_STATUS`/`_DECISION_STATUS`/
  `_AUDIT_KIND`; **envelope idempotency** via `resume_case(..., idempotency_key=...)`; payment receipt
  in the close audit payload.
- **`app/sim/routes.py`**: `POST /sim/payment` — a normal /sim step (no webhook); dedup via `eventId`.
- **`app/tools/salesforce.py`**: out-of-warranty `SA-OOW`/`AST-OOW`.
- **`packages/contract/.../types.py`**: `Card.payUrl`.
- **`app/config.py`** + **`.env.example`**: Razorpay keys + commerce knobs.
- **`app/main.py`**, **`tests/conftest.py`**: build + inject `CommerceService` + `FakeRazorpay`.
- **`tests/test_commerce.py`** (new): price authority, paid flow, no-double-charge (gateway +
  envelope), out-of-warranty trigger, high-value human gate, refund.

### 5. Important decisions
- **Price book is the authority** (code, like the confidence priors). The LLM proposes *which part*;
  deterministic code prices it — "AI proposes, policy decides" for money, with no Step-5 change.
- **One "Approve & Pay" tap** (OQ1) — matches RCS + Razorpay; one new customer interrupt.
- **Chargeability from the reason + warranty** (OQ2) — no new event field; two demo levers.
- **Two-layer no-double-charge** (OQ4): idempotent capture at the gateway + `eventId` dedupe on the
  `/sim/payment` call. Either alone stops a double charge; together they also stop a duplicate
  re-running the graph.
- **No webhooks in the POC** (the user's rule): payment completion is a normal `/sim/payment` step,
  the same simulation pattern as the at-risk event and the customer reply.
- **Integer paise, never float.** **Refund = tool + test, no graph branch** (OQ3).
- Rejected: commerce as a separate service/event, LLM-set prices, float money, real `razorpay` SDK now.

### 6. Tests / verification
- `cd apps/orchestrator && uv run pytest -q` → **54 passed** (47 prior + 7 new). `uv run ruff check .`
  → **All checks passed!**. `uv run python -c "import app.main"` → OK. `python -m app.commerce.razorpay`
  and `python -m app.commerce.service` self-checks pass. All offline (FakeRazorpay, no keys, no network).
- `test_commerce.py` pins: the book amount (370000 paise), the paid flow to `CLOSED` with the trace's
  commerce block, **the same payment fired twice charging once** (`len(_captured) == 1`, 2nd call
  `duplicate`),
  the `SA-OOW` out-of-warranty trigger, and a high-value quote pausing at `AWAITING_QUOTE_APPROVAL`
  then proceeding on `/sim/approve`.

### 7. Edge cases and limitations
- **Live Razorpay is unbuilt (step 9, gated).** No `razorpay` dep, no real order/link/capture yet —
  that lands with the real gateway + your TEST keys. Payment completion stays a `/sim/payment` step;
  a real inbound Razorpay webhook + signature check is only if you later choose to accept callbacks.
- **Quotes/orders live in graph state, not DB rows.** Durable truth is the case's decision trace +
  audit log (enough for the demo); a real system would persist quote/order tables.
- **A failed payment re-offers the same card indefinitely** — no retry cap / abandon path (POC).
- **Panel rendering** of the payment card / `payUrl` / commerce trace is Step 8.
- **Price book + labour priced for the demo** (CAP-492 ₹3,200, PCB-492 ₹4,800, labour ₹500); real
  pricing comes from Salesforce/commerce at step 9.
