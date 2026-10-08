# Build Step 7 — the 2 headline failure demos (graceful degradation)

**Status:** BUILT + offline-tested 2026-10-08 (**70 pytest green**, ruff clean, import OK). The
DLQ land+replay over real RabbitMQ is a manual demo (playbook §3f). · **Created:** 2026-10-08 ·
**Last updated:** 2026-10-08

> Build order #7 ([`scaffold.md`](scaffold.md) §6): "The 2 headline failure demos — RCS→SMS
> fallback, Salesforce-down / DLQ." The story both tell: **a dependency breaks and the system
> degrades gracefully instead of dropping the customer.** Mock-first; the offline suite stays green.

## The one rule (unchanged)

Neither demo lets the LLM decide anything new. **7a** is a *transport* reaction (a channel swap) in
the service layer — the graph stays paused, untouched. **7b** is *infrastructure* (a dependency
raises → the message parks in the dead-letter queue → replay on recovery) — the decision core never
runs on bad data. AI proposes, policy decides, tools act; this step is about what happens when the
plumbing fails.

## 1. Task

- **7a — RCS→SMS fallback.** If the RCS card fails to deliver (a `failed`/`undelivered` status
  callback), resend the same slot options as a plain **SMS** so the customer can still reply.
- **7b — Salesforce-down / DLQ.** When Salesforce is down, event processing fails and the message
  lands safely in the **dead-letter queue** (DLQ — a holding queue for messages that couldn't be
  processed). A read-only `/dlq` shows what's parked; `/sim/dlq/replay` requeues it once Salesforce
  is back.
- **"Done" looks like:** both failures are demoable; the offline unit tests prove the fallback
  trigger and the fault path; the DLQ land+replay is a manual demo (needs RabbitMQ).

## 2. What you asked for

- Continue the build; lock Step 7 with all five open questions answered as recommended
  (2026-10-08). Order left to my judgement → **7a first** (reuses the Step-9b status webhook), then
  7b. "At the end we have to implement everything."

## 3. Open questions — ANSWERED 2026-10-08 (locked, build now)

- **OQ1 — fallback trigger (7a):** on `failed`/`undelivered` for a case still awaiting a reply,
  resend options via SMS; handled in the **service layer** (graph untouched); fired offline via the
  existing `/webhooks/status` + a `/sim/delivery-status` twin. **→ yes, as rec.**
