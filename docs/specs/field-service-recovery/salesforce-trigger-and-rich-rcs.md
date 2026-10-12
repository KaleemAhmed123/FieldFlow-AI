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
- [ ] Push orchestrator so Render serves `/webhooks/sf/at-risk`; create `FieldFlow` Named Credential.
- [ ] Live fire: tick the field on a seeded appointment → case appears.
- [ ] `Card` contract extension + LLM-body surfacing + `card_to_rcs` mapping + tests.
- [ ] Per-archetype message sets in the graph.
- [ ] Panel rendering of new card kinds.
- [ ] Update `playbook.md` (new §3g trigger + rich-message how-to) in the same change.

## 6. Updates

- **2026-10-12** — Spec created after the 4 scoping answers. Research done: real FS jeopardy fields
  (`FSL__InJeopardy__c` + `FSL__InJeopardyReason__c`, reasons Delayed Start/Finish, Due Date
  Approaching, No Response, Rejected by Contractor) and the SRS §7 RCS primitive list captured.
- **2026-10-12** — **Phase 1 steps 1–2 shipped.** (1) `POST /webhooks/sf/at-risk` added to
  `app/webhooks/routes.py` (reuses the existing `/webhooks` router + the tested
  `platform_event_to_at_risk` + the broker) with `SF_HOOK_SECRET` gate; `tests/test_sf_hook.py` 4
  green, full suite 103, ruff clean. (2) `apps/salesforce-apex/deploy_sf.py` — stdlib Tooling API
  deployer (Apex create, update via MetadataContainer compile-poll, `--fields`, `--self-check`);
  self-check green. Playbook §3g-b added. Endpoint path is `/webhooks/sf/at-risk` (not `/hooks`) —
  lazy reuse of the webhooks router. Next: step 3 (fields + Named Credential + trigger/classes).

## 7. Explanation

*(Added when the work lands — the plain-English walkthrough.)*
