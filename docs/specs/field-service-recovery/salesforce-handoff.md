# Salesforce handoff — what FieldFlow AI needs from the org (offload sheet)

**Status:** OPEN — provisioning not started · **Created:** 2026-10-08 · **Owner split:** you (tech
lead, has a Dev-Edition org, SF experience, new to Field Service) + a Salesforce dev · **For:** the
real Salesforce swap, build **Step 9c** ([`build-step-9.md`](build-step-9.md)).

> **What this is:** the single sheet of Salesforce work to get done so we can swap `FakeSalesforce`
> for the real org. The orchestrator is the **MCP client**; Salesforce is the data/action source
> (your "Headless 360" — API-only, no Salesforce UI in the demo). **You provision + grant access; I
> generate the integration code.** Nothing here touches our Python until the org is ready.

## 0. The one thing to understand first

Field Service (FS) is a Salesforce add-on with its **own data model**. A real service visit is a
chain of objects, not one record:

```
Account ─ Contact (customer)
   └─ WorkOrder (the job) ── Asset (the unit being fixed) ── warranty
         └─ ServiceAppointment (the scheduled visit: start/end, SLA, status)  ← our "appointment"
               └─ assigned ServiceResource (the technician) ── Skills, ServiceTerritory
   Inventory: Product2 → ProductItem (stock at a Location)
```

Our whole system keys off **one ServiceAppointment** and the records hanging off it. That's exactly
the shape `FakeSalesforce` fakes today, so the swap is a data-source change, not a redesign.

## 1. The tool surface we must back with the real org

Each of our tools (`app/tools/registry.py`) maps to a Salesforce read or write. This is the contract
— confirm the **object + field API names** in your org so I generate matching SOQL/DML.

| Our tool | Kind | Salesforce object(s) | What we read/write |
|----------|------|----------------------|--------------------|
| `salesforce.get_appointment` | read | **ServiceAppointment** (+ parent **WorkOrder**) | `SchedStartTime`, `SchedEndTime`, `Status`, `ServiceTerritoryId`, SLA window (`DueDate`/`ArrivalWindowEndTime`), links to WorkOrder → Asset/Contact/Resource |
| `salesforce.get_customer` | read | **Contact** (via WorkOrder.ContactId) | `Name`, `Phone`/`MobilePhone` |
| `salesforce.get_asset` | read | **Asset** (+ warranty, see §4 OQ-A) | `Name`/model, warranty active? |
| `salesforce.get_technician` | read | **ServiceResource** (+ **ServiceResourceSkill**) | name, skills, `ServiceTerritoryId` |
| `inventory.find_part` | read | **ProductItem** (+ **Location**) | `QuantityOnHand` per location for a part |
| `reschedule.confirm` | action | **ServiceAppointment** update | set new `SchedStartTime`/`SchedEndTime` (or FS scheduling API) |
| `inventory.reserve` | action | **ProductItem** (atomic decrement) | reserve N of a part — conditional update, no oversell (NFR-5) |
| at-risk trigger | event | **Pub/Sub API** on ServiceAppointment | "appointment is at risk" → starts a recovery case |

## 2. Checklist — mostly the SF dev (the heavy FS config)

- [ ] **Enable Field Service** in the Dev-Edition org (the FS managed package + FS Settings).
- [ ] **Create one demo chain** (all fake data): 1 Account + Contact, 1 Asset (Daikin-style model),
      1 ServiceResource with a skill (e.g. `daikin-inverter`) + a ServiceTerritory, 1 WorkOrder +
      1 ServiceAppointment linked together, and **ProductItem stock** for one part (e.g. `CAP-492`,
      qty 1) at a Location. (Matches our fake so the existing demos just work.)
- [ ] **Decide + implement warranty** (OQ-A below) — simplest is a checkbox on Asset.
- [ ] **Decide + implement the at-risk event** (OQ-B) — a Platform Event or CDC on ServiceAppointment.
- [ ] Confirm the **exact API names** of every field in the §1 table (send me the list).

## 3. Checklist — you can DIY (you have the org + SF experience)

- [ ] **Connected App** (OAuth) for an integration user — **client-credentials flow** (headless, no
      human login). I need: the login URL (`https://<domain>.my.salesforce.com`), client id, client
      secret, and the integration user it runs as.
- [ ] **Integration user + permission set**: least-privilege — **read** on the §1 read objects,
      **edit** on ServiceAppointment + ProductItem, and **subscribe** to the Pub/Sub channel.
- [ ] (Optional, if you want to learn FS) load the demo data via Data Loader and poke the objects in
      SOQL — good way to confirm the field names for §2's last item.

## 4. Open decisions (my recommendation — your/the SF dev's call)

- **OQ-A — how is warranty modelled?** *Rec:* a custom checkbox **`Warranty_Active__c` on Asset** for
  the demo (one field, trivial). The "proper" FS way is the **AssetWarranty** object + warranty terms
  — more realistic but more setup. Checkbox now, upgrade later.
