# Salesforce record trigger + rich RCS messages

**Status:** Planning (awaiting go) · **Started:** 2026-10-12 · **Last updated:** 2026-10-12

> The piece that makes the demo start *inside Salesforce* — mark an appointment at-risk and the
> whole recovery flow runs — and makes the customer's phone show the *full* set of RCS capabilities
> (not just a bare slot carousel). Builds on build-step-9c (the seam + payload mapper already exist).

---

## 1. Task

Two linked deliverables, in order:

1. **SF record trigger** — a real Salesforce trigger on `ServiceAppointment` fires when the record is
   marked at-risk (by any of several fields), does an async HTTP callout to a new orchestrator
   endpoint `POST /webhooks/sf/at-risk`, which drops the event on the same RabbitMQ exchange `/sim` uses.
   Downstream (consumer, graph, policy, RCS) is unchanged.
2. **Rich RCS messages** — upgrade the customer-facing messages from a single bare carousel to a
   per-case set of rich cards that exercise the SRS §7 primitive list (AI-written body, suggested
   actions: View / Add to Calendar / Dial / Share Location, carousel, Open-URL payment, photo
   request, PDF report), driven by the case archetype and the seeded demo data.

**Done =**
- Tick the at-risk field on a seeded appointment in the org → within seconds a case appears at
  `GET /cases/{workOrderId}` with `OPTIONS_SENT`, exactly as `/sim/appointment-at-risk` produces today.
- The customer message(s) for that case render the right rich primitives for its archetype, both as
  real Vonage RCS (when armed) and in the React panel.

## 2. What you asked for (your words, captured)

- "Make the record trigger which will call the endpoint and our flow would run." Trigger = **Apex
  trigger + `@future(callout=true)`**. All SF code in Apex. Deploy via a **Python Tooling API script**.
- Trigger fields: "multiple fields can be trigger so even two of them could trigger and add more
  fields maybe you can search about field service to get more triggers." → use **real Field Service
  at-risk signals**, support **several** of them.
- Rich message: "Generate multiple options, show all capabilities we discussed in SRS — call, share
  location, payment, and all possible things… multiple impressive messages on front based on case,
  that is why I seeded the data."
- After this: the **copilot chat UI** (build-step-14), then the small ones (e-com `/api/mcp` fix,
  one Razorpay live fire, more Vonage sends, panel polish).

## 3. Open questions (my recommendation first; your answer pending)

| # | Question | My recommendation | **Answer (2026-10-12)** |
|---|----------|-------------------|-------------------------|
| Q1 | Does your Field Service org have the **FSL managed package** installed (so `FSL__InJeopardy__c` / `FSL__InJeopardyReason__c` exist)? | Default: assume no; use standard `Status` + our own custom fields so the Apex always compiles. | **No FSL.** Use standard `Status = 'Cannot Complete'` + new custom fields (`At_Risk__c`, `At_Risk_Reason__c`, `Delay_Minutes__c`). Create more fields if a scenario needs them. |
| Q2 | Rich-message **depth** — fully wire every primitive, or render all + wire the cheap interactive ones with heavy compute simulated? | Render all + wire cheap ones; simulate-but-label share-location/photo/PDF. | **Full rich experience** — all RCS primitives + all orchestrator capabilities. Heavy compute simulated-but-labelled per the recommendation. |
| Q3 | Where do the orchestrator **URL + shared secret** live in Salesforce? | A **Named Credential** `FieldFlow` (URL + custom header `X-FieldFlow-Secret`); Apex calls `callout:FieldFlow/...`. | **Named Credential**, and **deployed as metadata by `deploy_sf.py`** so the user clicks nothing. |

**New decision (2026-10-12):** all SF metadata is Claude-authored as source in the repo and deployed
programmatically — **Apex via Tooling API, declarative metadata (objects/fields/Flows/perm sets/Named
Credential) via Metadata API**, both in one Python `deploy_sf.py` using the `SF_*` token. **No `sf` CLI.**
Add metadata only when a scenario needs it (no speculative objects/fields).

## 4. Plan

### Phase 1 — the trigger (SF Apex + one orchestrator endpoint)

**Salesforce (all in `apps/salesforce-apex/`):**
- **Custom fields on ServiceAppointment** (you add, 2 min each — Tooling API for fields is fiddly):
  - `At_Risk__c` (Checkbox) — the explicit "fire it" tick.
  - `At_Risk_Reason__c` (Picklist, values = our 10 contract reasons) — which archetype runs.
  - `Delay_Minutes__c` (Number) — for delay scenarios.
