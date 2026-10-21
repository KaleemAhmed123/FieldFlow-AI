# Real availability slots (technician scheduling)

## 1. Task
- **Name:** Real availability slots — offer the customer genuine bookable times from Salesforce Field Service, not canned ones.
- **Status:** Planning (spec written, awaiting go)
- **Started:** 2026-10-21
- **Last updated:** 2026-10-21

## 2. What you asked for
- Stop offering **two random/canned slots**. Offer **real openings** that respect the technician's
  calendar, skills, territory and operating hours.
- Build it **properly — production-grade, not POC-throwaway.** This feature is going beyond the POC.
- Keep a clean split: the Salesforce/MCP work is the user's; the orchestrator wiring is Claude's.
- Get it done **as fast as cleanly possible** — give the user clear numbered steps.

## 3. Open questions (each with a recommended answer)
1. **Which scheduling API?**
   - **Recommend: Field Service managed-package Apex `FSL.AppointmentBookingService.GetSlots`.** The
     org already uses Field Service objects (ServiceAppointment, ServiceResource, ServiceTerritory,
     AssignedResource, ServiceResourceSkill, ServiceTerritoryMember, OperatingHours — all seeded).
     `GetSlots` returns customer-facing **arrival windows** honouring all of that — exactly what an
     RCS "pick a slot" card wants. (`GetCandidates` returns resource-specific pairs; use only if we
     later want to pin *which* tech.)
   - **User to confirm:** the FSL managed package is installed, and give the **Scheduling Policy id**
     (`FSL__Scheduling_Policy__c`, e.g. the shipped "Customer First") + an **Operating Hours id**.
2. **Slot ⇄ part interaction (the parts archetype).**
   - Today the parts flow offers a part-fit slot **+ a "loaner, no part" fallback**.
   - **Recommend:** offer **2–3 real slots, all for the part-fit repair** (they carry the part), and
     **drop the synthetic loaner**. Simpler and all options are genuinely bookable. Policy still
     strips a slot whose part is out of stock.
3. **What if scheduling returns no slots** (tech fully booked, API error, FSL exception)?
   - **Recommend: graceful fallback to the current canned slots**, and record
     `slotsAuthority: "fallback"` on the decision trace (mirrors the existing `priceAuthority`
     pattern). The demo never dead-ends; the trace shows which authority priced the times. Real
     slots → `slotsAuthority: "scheduler"`.
4. **How many slots to offer?**
   - **Recommend: top 2** by grade (best-fit first). RCS cards stay readable; matches today's count.
5. **Slot contract change** (carry real times on each option)?
   - **Recommend: yes.** Each option gains `start`/`end` (ISO-8601 UTC) + keeps `label` for display.
     `reschedule.confirm` then books the exact times and we **delete the fragile
     "TODAY HH:MM" label-parsing** in `RestSalesforce.reschedule`. Less code, not more.

> Per the explain-and-wait rule: **no code until these are answered.** Recommendations are defaults,
> not decisions.

## 4. Plan

### Architecture (where it plugs in)
```
generate_options (graph)
  └─ scheduling.slots(appointmentId)  ← NEW read tool
        Fake: deterministic canned slots (tests/offline)
        Rest: GET /services/apexrest/fieldflow/slots/{apptId}
                └─ Apex: FSL.AppointmentBookingService.GetSlots(...) → [{start,end,label,grade}]
  └─ real slots feed the proposer (AI keeps: which part, customer_message; times come from SF)
  └─ options now carry start/end + label
policy_validate → offer_to_customer → execute
  └─ reschedule.confirm(appointmentId, slotId, start, end)  ← books exact times, no label parsing
        (fallback: if no real slots, canned slots + slotsAuthority="fallback")
```