- **OQ-B — how is "appointment at risk" signalled?** *Rec:* a **Platform Event** `Appointment_At_Risk__e`
  we publish (fields: workOrderId, appointmentId, reason, delayMinutes) — clean and explicit, matches
  our current event. Alternative: **Change Data Capture** on ServiceAppointment.Status (no custom
  object, but noisier). We keep firing via `/sim` for the demo; the real Pub/Sub subscriber is the
  production path.
- **OQ-C — hosted MCP, or REST-behind-the-Toolbox first?** *Rec:* **REST/SOQL behind the existing
  Toolbox seam first** (fastest path to a real org; the tool names don't change), then wrap as a real
  hosted MCP server once Salesforce's hosted MCP is enabled in the org. Both satisfy "orchestrator =
  MCP client" at the seam; this just sequences the work.
- **OQ-D — reschedule: direct field update or the FS scheduling API?** *Rec:* **direct
  `SchedStartTime`/`SchedEndTime` update** for the demo (simple, visible). The FS **Appointment
  Booking / scheduling** API is the realistic path but heavier — defer.

## 5. What I generate once the org is ready (so you can scope the SF dev's time)

- The **OAuth client-credentials** auth + token refresh.
- One **SOQL query per read tool** and the **DML update** for reschedule/reserve, wired behind the
  current `build_toolbox()` seam (reads go live before actions, same as Step 2).
- The **Pub/Sub API subscriber** for the at-risk event.
- A **live smoke test** (gated, like RAG/Groq/Razorpay): one real appointment → real reads → a real
  reschedule, run once against the org.

**So the SF dev's job is mostly provisioning + data + permissions + the event; the integration code
is mine.** The smallest version: give me a Connected App + integration user + the demo chain + the
field API names, and I can have the read tools talking to the real org without the dev writing Apex.

## 6. What I need from you to start Step 9c

1. The Connected App creds (login URL, client id/secret, integration user).
2. The §1 field API names as they exist in your org.
3. OQ-A/B/C/D decisions (my recs are safe defaults).
4. Confirmation the demo chain + ProductItem stock exist.

Until then, `FakeSalesforce` stays the backing and every test runs offline.

---

## 7. Addendum — you already build Apex HTTP APIs: where MCP fits

You said you build custom HTTP endpoints in **Apex (`@RestResource`)**. That's a clean integration
surface and changes the recommended path. Plain-English on the terms:

- **Apex REST** = a custom HTTP endpoint you write in Salesforce (e.g. `GET /services/apexrest/
  fieldflow/appointment/{id}`). You control the exact JSON it returns.
- **MCP (Model Context Protocol)** = a standard way to expose "tools" to an AI client. It is **not**
  a Salesforce thing — it's a thin wrapper that says "here are the callable tools and their inputs."

**Two layers, and they stack — you don't have to learn MCP to start:**

1. **Now (fastest): point our Toolbox straight at your Apex REST endpoints.** Our `build_toolbox()`
   is already "MCP-shaped" (named read/action tools). I make each tool do an **HTTPS call to your
   Apex endpoint** instead of the fake. So all you expose is a handful of Apex REST endpoints that
   match the §1 tool surface — I write the Python that calls them. No MCP server yet, no wire
   protocol, real org data flowing.
2. **Later (optional): wrap those as a real MCP server.** A small server (Salesforce's hosted MCP if
   your org has it, or a thin process we run) advertises the same tools and calls your Apex endpoints
   underneath. Our orchestrator becomes a real MCP client. **Same seam — only `build_toolbox()`
   changes.** This is the "Headless 360" end state.

**So the cleanest offload for you:** expose **Apex REST endpoints matching the §1 tools** (one per
read, one per action), return JSON with the field names from §1. I map them to our Toolbox. The SF
dev then only needs to provision the org + data + the at-risk event; you own the Apex surface you're
already comfortable with.

Suggested Apex REST endpoints (names are illustrative — your call):

```
GET  /apexrest/fieldflow/appointment/{id}     -> { appointmentId, slaWindowMinutes, caseState,
                                                    customerId, assetId, resourceId }
GET  /apexrest/fieldflow/customer/{id}         -> { name, phone }
GET  /apexrest/fieldflow/asset/{id}            -> { model, warranty }        // "active" | "expired"
GET  /apexrest/fieldflow/technician/{id}       -> { name, skills[], territory }
GET  /apexrest/fieldflow/part/{partNo}         -> [ { location, qty } ]
POST /apexrest/fieldflow/reschedule            -> { status }                 // body: {appointmentId, slotId}
POST /apexrest/fieldflow/reserve               -> { ok }                     // body: {partNo, qty} (atomic)
```

If you give me the final endpoint URLs + the integration-user auth, I wire the real reads first
(safe), then the two actions — same order as Step 2.
