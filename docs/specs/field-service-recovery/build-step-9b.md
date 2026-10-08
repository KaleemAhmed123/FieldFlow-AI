# Build Step 9b — Real Vonage RCS: real send + **real inbound/status webhooks**

**Status:** Steps 1-2 **BUILT + offline-tested** 2026-10-08 (real `VonageMessagesClient` + `build_vonage`
+ `card_to_rcs` + `/webhooks/inbound` + `/webhooks/status`; **65 pytest green**, ruff clean, import OK).
Only the one live send to a real Android (step 3) is gated on creds + your go. ·
**Created:** 2026-10-08 · **Last updated:** 2026-10-08

> Swap `FakeVonage` for the **real Vonage Messages API** over **RCS** — real outbound cards **and
> real inbound/status webhooks**. Part of build order #9 ([`scaffold.md`](scaffold.md) §6). Vonage
> access + **$100 credit** received 2026-10-08; the Vonage side is set up (agent/sender provisioned).

## IMPORTANT — the webhook decision, corrected

The earlier "no webhooks in the POC" rule was **Razorpay-specific** (Razorpay stays a `/sim/payment`
**poll**). **Vonage webhooks ARE built here** — real **inbound message** (the customer's tap) and
real **message status** (delivered / read / failed) callbacks. That robustness is deliberate: it is
part of what makes the demo credible to partners. `/sim/*` stays as the **offline/test** path (fakes,
no device); the webhooks are the **real** path. Both drive the same `resume_case`.

## The one rule (unchanged)

Swapping `FakeVonage` → real Vonage changes **one wiring line** (`build_graph(..., vonage=...)` /
`app.state.vonage`). The graph, policy, tools, decision trace and every offline test don't change;
`FakeVonage` stays the default when no Vonage creds are set, so the suite stays offline.

## 1. Task

- **Name:** Real Vonage RCS adapter (send) + inbound & status webhook endpoints (receive), mock-first.
- **"Done" looks like:**
  - A `VonageClient` implementation that sends our `Card` as a **real RCS carousel / card** via the
    Messages API; `FakeVonage` stays the default (blank creds → fake, offline).
  - **`POST /webhooks/inbound`** — a real customer tap (RCS suggested-reply `postback_data`) resumes
    the paused case (the real counterpart of `/sim/customer-reply`).
  - **`POST /webhooks/status`** — delivered / read / failed callbacks recorded on the case (and the
    hook the RCS→SMS fallback will use in Step 7).
  - **Robustness:** Vonage **webhook signature verified** (JWT), inbound **idempotency** by
    `message_uuid` (like event dedup), handlers return **200** fast.
  - One real card sent to a **test Android device**, the real tap flowing back through the webhook to
    close the case. `/sim/*` still works for offline demos. All 58 tests stay green on `FakeVonage`.

## 2. What you asked for

- "I want things real here for Vonage" — real **send and receive**. "Keep this vonage webhook thing,
  it must be there to make the flow robust and impress the partners." The person on the Vonage side
  has set things up. Creds (API key + secret, application id, RCS agent/sender id, test Android
  number) "will be added soon."

## 3. Open questions (recommendations — the new chat confirms, then builds)

**OQ1 — RCS layout for the reschedule options.** *Rec:* a **carousel** (one card per slot: title =
label, text = technician + note), each with a **suggested_reply** whose `postback_data = "<slotId>|
<version>"`. Mirrors today's carousel and carries the version for the stale-reply guard (NFR-6).
*Alt:* one card with up to 4 suggested-reply buttons (simpler, less rich).

**OQ2 — public URL for webhooks in dev.** *Rec:* an **ngrok** (or Vonage dev) tunnel to
`localhost:8000`; set the two webhook URLs on the Vonage **Application**. Prod = the deployed URL.
This is a your-side action item (below). *Alt:* deploy somewhere public first.

**OQ3 — keep `/sim/*` alongside the real webhooks?** *Rec:* **yes.** `/sim/customer-reply` +
`/sim/payment` stay for offline tests/demos without a device; `/webhooks/inbound` is the real path.
Both call the same `resume_case`, so there's one code path to trust.

**OQ4 — what does the status webhook do now?** *Rec:* **record** delivered/read/failed on the case +
trace. The RCS→SMS **fallback** on a failed/undelivered card is **Step 7** (the failure demo) — the
status webhook lands now so Step 7 just consumes it. *Don't* pull the fallback forward.

**OQ5 — security + robustness (non-negotiable for "robust").** *Rec:* verify the Vonage webhook
**JWT signature** on every callback; **dedup inbound by `message_uuid`** (reuse the `IdempotencyKey`
table); return **200** immediately; log + drop anything unverified. The "Approve & Pay" card uses a
**suggested_action / open-url** to the Razorpay `short_url`.

## 4. Plan

### 4.1 Flow (real path; /sim stays as the offline twin)

```
offer_to_customer ─ real RCS carousel sent via Vonage Messages API (channel=rcs, message_type=card/
                    carousel; each slot a suggested_reply, postback_data="slotId|version")
      │  customer taps a slot on their Android (Google Messages)
      ▼
POST /webhooks/inbound ─ verify JWT · dedup message_uuid · parse postback_data → {slotId, version}
      │                   → case_service.resume_case(correlationId, {slotId, version}, idempotency_key=message_uuid)
      ▼
(existing graph) execute → … → offer_payment (RCS "Approve & Pay" card, open-url = Razorpay short_url)
      │
POST /webhooks/status ─ delivered/read/failed → record on the case + trace (Step-7 SMS fallback hook)
```

### 4.2 Files to touch

- **`app/tools/vonage.py`** — add `VonageMessagesClient(VonageClient)`: builds the RCS payload from
  our `Card` (carousel for options; a card + open-url suggested_action for the payment card) and
  POSTs to the Messages API (JWT auth from the application id + private key). Lazy SDK/HTTP import;
  `FakeVonage` unchanged. A `build_vonage(settings)` factory (fake unless creds set), like
  `build_gateway`.
- **`app/webhooks/routes.py`** (new) — `POST /webhooks/inbound` + `POST /webhooks/status`: JWT verify,
  `message_uuid` dedup, map inbound `postback_data` → `resume_case`, record status on the case.
- **`app/config.py` + `.env.example`** — `VONAGE_API_KEY`, `VONAGE_API_SECRET`, `VONAGE_APPLICATION_ID`,
  `VONAGE_PRIVATE_KEY` (path/contents), `VONAGE_RCS_SENDER` (agent id), `VONAGE_WEBHOOK_*` as needed.
- **`app/main.py`** — `app.state.vonage = build_vonage(settings)`; include the webhooks router.
- **`app/services/case_service.py`** — small helper to record a delivery-status update on a case
  (reuse the audit trail). Inbound reuses `resume_case(..., idempotency_key=message_uuid)`.
- **`packages/contract`** — the RCS payload mapping stays internal to the Vonage client; `Card` is
  unchanged (it already has `payUrl` for the open-url action).
- **tests** — unit-test the `Card → RCS payload` mapping (carousel + open-url) with the HTTP client
  mocked; unit-test the inbound webhook (postback parse + dedup + resume) and the status webhook with
  a **signed fixture**; `build_vonage` fake-vs-real. The 58 stay green on `FakeVonage`.
- **playbook.md** — the real-send demo (tunnel, set webhooks, send to the test device, tap, status),
  the $100 spend rule, and how signature verify / dedup work.

### 4.3 Build order (gated on creds + go)

1. `VonageMessagesClient` + `build_vonage` factory + the `Card → RCS` payload mapping (+ unit test,
   HTTP mocked). Fake unchanged, 58 green.
2. `/webhooks/inbound` + `/webhooks/status` (JWT verify, `message_uuid` dedup, resume/record) + unit
   tests with signed fixtures. 58 + new green, ruff clean, import OK.
3. **(GATED — creds + your go + a test device)** tunnel up, webhooks set on the Vonage Application,
   send one real RCS carousel to the Android device, tap a slot → webhook → case advances; then the
   real "Approve & Pay" card → (Razorpay still /sim or live) → close. Watch status callbacks.
4. playbook + this file's Explanation; (gated) context note that Vonage is real.

### 4.4 RCS reference (verified 2026-10-08 against Vonage docs)

- **Send** (Messages API): `channel:"rcs"`, `message_type:"card"` (or carousel), `card:{title (≤200),
  text (≤2000), media_url, suggestions:[{type:"suggested_reply"|"suggested_action", text,
  postback_data}]}` — **max 4 suggestions** per card. `from` = the RCS agent/sender id; `to` = E.164.
- **Receive:** configure **two** webhooks on the Vonage **Application** — **Inbound Message** and
  **Message Status**; handlers must return **200**; signatures are JWT-verifiable. Dev needs a public
  URL (ngrok). India = **transactional** agent, **Android + Google Messages only**.

### 4.5 Your action items (surfaced early)

- **Add the creds to `.env`:** `VONAGE_API_KEY`, `VONAGE_API_SECRET`, `VONAGE_APPLICATION_ID`, the
  **private key** file, `VONAGE_RCS_SENDER` (agent id). ("Will be added soon.")
- **A public tunnel** (ngrok) to `localhost:8000`, and set the two webhook URLs on the Vonage
  Application (a junior can do the ngrok + dashboard wiring).
- **A test Android phone** with Google Messages + RCS, on an India number the agent can reach.
- **$100 rule:** sandbox / one test number, one send per manual demo, never in a loop or a test run.

### 4.6 Alternatives rejected

- **No inbound webhook (/sim only) for Vonage** — you explicitly want it real + robust. (Razorpay
  stays /sim poll; the two channels differ by design.)
- **Replacing `/sim/*`** — kept as the offline twin so tests/CI need no device or tunnel.
- **Pulling the RCS→SMS fallback into 9b** — that's Step 7; 9b just lands the status webhook it needs.

## 5. Tasks

- [x] 1. `VonageMessagesClient` + `build_vonage` + `Card→RCS` mapping (+ unit tests); **65 green**.
- [x] 2. `/webhooks/inbound` + `/webhooks/status` (stdlib HS256 verify, `message_uuid` dedup,
  resume/record) + signed-fixture tests. ruff clean, import OK.
- [ ] 3. **(GATED — creds + go + device)** one real RCS send + real tap via webhook + status callbacks.
- [x] 4. playbook §3e + this Explanation (steps 1-2). Live-fire bits + context note stay for step 3.

## 6. Updates

- **2026-10-08** — Plan created. **Webhook decision corrected:** the no-webhook rule was Razorpay-only;
  **Vonage gets real inbound + status webhooks** (user: "keep the vonage webhook thing, it must be
  there... impress the partners"). Real **send + receive**. RCS send/webhook shapes verified against
  Vonage docs (card/carousel + ≤4 suggestions; Inbound + Status webhooks, JWT-verifiable, return 200).
  `/sim/*` kept as the offline twin. **No code — waiting on Vonage creds + the go** (new chat builds it).

- **2026-10-08 (steps 1-2 built, offline)** — User approved all OQs (OQ1 carousel, OQ3 keep /sim,
  OQ4 status records only, OQ5 verify+dedup+200) and the two refinements:
  1. **OQ1 refined → `postback_data = "correlationId|slotId|version"`.** The written plan's
     `"slotId|version"` had no case id; a real inbound webhook carries no correlationId, so the case
     id is now embedded in the button data and parsed back out. No phone-number lookup.
  2. **OQ5 refined → stdlib HS256, no new dep.** Vonage signs webhooks HMAC-SHA256 with the account
     signature secret (confirmed against Vonage docs). Verified with `hmac`/`hashlib`/`base64` — no
     PyJWT. Keeps CI dependency-free, matching the Razorpay/LLM pattern.
  3. **Send auth → Basic (api_key:api_secret), not JWT.** Lazier and removes the private-key
     requirement from our code entirely; the application id + private key stay on the Vonage side
     (agent + webhook config). `httpx` is lazy-imported, added as a runtime dep only at the live fire.
  4. **Safe arming guard.** `build_vonage` returns the real client ONLY when key+secret+agent_id AND
     `VONAGE_TEST_TO` are all set — so real keys can live in `.env` during offline dev without a
     billed send firing; you arm it deliberately by setting the test recipient before a demo.
  Result: **65 pytest green** (58 + 7 new), ruff clean, `import app.main` OK. All offline on
  FakeVonage. Only the one real device send (step 3) remains gated.

- **2026-10-08 (live fire DEFERRED — tracked debt)** — The webhook/tunnel setup can't be done yet
  (no ngrok + dashboard access this session), so **task 3 (the one real device send) is left as
  debt** — explicitly, not forgotten. Nothing offline depends on it; the code path is built, armed
  behind `VONAGE_TEST_TO`, and fully unit-tested. **To clear the debt:** do the playbook §3e setup
  (ngrok + the 2 webhook URLs + `VONAGE_SIGNATURE_SECRET`), set `VONAGE_TEST_TO`, `uv add httpx`,
  fire one at-risk event, tap the slot on the Android. Build continued to **Step 7** meanwhile.

## 7. Explanation (steps 1-2 — built offline; the live device send still gated)

### 1. What changed
Two real Vonage pieces now exist behind the unchanged seam:
- **Send** — a real `VonageMessagesClient` that turns our `Card` into a Vonage Messages API **RCS
  carousel** (one card per slot) or a **payment card** (an "Approve & Pay" open-url to Razorpay), and
  POSTs it. `build_vonage(settings)` picks it over `FakeVonage` only when the send is fully *armed*.
- **Receive** — `POST /webhooks/inbound` (the customer's tap) and `POST /webhooks/status`
  (delivered/read/failed), with the Vonage JWT signature verified, inbound deduped by `message_uuid`,
  and both returning 200 fast.

The whole suite still runs on `FakeVonage` (65 green). Only the one real send to a device is gated.

### 2. Why it was needed
Step 6 and earlier used `FakeVonage` — it recorded the card but sent nothing. To make the customer
channel real (and robust enough to show partners) we needed a true RCS send **and** a real return
path for the tap, without breaking the offline test suite or the "AI proposes, policy decides" core.

### 3. How it works, step by step
1. The graph's `offer_to_customer` builds the carousel `Card` (now carrying its `version`) and calls
   `vonage.send_card(correlationId, card)` — exactly as before.
2. The real client's `card_to_rcs` maps it to the RCS payload. Each slot button gets a hidden
   `postback_data = "correlationId|slotId|version"`; the payment card gets a `suggested_action`
   open-url to the Razorpay short link. The client POSTs with **Basic auth** to the Messages API.
3. The customer taps a slot on their Android. Vonage POSTs `/webhooks/inbound` with a JWT in the
   `Authorization` header and `reply.id` = our postback string.
4. `verify_vonage_jwt` recomputes the HMAC-SHA256 over the token and checks the `payload_hash` claim
   against the body (stdlib only). Unverified → logged and dropped, still 200.
5. `parse_postback` splits the string back into `{correlationId, slotId, version}`; the handler calls
   the **same** `case_service.resume_case` that `/sim/customer-reply` uses, keyed by `message_uuid`
   so a Vonage retry can't double-resume. The case advances exactly as in the offline flow.
6. `/webhooks/status` verifies the same way and calls `record_delivery_status`, which best-effort maps
   the `message_uuid` back to its case and appends a `delivery_status` audit row (Step 7 consumes it).

### 4. Files / functions changed
- **`app/tools/vonage.py`**: added `card_to_rcs` (Card → RCS payload, ≤4 suggestions, postback /
  open-url), `VonageMessagesClient` (Basic-auth send, lazy `httpx`), `build_vonage(settings)` (the
  armed-or-fake factory). `FakeVonage` unchanged.
- **`app/webhooks/routes.py`** (new): `verify_vonage_jwt`, `parse_postback`, `POST /webhooks/inbound`,
  `POST /webhooks/status`. **`app/webhooks/__init__.py`** exports the router.
- **`app/services/case_service.py`**: added `record_delivery_status` (maps message_uuid → case,
  writes the audit row).
- **`app/main.py`**: `app.state.vonage = build_vonage(settings)` (the one swap line) + include the
  webhooks router.
- **`packages/contract/.../types.py`**: `Card.version` (default 0) so the carousel can stamp the
  offer version into the postback. **`app/graph/build.py`**: `offer_to_customer` sets `version` on
  the card.
- **`app/config.py` + `.env.example`**: the `VONAGE_*` settings (key/secret/application_id/agent_id/
  test_to/signature_secret/messages_url).
- **`tests/test_vonage.py`** (new, 7 tests): mapping, arming, JWT verify, postback parse, the
  send→tap→resume round-trip + dedup, and the status audit row.
- **`playbook.md`**: §3e (secrets, arming, ngrok + webhook setup, the gated live demo), plus §4/§5/§6.

### 5. Important decisions
- **Postback carries the correlationId** (not just slot|version) — the real webhook has no case id
  otherwise. Self-contained, no lookup. *(Refines OQ1.)*
- **Signature verified with stdlib HS256** — Vonage uses HMAC-SHA256; no PyJWT, CI stays dep-free.
  *(Refines OQ5.)* Rejected: adding PyJWT/cryptography.
- **Basic-auth send** — removes the private key from our code; lazier than generating RS256 JWTs.
  Rejected: JWT/application-key auth (kept as the fallback if an account requires it).
- **Armed-or-fake guard** — real send needs `VONAGE_TEST_TO` set too, so billed sends can't fire by
  accident while keys sit in `.env`. Rejected: real-on-any-key (would fire on boot during dev).
- **Seam unchanged** — `send_card(to, card)` kept; `to` is the correlationId at the call site and the
  real client sends to the configured device. True "one wiring line" swap.

### 6. Tests / verification
- `cd apps/orchestrator && uv run pytest -q` → **65 passed** (58 prior + 7 new).
- `uv run ruff check .` → **All checks passed!**  ·  `uv run python -c "import app.main"` → OK.
- All offline: `FakeVonage`, no creds, no network. The signed-fixture test proves verify accepts a
  valid token and rejects a wrong secret / tampered body / blank-secret-skip / malformed token.

### 7. Edge cases and limitations
- **The live device send (step 3) is NOT done** (gated): no real RCS carousel sent, no real tap, no
  real status callback exercised; `httpx` not yet added as a runtime dep.
- **The exact RCS wire shape** (`message_type` card/carousel + suggestions) follows Vonage's docs but
  is re-confirmed at the live fire — `card_to_rcs` is the one spot likely to need a small tweak.
- **`record_delivery_status` scans cases** to map `message_uuid` → case (POC-scale; a `sent_messages`
  index if volume grows). Status callbacks are not deduped (append-only log, harmless).
- **Blank `VONAGE_SIGNATURE_SECRET` disables the signature check** (dev convenience) — set it before
  exposing the ngrok tunnel.
- **One test device only** — the real client sends to `VONAGE_TEST_TO`, not a per-customer number
  (no real customer data in the POC).