- **`ServiceAppointmentAtRisk.trigger`** (after insert, after update): collects appointment Ids that
  *became* at-risk — fires when **any** of: `At_Risk__c == true`, **or** `Status == 'Cannot Complete'`,
  **or** (if FSL present, Q1) `FSL__InJeopardy__c == true`. Only on the transition (new & not old), so
  re-saves don't double-fire. Passes the Ids to:
- **`FieldFlowAtRisk.cls`** `@future(callout=true) notify(Set<Id>)`: SOQL the appointments (number,
  parent WorkOrder, reason, delay), build the JSON our mapper expects, `HttpRequest` POST to
  `callout:FieldFlow/webhooks/sf/at-risk`. `eventId = appointmentId + '-' + SystemModstamp` so a given
  at-risk transition is idempotent end-to-end.
- **`FieldFlowAtRiskTest.cls`** — required for deploy (Apex needs test coverage); asserts the callout
  body shape with an `HttpCalloutMock`.

**Orchestrator (`apps/orchestrator/`):**
- **`POST /webhooks/sf/at-risk`** in `app/webhooks/routes.py`: check `X-FieldFlow-Secret` against
  `settings.sf_hook_secret` (401 on miss), `platform_event_to_at_risk(payload)` (exists), then
  `broker.publish(ev.event, ev.model_dump())` — the exact path `/sim/appointment-at-risk` uses. ~20 lines.
- **`SF_HOOK_SECRET`** added to `config.py` + `.env.example`.
- Test `tests/test_sf_hook.py`: secret-gate + maps + publishes (fake broker). Offline, in CI.

**Deploy tooling:**
- **`apps/salesforce-apex/deploy_apex.py`** — Tooling API deploy using the `SF_*` client-credentials.
  Creates new classes/triggers via `POST /tooling/sobjects/ApexClass|ApexTrigger`; updates existing
  ones via the `MetadataContainer` → `ContainerAsyncRequest` compile-and-poll flow. One command does
  the trigger + both classes. (This also documents the Tooling API for future SF code.)

### Phase 2 — rich RCS messages (per-case primitive sets)

- **Extend the `Card` contract** (`packages/contract`): add an AI-written `body` string and a list of
  declarative `actions` (`view` / `calendar` / `dial` / `share_location` / `open_url`), plus a
  `requests` concept for inbound (share-location, photo). Keep `options` (slots) as-is.
- **Surface the LLM text we already generate** as the empathetic, reason-aware card body (today it's
  only in the trace, hidden from the customer).
- **Per-archetype message sets** (driven by the seeded reason/warranty data):
  - *delay* → appointment card (View, Add to Calendar, **Share Location**, Dial) + slot carousel.
  - *parts* → **photo request** card → quote card → **Pay** (Open-URL webview) → confirmation
    (Dial, Calendar) → **PDF** service-report card.
  - *complex* → human-approval pause, then a call-back / Dial card.
- **`card_to_rcs`** (`app/tools/vonage.py`): map each action/request to its real Vonage RCS suggested
  action / suggestion. Capability-check before exotic primitives (SRS risk R6).
- **Panel**: render the new card kinds richly so the demo looks complete even offline.
- **Scope honesty (Q2):** share-location ETA, photo OCR/vision and PDF bytes are *simulated compute*
  for the POC — the primitive is real and interactive, the heavy pipeline behind it is stubbed and
  labelled as such in the decision trace.

### Rejected alternatives
- *Record-triggered Flow instead of Apex trigger* — you said all code in Apex.
- *gRPC Pub/Sub trigger (build-step-9c stub)* — heavier deps, needs full org provisioning; the HTTP
  callout gets the same result for the demo with a fraction of the moving parts.
- *Fully wiring OCR/ETA/PDF* — large, off the hero story; simulated-but-labelled is the POC-right call.

## 5. Tasks

- [x] Q1–Q3 answered.
- [x] Orchestrator `/webhooks/sf/at-risk` + `SF_HOOK_SECRET` + test (4 green; full suite 103).
- [x] `deploy_sf.py` Tooling API script (Apex create + update-via-MetadataContainer + `--fields`; self-check green).
- [ ] `deploy_sf.py --fields` creates the 3 ServiceAppointment fields; create the `FieldFlow` Named Credential.
- [x] `ServiceAppointmentAtRisk.trigger` + `FieldFlowAtRisk.cls` + test written + **deployed to the org
  2026-10-13** (all 3 compiled via Tooling API → the 3 custom fields confirmed present).
- [x] Push orchestrator so Render serves `/webhooks/sf/at-risk` (live 2026-10-13); `FieldFlow` Named
  Credential created with the `X-FieldFlow-Secret` header; `SF_HOOK_SECRET` set on Render (secret path
  live, not blank).
