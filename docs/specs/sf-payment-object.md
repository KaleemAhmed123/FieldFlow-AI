# SF payment object — write captured payments back to Salesforce

## 1. Task

- **Name:** Salesforce payment write-back (`FieldFlow_Payment__c`)
- **Status:** shipped — live-verified end to end on 2026-10-21
- **Started:** 2026-10-21
- **Last updated:** 2026-10-21

## 2. What you asked for

- Make a **custom payment object** in Salesforce with the fields we get from Razorpay, and write to it.
- Deploy the object + fields **using the APIs we have** (`apps/salesforce-apex/deploy_sf.py`), not
  by hand in the UI.
- Make an **Apex REST endpoint** that does the write. Reuse/match the existing Apex surface.
- Context (2026-10-21): every backend is **real** now (DB, SF, e-com, AI) — build real, not mock-first.

## 3. Open questions (answered)

1. **Object shape — dedicated object or fields on an existing one?**
   → **Dedicated `FieldFlow_Payment__c`** with a **lookup to ServiceAppointment**. Clean, one row per
   payment, shows as a related list on the appointment (answers "is it written to a related object?").
2. **Idempotency?** → **Upsert on `Payment_Id__c`** (External Id, Unique). A retried capture updates
   the one row, never duplicates — mirrors the gateway's no-double-charge guarantee.
3. **Build now or spec first?** → Build now (user gave an explicit go).

## 4. Plan

**Object** `FieldFlow_Payment__c` (AutoNumber name `PAY-{00000}`), fields:

| Field | Type | From (Razorpay/order) |
|---|---|---|
| `Payment_Id__c` | Text(64), External Id, Unique | receipt `paymentId` (upsert key) |
| `Payment_Ref__c` | Text(64) | `paymentRef` (payment-link id) |
| `Order_Id__c` | Text(64) | our `orderId` |
| `Amount_Paise__c` | Number(18,0) | `amountPaise` (integer paise) |
| `Currency_Code__c` | Text(8) | `currency` |
| `Status__c` | Text(32) | `captured` / etc. |
| `Service_Appointment__c` | Lookup(ServiceAppointment) | resolved from `appointmentId` |

**Endpoint** `POST /services/apexrest/fieldflow/payment` on the existing `FieldFlowRest` class
(not a new class) — upserts the record and links the appointment.

**Orchestrator** `salesforce.record_payment` tool, called best-effort in the graph's `settle_payment`
(money is already captured; a SF write hiccup must not strand the paid case). Fake-first: offline
`FakeSalesforce` stores in memory; `RestSalesforce` POSTs to the endpoint.

**Files touched:** `apps/salesforce-apex/FieldFlowRest.cls`, `apps/salesforce-apex/deploy_sf.py`,
`apps/orchestrator/app/tools/salesforce.py`, `app/tools/registry.py`, `app/graph/build.py`,
`apps/orchestrator/tests/test_salesforce_rest.py`, `playbook.md`.