### Division of work
**User — Salesforce / ops (org-specific, can't be done from the repo):**
- Confirm FSL package + provide Scheduling Policy id + Operating Hours id.
- Ensure demo appointments have a **ServiceTerritory** + an **arrival window**
  (`EarliestStartTime` / `DueDate`) so `GetSlots` has a window to search.
- Deploy the updated Apex (`deploy_sf.py`), set the two ids as env vars on Render, run the smoke test.
- (Optional) wrap the `slots` endpoint as an MCP tool for the copilot.

**Claude — code (in this repo):**
- Draft the Apex `slots` route in `FieldFlowRest.cls` (user confirms the FSL signature in-org).
- `scheduling.slots` tool (Fake + Rest) in `salesforce.py` + `registry.py`.
- Wire into `generate_options`; add `start`/`end` to options; proposer uses real times.
- `reschedule.confirm` books `start`/`end` directly; keep `label` for the card.
- Fallback + `slotsAuthority` on the trace.
- `config.py` settings: `SF_SCHEDULING_POLICY_ID`, `SF_OPERATING_HOURS_ID`.
- Tests (proposer uses injected slots; reschedule books exact times; fallback path).
- `.env.example` + `playbook.md` updates.

### Files to touch
- `apps/salesforce-apex/FieldFlowRest.cls` — add `slots` route (+ test class).
- `apps/orchestrator/app/tools/salesforce.py` — `get_slots` on Fake + Rest; drop label parsing on reschedule.
- `apps/orchestrator/app/tools/registry.py` — register `scheduling.slots`; reschedule takes start/end.
- `apps/orchestrator/app/graph/build.py` — call slots in `generate_options`; options carry start/end; `slotsAuthority`.
- `apps/orchestrator/app/llm/proposer.py` — seed options from real slots (times), AI keeps part/message.
- `apps/orchestrator/app/config.py` + `.env.example` — two new SF ids.
- tests + `playbook.md`.

### Alternatives rejected
- **Salesforce Scheduler REST `/scheduling/getAppointmentSlots`** — different product; the org is on
  Field Service, so FSL Apex is the native fit (no new product to license/configure).
- **Keep label parsing** — fragile ("TODAY/TOMORROW" only, same-day 2h window). Carrying ISO times is
  the production-correct move.
- **Hard-fail when no slots** — bad demo + bad UX. Fallback-to-canned keeps the pipeline alive and is
  honest (trace says `fallback`).

## 5. Tasks
- [x] OQs 1–5 answered (user).
- [x] User provided Scheduling Policy id (`a0pdM000001SsT7QAK`) + Operating Hours id (`0OHdM000005WIlLWAW`).
- [ ] User confirms FSL package installed (implied by FSL objects; verify on deploy).
- [x] Arrival window baked into the seed (rolling 90-day window) — user re-seeds + confirms territory.
- [x] Apex `slots` route drafted (Claude) → **deploy + smoke-test still pending (user)**.
- [x] `scheduling.slots` tool (Fake + Rest) (Claude).
- [x] `generate_options` wired to real slots; AI keeps part+message, times from SF (Claude).
- [x] `reschedule.confirm` books explicit start/end (label parsing kept as the canned fallback) (Claude).
- [x] Fallback to canned + `slotsAuthority` on the trace (Claude).
- [x] Paging: 2/page + "See other times" (MORE_SLOT) across RCS round-trips (Claude).
- [x] Config + `.env.example` (Claude). **Render env vars still pending (user).**
- [x] Tests green (129) + ruff clean (Claude).
- [x] `playbook.md` (§3i) + this spec's §7 walkthrough (Claude).
- [ ] Live smoke: deploy Apex, set Render ids, fire an appointment, confirm the card shows real times
      + "See other times", book one end-to-end (user + Claude).

## 6. Updates
- 2026-10-21 — Spec written. Awaiting answers to OQs 1–5 and the org-side confirmations before any code.
- 2026-10-21 — **Decisions locked** (all OQs answered):
  - OQ1 API = **FSL `GetSlots`** (pending user org confirmation of package + ids).
  - OQ2 slots = **2 best real slots** + a **"See other times"** button that pages through more real
    openings. We fetch a larger batch (top ~6), show 2 per page, keep the rest in case state; the
    button resumes the case to show the next 2. **Loaner slot dropped.**
  - OQ3 no-slots = **fall back to canned + `slotsAuthority="fallback"`** on the trace.
  - OQ4 page size = **2**; batch fetched = ~6.
  - OQ5 contract = **yes**, options carry ISO `start`/`end`; drop label parsing in reschedule.
  - **New scope from OQ2:** paging. Adds a page index to case state, a "see other times" suggested
    reply + postback, and offer/await_reply handling to advance pages (wrap/stop at the end).
  - Sequencing: build the **orchestrator side + Fake + Apex draft + tests first** (needs no org ids);
    user supplies ids + deploys Apex + sets territory/window in parallel; then live smoke test.

## 7. Explanation

**1. What changed.** The reschedule options the customer sees are now **real bookable times** from
Field Service, not two canned guesses. A new Apex endpoint asks Field Service's own scheduler for
openings; the orchestrator shows 2 per RCS card with a "See other times" pager, and books the exact
instant the customer taps. If the scheduler has nothing (or isn't configured), it falls back to the
old canned slots and says so on the trace.

**2. Why it was needed.** The old slots were invented strings ("TODAY 15:00-17:00") that ignored the
technician's real calendar. Beyond-POC, we need genuine availability so a booked slot is one the tech
can actually keep.

**3. How it works, step by step.**
- Apex `GET /fieldflow/slots/{apptId}?policyId=..&operatingHoursId=..&max=6` calls
  `FSL.AppointmentBookingService.GetSlots` and returns `[{start, end, grade}]` (or `[]`).
- In the graph's `generate_options`, after the AI proposes the fix, `scheduling.slots` fetches those
  real times. The AI's choice of **part + customer message** is kept; each real slot becomes an
  option carrying that part. `slotsAuthority` records `scheduler` (real) or `fallback` (canned).
- `policy_validate` validates the pool once (all slots share the part, so stock/skill apply equally).
- `offer_to_customer` shows `PAGE_SIZE` (2) slots; while more remain it adds a `MORE_SLOT`
  ("See other times") option. A tap on it (`execute`) advances `slotPage` and re-offers (new version).
- Booking a real slot passes its concrete `start`/`end` to `reschedule.confirm`, which the real org
  books directly (no label parsing); canned fallback slots still parse their label to times.

**4. Files / functions changed.**
- `apps/salesforce-apex/FieldFlowRest.cls` — new `slots` route (`getSlots`) over FSL GetSlots.
- `app/tools/salesforce.py` — `get_slots` on the Protocol + Fake (`_slots`) + Rest (query-param GET,
  fails soft to `[]`); `format_slot_label` / `_parse_iso`; `reschedule` accepts explicit start/end.
- `app/tools/registry.py` — registered `scheduling.slots`; `reschedule.confirm` forwards start/end.
- `app/graph/build.py` — real-slot pool + `slotsAuthority`/`slotPage` in `generate_options`; paging in
  `offer_to_customer`; `MORE_SLOT` handling in `execute`; `PAGE_SIZE`/`MORE_SLOT` constants.
- `app/config.py` + `.env.example` — `SF_SCHEDULING_POLICY_ID`, `SF_OPERATING_HOURS_ID`, `SF_SLOTS_MAX`.
- `apps/salesforce-apex/seed_demo_data.py` — rolling 90-day arrival window on every appointment.
- `tests/test_availability_slots.py` — label formatter, paginate-and-book, canned fallback.
- `playbook.md` §3i.

**5. Important decisions.** Used FSL's own scheduler (don't rebuild scheduling). Kept the AI's
part/message, took only the times from SF (keeps "AI proposes, policy decides"). Dropped the synthetic
loaner slot for 2 real slots + a pager. Fallback-to-canned (not hard-fail) so a scheduling hiccup
never dead-ends. Fake `get_slots` returns `[]` by default so all 126 prior tests keep passing.

**6. Tests / verification.** `uv run pytest -q` → **129 passed**; `uv run ruff check app tests` → clean.
New tests cover the label tz conversion, the 4-slot paginate-and-book path, and the canned fallback.
**Not yet verified live** — the Apex endpoint is a draft; needs org deploy + the two ids on Render.

**7. Edge cases and limitations.** `GetSlots` returns time windows, not which resource — the displayed
technician is the AI's proposed one, not per-slot (use `GetCandidates` later to pin a resource). The
`GetSlots` overload is confirmed against the docs but unverified against this org's FSL version. Empty
window (no `EarliestStartTime`/`DueDate`) → `[]` → fallback. `max` caps the batch (6); more openings
beyond that aren't paged. Grade is fetched but not yet surfaced to the customer.