- [x] **Live fire 2026-10-13** — ticked `At_Risk__c` in the org → trigger → `@future` callout →
  `/webhooks/sf/at-risk` → graph → **real RCS carousel on the phone** → tapped a slot → case **CLOSED**.
  Phase 1 proven end-to-end against the real org. (Field visibility needed Field-Level Security, not
  just the page layout; the trigger fires only on a false→true transition.)
**Phase 2 — rich RCS messages (sliced):**
- [x] **Slice 1 — AI customer message (the RCS body).** `Card.body` added (contract + schema + TS
  regen); proposer now writes a warm, reason-aware `customer_message` (LLM prompt + schema +
  `customer_message_for` deterministic floor + parse fallback); threaded graph
  `generate_options → customerMessage → offer_to_customer` onto `card.body`; real `send_card` leads
  with an RCS text (the body) then the carousel; panel `RcsCardPreview` renders the body under a new
  title. Backend 106 tests green (+3), ruff clean; panel tsc+vite build green. (2026-10-13)
- [x] **Slice 2 — suggested action chips on the offer.** `CardAction` model (type/label/value) +
  `Card.actions` (contract + schema + TS regen); `_offer_actions(context)` attaches **Share Location**
  + **Dial technician** (tech phone, else Call support) to every archetype's offer carousel;
  `actions_to_suggestions()` maps them to real RCS suggestion chips on the leading text message;
  FakeSalesforce technician got a `phone`; panel renders the chips with icons. Backend 107 tests
  green (+1), ruff clean; panel build green. (2026-10-13) NOTE: **Calendar + View belong on a
  *post-choice* confirmation card** (putting them on a pre-choice offer is wrong and would break the
  e2e card asserts) → moved to slice 3 with the confirmation message.
- [x] **Slice 3 — confirmation card + per-archetype ends.** `verify` now sends a `kind="confirmation"`
  card with an **archetype-aware body** (`_confirmation_body`: part-fit / specialist / simple
  reschedule) and **Add to Calendar** + one-tap **Call** actions (`_confirmation_actions`); the chosen
  slot is threaded via `chosenSlot`. Open-URL is already shown by the payment card, so no stand-in
  "View". Panel renders the confirmation (body + chips, no slots). Each archetype now has a distinct
  start (slice 1 body) and end (this). Happy-path test asserts the confirmation + its actions.
  Backend 107 green, ruff clean; panel build green. (2026-10-13)
- [x] **Slice 4 — panel rendering** folded into slices 1–3: `RcsCardPreview` renders body, action
  chips (icons), and the confirmation kind. Further visual polish optional.
- [x] **Slice 5 — photo request + inbound image (parts).** Parts offers get a "Send a photo of the
  label" chip; `case_service.record_photo` runs **simulated OCR** (= the asset's model, matched vs
  Salesforce) and writes `photoVerified` onto the decision trace; `/sim/photo` is the offline twin;
  panel `DecisionTrace` shows it. (2026-10-13) *(Real inbound-image webhook needs a device→case map —
  deferred; `/sim/photo` is the demo trigger.)*
- [x] **Slice 6 — service-report PDF (confirmation).** `verify` attaches a **Service report (PDF)**
  open-URL action to the confirmation + a `serviceReport` note on the trace (SRS FR-13b); panel renders
  a PDF link. URL is a single POC placeholder (a real per-case PDF is the gated step). (2026-10-13)
  Backend 108 tests green (+1), ruff clean; panel build green. Playbook §3g-c added.
- [ ] Update `playbook.md` rich-message how-to once the slices settle.

## 6. Updates

- **2026-10-12** — Spec created after the 4 scoping answers. Research done: real FS jeopardy fields
  (`FSL__InJeopardy__c` + `FSL__InJeopardyReason__c`, reasons Delayed Start/Finish, Due Date
  Approaching, No Response, Rejected by Contractor) and the SRS §7 RCS primitive list captured.