- **OQ2 — what the SMS carries (7a):** plain text listing the slots with their ids ("Reply with
  t-1 / t-2 …"); the reply still comes back through the existing reply path. **→ yes, as rec.**
- **OQ3 — "Salesforce down" toggle (7b):** a runtime `/sim/fault` endpoint (no restart). **→ rec.**
- **OQ4 — retries before DLQ (7b):** keep immediate DLQ (one failure → `events.dlq`, already wired);
  timed-retry deferred (needs a delay queue). **→ as rec.**
- **OQ5 — DLQ visibility (7b):** a read-only `/dlq` peek (depth + parked messages) + `/sim/dlq/replay`
  to requeue, so it's visible in the panel. **→ yes, as rec.**

## 4. Plan

### 4.1 Flow

```
7a:  offer_to_customer → RCS card sent
        │  delivery status = failed/undelivered  (real: /webhooks/status · offline: /sim/delivery-status)
        ▼
     record_delivery_status → case still OPTIONS_SENT? → vonage.send_sms(same options as text)
        │  customer replies as usual (slotId) → the paused graph resumes → normal flow

7b:  /sim/fault {salesforceDown:true} → FakeSalesforce reads raise
     /sim/appointment-at-risk → consumer handler raises → broker nacks (no requeue) → events.dlq
     GET /dlq  → {depth, messages}     (read-only peek, messages requeued after peeking)
     /sim/fault {salesforceDown:false} → Salesforce "back up"
     POST /sim/dlq/replay → republish parked messages to the main exchange → processed normally
```

### 4.2 Files to touch

- **`app/tools/vonage.py`** — add `send_sms(to, text)` to the Protocol, `FakeVonage` (records it),
  and `VonageMessagesClient` (channel=sms text, lazy httpx).
- **`app/services/case_service.py`** — `record_delivery_status` gains the `vonage` client + the
  fallback: a failed status on an awaiting case → `send_sms` the options as text + an audit row.
  Add `_options_sms(...)` text builder.
- **`app/webhooks/routes.py`** — `/webhooks/status` passes `app.state.vonage` to the recorder.
- **`app/sim/routes.py`** — `/sim/delivery-status` (offline twin of the status webhook), `/sim/fault`
  (toggle `salesforce.down`), `/sim/dlq/replay` (requeue parked messages).
- **`app/tools/salesforce.py`** — `FakeSalesforce.down` flag; reads raise when set ("Salesforce down").
- **`app/queue/broker.py`** — `dlq_stats()` (depth), `peek_dlq(limit)` (read + requeue), `replay_dlq(limit)`.
- **`app/api/routes.py`** — `GET /dlq` (depth + parked messages, read-only).
- **tests** — `test_failures.py`: SMS fallback fires only on a failed status + awaiting case; a down
  Salesforce makes `handle_event` raise (proving the DLQ path); the toggle flips reads on/off.
- **playbook.md** — §3f: both failure demos end to end.

### 4.3 Build order

1. **7a** — `send_sms` + the fallback in `record_delivery_status` + `/sim/delivery-status` + tests.
2. **7b** — fault toggle + `FakeSalesforce.down` + broker DLQ peek/replay + `/dlq` + `/sim/dlq/replay`
   + tests.
3. playbook §3f + this file's Explanation.

### 4.4 Alternatives rejected

- **Timed retries before DLQ** — needs a RabbitMQ delay/TTL queue; immediate DLQ is honest and wired.
- **Inbound-SMS parsing for the fallback reply** — the existing reply path already carries the
  slotId; the SMS just lists the options. No new parser.
- **A metric counter instead of `/dlq` peek** — less convincing to partners; the peek shows the real
  parked messages.
- **Fallback inside the graph** — it's a transport concern; keeping it in the service layer leaves
  the one rule and the decision core untouched.

## 5. Tasks

- [x] 1. 7a: `send_sms` + `record_delivery_status` fallback + `/sim/delivery-status` + tests.
- [x] 2. 7b: `/sim/fault` + `FakeSalesforce.down` + broker DLQ peek/replay + `/dlq` + `/sim/dlq/replay` + tests.
- [x] 3. playbook §3f + this Explanation.

## 6. Updates

- **2026-10-08** — Plan created; OQ1-OQ5 locked as recommended (user). DLQ topology already exists in
  `broker.py` (queue `events` dead-letters to `events.dlq`), so 7b adds only the fault toggle +
  visibility, not the queue plumbing. Building 7a first.

- **2026-10-08 (built, offline)** — Both demos built mock-first. **70 pytest green** (65 + 5 new),
  ruff clean, import OK. 7a reuses the Step-9b status webhook; 7b reuses the already-wired DLQ
  topology (added only the fault toggle + peek/replay + `/dlq`). The land+replay over real RabbitMQ
  stays a manual demo (needs a broker; offline the broker is `None` → the endpoints say so).

## 7. Explanation (built offline; the DLQ land+replay is a manual RabbitMQ demo)

### 1. What changed
Two failure paths now degrade gracefully instead of dropping the customer:
- **7a RCS→SMS fallback** — a delivery-status callback that says the RCS card did NOT arrive
  (`failed`/`undelivered`/`rejected`), on a case still waiting for the customer's tap, resends the
  same slot options as a plain **SMS**. The customer replies as normal and the flow continues.
- **7b Salesforce-down / DLQ** — a runtime toggle makes Salesforce reads raise; a fired event then
  fails processing and the broker parks it in the **dead-letter queue** (`events.dlq`) instead of
  losing it. A read-only `/dlq` shows what's parked; `/sim/dlq/replay` requeues it after recovery.

### 2. Why it was needed
A credible demo for partners has to show the unhappy paths, not just the golden one: the customer's
phone might not support RCS, and Salesforce (the system of record) will sometimes be unreachable. The
system must keep the customer moving and must never silently drop an event.

### 3. How it works, step by step
**7a:** `offer_to_customer` sends the RCS card (it returns a `messageUuid` on the real path). A later
status callback hits `/webhooks/status` (real) or `/sim/delivery-status` (offline). `record_delivery_status`
maps the `messageUuid` back to its case, writes a `delivery_status` audit row, and — if the status is
a failure AND the case is still `OPTIONS_SENT` — builds a plain-text list of the slots
(`_options_sms`) and calls `vonage.send_sms`, writing an `sms_fallback` audit row and bumping a
counter. The graph is never touched; this is a transport swap in the service layer.

**7b:** `/sim/fault {salesforceDown:true}` sets `FakeSalesforce.down`, so every read raises. A fired
`appointment.at_risk` → the consumer's handler raises → the broker `nack`s it with no requeue → it
dead-letters to `events.dlq` (topology already in `broker.py`). `GET /dlq` passively declares the
queue for its depth and peeks the bodies (get-then-requeue, a read not a drain). After
`/sim/fault {salesforceDown:false}`, `POST /sim/dlq/replay` re-publishes each parked message to the
main exchange (keeping its routing key) and acks it off the DLQ, so it processes normally.

### 4. Files / functions changed
- **`app/tools/vonage.py`**: `send_sms` on the Protocol, `FakeVonage` (records to `.sms`), and
  `VonageMessagesClient` (channel=sms text, lazy httpx).
- **`app/services/case_service.py`**: `record_delivery_status` now takes the `vonage` client and runs
  the fallback; `_options_sms` builds the SMS text; `_FAILED_DELIVERY` is the trigger set.
- **`app/tools/salesforce.py`**: `FakeSalesforce.down` + a `_guard()` that raises on every read.
- **`app/queue/broker.py`**: `dlq_stats` (depth), `peek_dlq` (read + requeue), `replay_dlq` (requeue + ack).
- **`app/api/routes.py`**: `GET /dlq` (depth + parked messages; broker-down → unavailable).
- **`app/sim/routes.py`**: `/sim/delivery-status` (status twin), `/sim/fault` (toggle), `/sim/dlq/replay`.
- **`app/webhooks/routes.py`**: `/webhooks/status` passes `app.state.vonage` to the recorder.
- **`app/telemetry.py`**: `sms_fallbacks` + `dlq_replays` counters.
- **`tests/test_failures.py`** (5 tests): fallback fires only on a failed+awaiting case; delivered →
  no SMS; unknown uuid → records, no SMS; a down Salesforce makes `handle_event` raise with no case
  persisted; the toggle flips reads off and back on. **`tests/test_vonage.py`**: updated the status
  test for the new `vonage` arg.

### 5. Important decisions
- **Fallback in the service layer, not the graph** — it's a transport concern; the decision core and
  the one rule stay untouched.
- **SMS lists slot ids, reply path unchanged** (OQ2) — no inbound-SMS parser; the customer replies
  with the same slotId the existing path already understands.
- **Immediate DLQ, no timed retry** (OQ4) — honest and already wired; timed retries need a delay
  queue the POC doesn't need.
- **`/dlq` peek requeues what it reads** — a peek must not consume; the replay is a separate,
  deliberate action.
- **Runtime fault toggle** (OQ3) — a live demo flips it without a restart.

### 6. Tests / verification
- `cd apps/orchestrator && uv run pytest -q` → **70 passed** (65 prior + 5 new).
- `uv run ruff check .` → **All checks passed!**  ·  `uv run python -c "import app.main"` → OK.
- All offline (fakes, no RabbitMQ, no network).

### 7. Edge cases and limitations
- **The DLQ land+replay is NOT exercised offline** — the broker is `None` without RabbitMQ, so `/dlq`
  and `/sim/dlq/replay` report unavailable; the real land+replay is the manual demo in playbook §3f.
- **Fallback needs the `messageUuid` on the case** — the real send stores it; offline we set it (the
  test does). Without it the status callback can't find the case (records under the uuid, no SMS).
- **One fallback per failed status** — no SMS retry ladder; a repeated failed status would resend
  (idempotency on the SMS is not modelled; fine for the POC).
- **`peek_dlq`/`replay_dlq` are bounded by `limit`** (default 20) — a deep DLQ needs repeated calls.
