# Build Step 9c — the at-risk flow triggered by a real Salesforce event

## 1. Task

- **Name:** Salesforce Pub/Sub trigger — make a recovery case start from a real Salesforce
  **Platform Event**, not from `/sim`.
- **Status:** mock-first **SHIPPED** (seam + mapper + wiring + tests, 78 green); real gRPC
  subscription **gated** on org provisioning.
- **Started:** 2026-10-10 · **Last updated:** 2026-10-10.

## 2. What you asked for

- "Start the Salesforce work first. Make the flow **triggered from SF** so we're one step closer to
  demo."
- Decisions confirmed: **Platform Event via Pub/Sub API** (not CDC); **build mock-first now**, real
  fire gated on the org.

## 3. Open questions

| # | Question | Recommendation | Your answer |
|---|----------|----------------|-------------|
| OQ1 | Platform Event vs Change Data Capture? | **Platform Event `Appointment_At_Risk__e`** — explicit, matches our event shape. | **Platform Event** ✅ |
| OQ2 | Build the subscriber now or wait for the org? | **Mock-first now**, real fire gated. | **Mock-first now** ✅ |
| OQ3 | Reuse Salesforce's event uuid as our idempotency key? | **Yes** — `EventUuid` → `eventId` so a redelivered Pub/Sub event dedupes (NFR-2). | taken (default) |
| OQ4 | Transport: gRPC Pub/Sub API vs the older CometD streaming? | **gRPC Pub/Sub API** (the modern one you chose). CometD is lighter but legacy — noted only. | gRPC |

## 4. Plan

**The lazy insight:** the trigger is just a *source* in front of the existing queue. Today
`/sim/appointment-at-risk` publishes the contract event onto RabbitMQ. A real Salesforce subscriber
publishes **the same event onto the same exchange** — the consumer, graph, policy and RCS downstream
never change. So this step adds one seam, nothing else moves.

**Files touched:**
- `app/events/source.py` (new) — `platform_event_to_at_risk` (pure mapper), `EventSource` protocol,
  `SalesforcePubSubSource` (gated), `build_event_source(settings)`.
- `app/events/__init__.py` (new) — exports.
- `app/config.py` — `SF_LOGIN_URL/SF_CLIENT_ID/SF_CLIENT_SECRET/SF_PUBSUB_TOPIC/SF_PUBSUB_ENDPOINT`
  + the `sf_pubsub_armed` property (the one gate).
- `app/main.py` — start the source as a background task when armed + broker present; stop on
  shutdown. Mirrors `build_vonage` / `build_gateway`.
- `.env.example` — the SF Pub/Sub section.
- `tests/test_event_source.py` (new) — the mapper + the armed/unarmed gate, offline.

**Rejected alternatives:**
- *A `FakeEventSource` that idles* — cut. Unarmed → `build_event_source` returns `None` and `/sim`
  stays the trigger; a do-nothing class would be an abstraction with no caller.
- *Writing the full gRPC/Avro subscriber now* — cut. It can't be built or tested without the
  provisioned org, and the deps are heavy. The reusable core (the mapper) is done; the gRPC body
  lands with the org (same shape as `uv add razorpay` being deferred to the live step).

## 5. Tasks

- [x] `platform_event_to_at_risk` mapper (tolerant of the `__c` suffix; fails loud on missing ids).
- [x] `EventSource` seam + `SalesforcePubSubSource` (gated skeleton) + `build_event_source`.
- [x] Config + `sf_pubsub_armed` gate + `.env.example`.
- [x] Wire into `main.py` lifespan (start/stop the source).
- [x] `tests/test_event_source.py` (6 tests) — 78 green, ruff clean, `import app.main` OK.
- [ ] **Gated (needs the org):** fill `SalesforcePubSubSource.run` with the OAuth + gRPC subscribe,
      add the pubsub deps, one live fire.

## 6. Updates

- **2026-10-10** — Step created and built mock-first. Seam + mapper + wiring + 6 tests; full suite
  78 passed, ruff clean. Real gRPC subscription deferred to the gated live step (needs the org).
  Also recorded **Decision A** (inventory → separate e-com source) across the context docs in the
  same change — the handoff sheet's two `inventory.*` rows are struck (they move to the e-com).

## 7. Explanation (plain English)

1. **What changed.** The system can now be triggered by a real Salesforce event. Today a demo fires
   the at-risk flow by calling `/sim`. This step adds the *real* door: a Salesforce **Platform
   Event** (a custom broadcast message, `Appointment_At_Risk__e`) read over Salesforce's **Pub/Sub
   API** (its event stream). The code for that door is in place and tested offline; the one live
   connection is gated on the Salesforce org existing.
2. **Why it was needed.** For the demo to be credible to partners, the recovery case should start
   from Salesforce itself, the way it would in production — not from a button we press.
3. **How it works, step by step.** Salesforce publishes an `Appointment_At_Risk__e` event → our
   subscriber receives it → `platform_event_to_at_risk` converts the Salesforce payload into our
   standard `appointment.at_risk` event → it's published onto the **same RabbitMQ exchange** `/sim`
   already uses → the existing consumer, LangGraph flow, policy and RCS send run exactly as before.
   The trigger is swapped; nothing downstream is.
4. **Files / functions.** `app/events/source.py`: `platform_event_to_at_risk` (payload → contract
   event, the tested core), `SalesforcePubSubSource` (the real subscriber, gated), and
   `build_event_source` (returns the real source only when the three `SF_*` creds are set, else
   `None` so `/sim` stays the trigger). `app/main.py` starts it as a background task on boot.
5. **Important decisions.** (a) Platform Event over CDC — explicit and matches our event. (b)
   Mock-first — the mapper + seam ship now; the heavy gRPC body waits for the org, because it can't
   be built or tested without one. (c) Reuse Salesforce's own event uuid as our idempotency key, so
   a redelivered event is processed once (NFR-2). (d) A malformed event (missing ids) raises loudly
   rather than mis-routing — the lesson from the Vonage live fire.
6. **Tests / verification.** `uv run pytest -q` → **78 passed** (was 72; +6 here). `uv run ruff
   check .` → clean. `uv run python -c "import app.main"` → OK. The tests prove: the `__c` and
   plain payloads both map, an unknown reason falls back safely, missing ids raise, and the source
   is `None` when unarmed / built when armed.
7. **Edge cases and limitations.** The real gRPC subscription is **not** written yet — arming the
   `SF_*` creds today raises a clear "gated live step" error on boot (by design, so it fails loud,
   not silently). No retry/replay policy on the subscriber yet (the DLQ still protects the
   downstream). The org, the Connected App, and the `Appointment_At_Risk__e` event must exist before
   the live path can run — see [`salesforce-handoff.md`](salesforce-handoff.md).