- **2026-10-13** — **Rich-RCS live-fire bugs fixed (first real SF-triggered send).** Ticking
  `At_Risk__c` fired the whole pipeline correctly (trigger → `/webhooks/sf/at-risk` → queue → graph);
  only the real Vonage send failed, so the case landed `FAILED`. Three fixes, all in one change:
  (A) the rich **action chips** were sent as `type:"action"` (+ a `share_location:true` flag) → Vonage
  422 "Invalid suggestion `action`" (#1020). `actions_to_suggestions` now emits only Vonage's valid
  flat chip types — `reply`/`dial`/`open_url`/`share_location` — per the RCS Suggestion Chips docs;
  `dial` is cleaned to **E.164** (`_e164`) + a required `fallback_url`; calendar/photo have no
  POC-formable flat chip so they stay panel-only. (A2) the **payment** card chip had the same
  `type:"action"` bug → now `open_url`. (B) `/webhooks/status` assumed `to` was `{"number":…}` but RCS
  sends a bare string → 500 retry loop; `status_recipient()` now accepts either. Suite **109 green**
  (+1), ruff clean. Playbook §3e live-fire table updated. Next: user redeploys Render + re-fires.
- **2026-10-12** — **Phase 1 steps 1–2 shipped.** (1) `POST /webhooks/sf/at-risk` added to
  `app/webhooks/routes.py` (reuses the existing `/webhooks` router + the tested
  `platform_event_to_at_risk` + the broker) with `SF_HOOK_SECRET` gate; `tests/test_sf_hook.py` 4
  green, full suite 103, ruff clean. (2) `apps/salesforce-apex/deploy_sf.py` — stdlib Tooling API
  deployer (Apex create, update via MetadataContainer compile-poll, `--fields`, `--self-check`);
  self-check green. Playbook §3g-b added. Endpoint path is `/webhooks/sf/at-risk` (not `/hooks`) —
  lazy reuse of the webhooks router. Next: step 3 (fields + Named Credential + trigger/classes).

- **2026-10-13 (later)** — **First end-to-end SF → RCS debug: isolated the chain hop by hop, fixed
  the data + a robustness bug.** Ticking `At_Risk__c` was producing no RCS. Walked the 7 hops using
  the `@future`'s own async Apex debug line (`FieldFlow at-risk <num> -> <code> <body>`):
  - **401 `bad secret`** → the `FieldFlow` Named Credential is **legacy** (no Custom Headers section),
    so it sent no `X-FieldFlow-Secret` at all. POC decision (user, 2026-10-13): **blank `SF_HOOK_SECRET`
    on Render** to unblock; the secret gate is restored later via a new-style NC + External Credential
    (debt).
  - **200 `published:true`** but the case went **FAILED** → the real Salesforce REST reads worked
    (appointment/customer/asset all 200), but the ticked appointment (`SA-0021`) was a **stray,
    hand-made record with no AssignedResource** → `resourceId: null` → `get_technician(None)` 404 →
    `load_context` stored `context["technician"] = None` → the proposer's `context.get("technician",
    {}).get(...)` crashed on the None (the `{}` default never fires when the key exists) → DLQ.
  - **Root-cause fix (robustness):** `load_context` now coalesces a missing customer/asset/technician
    to `{}` ([app/graph/build.py]) — a sparse real-org record degrades (card falls back to "Call
    support") instead of hard-crashing the whole pipeline into the DLQ. Test
    `test_missing_technician_still_sends_options` (suite 117 green, ruff clean).
  - **Clean-slate tooling (user chose "reseed real data everywhere"):** `apps/orchestrator/scripts/
    reset_state.py` wipes the orchestrator's case history + paused checkpoints + purges the DLQ,
    **keeping `app_secrets`** (the SF copilot token). Dry-run by default; `--yes` applies. Verified
    against live Supabase + CloudAMQP (found 28 cases + 19 parked DLQ msgs). The full clean+reseed
    order (SF `seed_demo_data.py --clean`+reseed → e-com `pnpm seed` → `reset_state.py`) is in
    **playbook §3l**, with the gotcha that `--clean` won't remove untagged strays like `SA-0021`
    (delete by hand). Next: user runs the reseed + ticks a FIRE-MENU appointment for the first clean
    SF → RCS card.

- **2026-10-13 (reseed + verify done).** Ran the full clean+reseed: SF `--clean` + reseed (28
  appointments `SA-0031..SA-0058`), e-com `pnpm seed` (86 parts), orchestrator `reset_state.py --yes`
  (cleared 28 cases + 683 checkpoint rows + 19 DLQ msgs). **`seed_demo_data.py` needed three fixes for
  this org's Field Service validation:** (1) can't CREATE a ServiceAppointment in Scheduled status →
  create in default (no status); (2) assigning a resource needs the SA scheduled → set
  SchedStart/EndTime in a separate update, staggered 3h/case; (3) assignment still needs a
  ServiceTerritoryMember, which this org lacks → **best-effort assign, skip on failure** (appointments
  still created; cards fall back to "Call support" via the new guard). **Verified live** by firing
  `/sim/appointment-at-risk` for `SA-0033` on Render → `OPTIONS_SENT`, real customer (Imran Khan) +
  asset (WA-220) read from the org, groq proposer (conf 0.97), carousel sent. The SF→RCS pipeline is
  unblocked; the only gap is named-tech cards (needs FS territory setup).

## 7. Explanation

*(Added when the work lands — the plain-English walkthrough.)*
