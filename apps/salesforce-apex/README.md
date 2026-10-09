# FieldFlow — Salesforce Apex REST surface

The real Salesforce backing for FieldFlow's **read tools + reschedule action**, as plain **Apex
REST**. The orchestrator's Toolbox calls it over HTTPS; the authority ladder stays in our Python.

> **Why not a hosted-MCP tool?** Hosted MCP (Headless 360) is built for an *AI agent to discover and
> invoke* tools. Our orchestrator calls named tools **deterministically**, and the LLM must never
> decide a mutation. Apex REST keeps that clean. Hosted MCP can wrap these same endpoints later if we
> want that demo story — see `apps/headless360-sf/` (optional, not built yet). **Decision A:** no
> part/stock endpoint here — inventory is the e-com service.

## 1. What's in this folder

- `FieldFlowRest.cls` — the `@RestResource` class: 4 reads + reschedule, JSON shapes matching
  `apps/orchestrator/app/tools/salesforce.py` (`FakeSalesforce`).
- `FieldFlowRest.cls-meta.xml` — metadata (needed for an SFDX deploy).

## 2. Deploy it (pick ONE — both end up the same)

**Route A — Developer Console (fastest, no tooling):**
1. Your org → gear → **Developer Console**.
2. **File → New → Apex Class**, name it `FieldFlowRest`.
3. Paste the entire body of `FieldFlowRest.cls` (replace the stub). **File → Save.**

**Route B — VS Code + Salesforce CLI (if you use SFDX):**
```bash
# from repo root, with the Salesforce Extensions / sf CLI authed to your org:
sf project deploy start --source-dir apps/salesforce-apex --target-org <your-org-alias>
```

## 3. Org prerequisites (one-time)

- [ ] **Custom field** `Asset.Warranty_Active__c` (Checkbox). Setup → Object Manager → Asset →
      Fields → New → Checkbox. (This is the handoff OQ-A recommendation.) Tick it on in-warranty assets.
- [ ] **Integration-user access**: the user your Connected App runs as (the client-credentials
      "Run As" user, [salesforce-handoff.md §8](../../docs/specs/field-service-recovery/salesforce-handoff.md))
      needs **API Enabled** + Apex class access to `FieldFlowRest` (add it to their Permission Set →
      Apex Class Access) + read on the queried objects + edit on ServiceAppointment.
- [ ] **Demo data chain** exists (Account+Contact, Asset, ServiceResource+Territory, WorkOrder +
      ServiceAppointment linked) — handoff §8 step D.

## 4. Confirm the org assumptions (flagged in the .cls as A1–A4)

The SOQL assumes a standard Field Service shape. If your org differs, tell me and I adjust:
- **A1** warranty = `Asset.Warranty_Active__c` checkbox.
- **A2** `ServiceAppointment.ParentRecordId` → WorkOrder, which has `ContactId` + `AssetId`; the
  technician is the `ServiceResource` on the appointment's `AssignedResource`.
- **A3** the id we pass matches `AppointmentNumber` **or** the record `Id`.
- **A4** `slaWindowMinutes` is defaulted to 120 (no standard field).

## 5. Smoke-test (after deploy + a client-credentials token)

The **same** `SF_*` client-credentials token you set for the trigger works for Apex REST:
```bash
# 1) get a token (see salesforce-handoff.md §8F) → $TOKEN + the instance url
# 2) call a read:
curl -H "Authorization: Bearer $TOKEN" \
  "https://<yourdomain>.my.salesforce.com/services/apexrest/fieldflow/appointment/SA-19281"
# → {"appointmentId":"SA-19281","customerId":"003...","assetId":"02i...","resourceId":"0Hn...",
#    "slaWindowMinutes":120,"caseState":"Scheduled"}
```

## 6. How the orchestrator consumes it (next step, I write this)

A `RestSalesforce` class implementing the `SalesforceTools` Protocol (client-credentials token +
httpx calls to these endpoints), swapped in behind `build_toolbox` when the `SF_*` creds are set —
exactly like `build_vonage` / `build_gateway`. The graph and tests don't change. **Reads can go live
first (safe), then reschedule.** Mock-first unit tests parse canned JSON; the live calls are gated on
this class being deployed + the data chain existing.