**Rejected:** a new Apex class (the existing one already routes POSTs); a text field for the
appointment link (a real lookup tells the "related object" story and enables the related list);
creating the object via the Tooling API (it can't INSERT a CustomObject → used the Metadata API).

## 5. Tasks

- [x] Apex: `payment` POST branch + `recordPayment` + `toDecimal` on `FieldFlowRest`.
- [x] `deploy_sf.py`: create object (Metadata API) + fields (Tooling API), `--payment` flag.
- [x] `deploy_sf.py`: fix the class-name parser (matched prose "class is …" in a comment → always
      took the create path); stricter regex requiring `class <Name> {`.
- [x] `deploy_sf.py`: `--payment-perms` to grant the integration user object + field FLS.
- [x] Orchestrator: `record_payment` on the Protocol, `FakeSalesforce`, `RestSalesforce`.
- [x] Register `salesforce.record_payment` action tool; wire into `settle_payment` (best-effort).
- [x] Tests: Fake idempotency + the real POST path (httpx mock). Full suite 120 passed.
- [x] Deploy object + 7 fields + updated class to the live org (`astreait88-dev-ed`).
- [x] FLS grant (`--payment-perms`) — via a dedicated permission set (profile had Modify All Data).
- [x] End-to-end live smoke test: POST → row created + linked to SA-0001; repeat → same row (idempotent).

## 6. Updates

**2026-10-21** — Built + deployed. Object + 7 fields created via the Metadata API (Tooling can't
insert a CustomObject — hit `No such column 'FullName' on CustomObject`, switched to SOAP
`createMetadata`). Found + fixed a real deploy-script bug: the class-name regex matched "this class
is the foundation" in the doc comment, parsing the name as `is`, so it never updated the existing
class — always tried to create, which compiled in a context that rejected a Field-Service query.
Fixed with a stricter regex (name must be followed by `{`). Updated class deployed via the
MetadataContainer path. The live POST currently returns `Payment_Id__c is inaccessible` — field-level
security isn't granted to the integration user yet; the `--payment-perms` step does that but the
sandbox blocked it as a security change, so it's handed to the user.

## 6. Updates (cont.)

**2026-10-21 (later)** — FLS grant redesigned + shipped. The profile approach failed: the
integration user's profile has **Modify All Data**, and Salesforce rejects ObjectPermissions on a
MAD profile (`Cannot insert a record if parent permission set has Modify All Data`). Switched to a
**dedicated permission set** `FieldFlow_Payment_Access` (object + 7 field perms) assigned to the
integration user — no MAD conflict, additive, reproducible. Live smoke test passed: POST created
`a13dM…` linked to SA-0001; a repeat with the same `paymentId` returned the same record id (one row);
test record deleted afterwards. **Shipped.**

## 7. Explanation

**What changed.** Captured payments now land in Salesforce. A new custom object `FieldFlow_Payment__c`
holds one row per payment (Razorpay ids, amount in paise, status) with a **lookup to the
ServiceAppointment** it paid for — so a payment shows as a related record on the visit.

**Why it was needed.** Before, a payment lived only in Razorpay + the orchestrator's decision trace;
Salesforce (the system of record for the job) had no payment record. The manager asked for payment
data written back against the appointment.

**How it works, step by step.**
1. Customer pays → the gateway capture succeeds in the graph's `settle_payment` node.
2. `settle_payment` calls the Toolbox action `salesforce.record_payment` (best-effort: the money is
   already captured, so a SF write failure is logged onto the trace and never blocks closing the case).
3. `RestSalesforce.record_payment` POSTs the receipt to `POST /services/apexrest/fieldflow/payment`.
4. The Apex `recordPayment` **upserts** `FieldFlow_Payment__c` on the external-id `Payment_Id__c`
   (idempotent — a retried capture updates the one row), resolves the appointment by number/id and
   sets the lookup.
5. The record id + the capture receipt ride back onto the decision trace (`decision.paymentRecord`).
   Offline, `FakeSalesforce` stores it in memory with the same idempotency, so tests/demos run keyless.

**Files / functions changed.**
- `apps/salesforce-apex/FieldFlowRest.cls` — `doPost` now routes to `reschedule` or the new
  `recordPayment`; added `recordPayment` (upsert + link) and `toDecimal`.
- `apps/salesforce-apex/deploy_sf.py` — `PAYMENT_OBJECT`/`PAYMENT_FIELDS`; `metadata_create_object`
  (Metadata-API SOAP, since Tooling can't insert a CustomObject); `deploy_payment` + `--payment`;
  `grant_payment_perms` + `--payment-perms` (dedicated permission set); `data_api`/`data_query`
  helpers; **fixed** `parse_apex_text` (stricter class-name regex).
- `apps/orchestrator/app/tools/salesforce.py` — `record_payment` on the Protocol, `FakeSalesforce`,
  `RestSalesforce`.
- `app/tools/registry.py` — registered the `salesforce.record_payment` action tool.
- `app/graph/build.py` — `settle_payment` calls it best-effort and records the result on the trace.
- `apps/orchestrator/tests/test_salesforce_rest.py` — Fake idempotency + the real POST path.

**Important decisions.** Dedicated object + lookup (not fields on Case) for the related-list story;
reuse the existing Apex class (not a new one); upsert on the Razorpay payment id for idempotency;
Metadata API for the object (Tooling can't create it); a dedicated permission set for FLS (the
profile's Modify All Data blocks ObjectPermissions).

**Tests / verification.** Offline: `deploy_sf.py --self-check` ok; full orchestrator suite **120
passed**. Live: object + 7 fields + class deployed to `astreait88-dev-ed`; POST → record created and
linked to SA-0001; repeat → same record id (idempotent); test record deleted.

**Edge cases & limitations.** If the appointment id doesn't resolve, the payment is still recorded
but **unlinked** (not an error). A SF write failure in `settle_payment` is swallowed (money already
captured) — the payment then exists in Razorpay + the trace but not in SF until re-fired. `Currency_Code__c`
is a plain text field (not SF multi-currency). The grant lives on a dedicated permission set assigned
to the current integration user only — a different integration user would need the same assignment.
