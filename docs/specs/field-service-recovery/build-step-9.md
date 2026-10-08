# Build Step 9 — Swap mocks → real: Razorpay Test-Mode (now) · Vonage + Salesforce MCP (blocked)

**Status:** Razorpay gateway BUILT + offline-tested 2026-10-08 (58 pytest green, ruff clean; the one
live Test-Mode fire + the `razorpay` dep are still gated). Vonage = 9b (next); Salesforce = 9c
([`salesforce-handoff.md`](salesforce-handoff.md)). · **Created:** 2026-10-08 · **Last updated:** 2026-10-08

> Build order #9 ([`scaffold.md`](scaffold.md) §6: "Swap mocks → real Vonage + real Salesforce/MCP").
> We fold the **gated live Razorpay Test-Mode** call (from Step 6) in here too. Reality check: of the
> three real swaps, **only Razorpay is unblocked** — your TEST keys are in `.env`. Real **Vonage**
> (RCS access, risk R1) and real **Salesforce MCP** (a Developer-Edition org + access, risk R3) are
> still blocked on external setup, so this plan builds **Razorpay for real now** and keeps Vonage +
> Salesforce as clearly-scoped later sub-steps.

## Webhook scope (important, corrected 2026-10-08)

The "no webhooks in the POC" rule is **Razorpay-only** — Razorpay payment stays a `/sim/payment`
**poll**. **Vonage gets real inbound + status webhooks** (customer taps + delivery/read), built in
[`build-step-9b.md`](build-step-9b.md); `/sim/*` remains the offline twin for tests/demos. The two
channels differ on purpose: Razorpay confirmation is a poll; Vonage is event-driven and that
robustness is part of the demo.

## The one rule (unchanged)

Swapping a fake for the real thing must change **one wiring line**, nothing else. `FakeRazorpay`
already sits behind the `PaymentGateway` interface; the graph, policy, tools, tests and the
decision trace don't know or care which gateway is live. The real client drops in behind the same
Protocol. Mock-first stays true: with blank keys the fake runs and the whole suite is offline.

## 1. Task

- **Name:** Make the Razorpay payment real (Test-Mode), behind the existing `PaymentGateway` seam —
  **no webhook** (keep the `/sim/payment` step), one gated live payment to prove it end to end.
- **"Done" looks like:**
  - A `RazorpayGateway` implementing `PaymentGateway`, built from `.env` keys; blank keys → `FakeRazorpay`
    (unchanged, offline). One factory line swaps them.
  - A real Razorpay **payment link** is created; the customer pays on the real hosted page with a
    **test card**; the system confirms the payment is really **paid** and closes the case.
  - **No inbound webhook** — payment completion is confirmed by the gateway **polling** Razorpay when
    `/sim/payment` is fired (your POC rule: everything via `/sim`).
  - All 54 tests stay green on the fake. **One gated live run** (your go), like the Step 5 live Groq call.
  - Safety rails so a live call can't surprise-charge: **test-keys-only guard**, tiny amounts, opt-in via keys.
- **Explicitly NOT in this step:** real Vonage, real Salesforce MCP (blocked — see §4.3).

## 2. What you asked for

- "Yes start planning the Step 9." Earlier in Step 6 you approved the gated live Razorpay call,
  copied your **TEST** keys into `apps/orchestrator/.env`, and set the hard rule: **no webhooks in the
  POC — the normal `/sim` flow is fine.** This plan honours all of that.

## 3. Open questions — ANSWERED 2026-10-08 (awaiting the explicit "go build" for the Razorpay code)

**Locked:** OQ2 → **poll Razorpay** (no webhook). OQ3 → **payment link only**. OQ4 → **test-key
guard + opt-in**. OQ1 → **Razorpay only *now*, but both others come back very early:**
- **Vonage is now UNBLOCKED** — you received official Vonage access on 2026-10-08 with **$100 of
  credit** (spend sensibly: sandbox first, minimal real sends, no load loops). Real Vonage becomes
  **Step 9b, near-term** — I'll plan it right after the Razorpay live call.
- **Salesforce:** you have a **Developer-Edition org** (no Field Service experience yet — willing to
  learn). You want a **handoff file** listing exactly what to get done so you can offload to the SF
  dev, and I generate the API/integration code. Created:
  [`salesforce-handoff.md`](salesforce-handoff.md). Real Salesforce MCP (your "Headless 360") becomes
  **Step 9c**, started as soon as the org + data + access are ready.

### The original open questions (kept for the record)

**OQ1 — Scope of "Step 9 now".**
- **Recommendation: Razorpay Test-Mode live ONLY.** It's the one unblocked swap (keys ready). Treat
  real Vonage and real Salesforce MCP as **separate sub-steps (9b, 9c)**, planned at a high level
  here but built only when their external access clears (R1 / R3).
- *Why:* Vonage needs approved RCS agent access; Salesforce MCP needs a Developer-Edition org + an
  integration user. Both are weeks-of-lead-time external dependencies, not code we can finish today.

**OQ2 — How payment completion is confirmed, with no webhook (your POC rule).**
- **Recommendation: poll Razorpay.** When `/sim/payment` is fired, the real gateway calls
  `payment_link.fetch(id)` and we proceed **only if status == "paid"** (Razorpay is the source of
  truth). The caller's `status` field is **ignored for the real gateway** (kept for the fake, so
  offline tests still drive success/failure). No inbound callback.
- *Alternatives (rejected unless you want one):* (a) trust the caller's `status` even when live —
  doesn't actually verify a real payment; (b) accept a real Razorpay webhook + verify its signature
  (`client.utility.verify_payment_link_signature`) — violates the no-webhook POC rule; only if you
  later choose to accept real callbacks.

**OQ3 — Razorpay object: payment link only, or Razorpay order + link?**
- **Recommendation: payment link only.** A Razorpay **Payment Link** is self-contained, shareable
  (its `short_url` is the RCS "Approve & Pay" target) and **auto-captures** on payment. Our internal
  "order" (from `commerce.create_order`) stays our own id in the trace. Fewer API calls, less to break.
- *Alternative:* also create a Razorpay `order` — only needed for the embedded Checkout widget, which
  we don't use. Rejected.

**OQ4 — Live-call safety rails (it hits the real Razorpay API with your keys).**
- **Recommendation: three cheap guards.** (1) refuse unless the key looks like a **test key**
  (`rzp_test_…`) — a live key aborts with a clear error; (2) keep the demo amounts small; (3) the
  real path is opt-in — blank keys = fake, so nothing live runs by accident or in CI.
- *Why:* a POC should make it impossible to accidentally fire a real charge on a live account.

### Defaults I'll take unless you object (named, not blocking)

- **Add `razorpay` as a dep** (like `groq`/`google-genai` were added at their live step), lazy-imported
  in `RazorpayGateway` so offline import stays clean.
- **`capture_payment` becomes "verify + capture"** for the real gateway: it fetches the live link,
  confirms `paid`, and returns the receipt (refuses → `settle_payment` re-offers). The graph stays the
  single decision point; `/sim/payment` keeps just carrying the ids.
- **Refund** uses `client.payment.refund(razorpay_payment_id)` for real; still only exercised offline
  (tool + test), no live refund in this step.
- **Context docs:** after this ships, a one-line update to `context/00` (Razorpay now real in Test-Mode)
  — gated on your yes, as always.

## 4. Plan

### 4.1 The flow (unchanged shape; only the gateway is now real)

```
build_quote → create_payment ─ commerce.create_payment_link ─▶ RazorpayGateway.create_payment_link
                                                                client.payment_link.create({amount,
                                                                currency, description, notes})
                                                                → { id: plink_…, short_url, status }
            → offer_payment  ─ RCS "Approve & Pay ₹X" card, payUrl = the REAL short_url
            → await_payment  ─ interrupt; customer opens the real page, pays with a TEST card
            → /sim/payment   ─ (no webhook) → settle_payment ─ commerce.capture_payment ─▶
                                RazorpayGateway.capture = payment_link.fetch(id); paid? → receipt
                                                                            not paid? → re-offer
            → verify → close (PAID)
```

### 4.2 Files to touch (Razorpay live)

- **`app/commerce/razorpay.py`** — add `RazorpayGateway(PaymentGateway)` (lazy `import razorpay`;
  `razorpay.Client(auth=(key_id, key_secret))`): `create_payment_link` → `payment_link.create`;
  `capture` → `payment_link.fetch` + "paid" check (verify, not re-charge); `refund` →
  `payment.refund`. Add a `fetch_payment` helper. Keep `FakeRazorpay` exactly as is.
- **`app/commerce/razorpay.py`** (or `app/commerce/__init__.py`) — a `build_gateway(settings)` factory:
  real gateway iff `razorpay_key_id`/`secret` set **and** the key is a test key; else `FakeRazorpay`.
- **`app/config.py` + `.env.example`** — note the test-key guard; keys already present.
- **`app/main.py`** — `app.state.razorpay = build_gateway(settings)` (the one swap line).
- **`pyproject.toml`** — add `razorpay` (dev-/runtime dep).
- **`playbook.md`** — the live Test-Mode run (test card `4111 1111 1111 1111`, the `/sim/payment`
  poll, how to read the Razorpay dashboard) + the test-key guard note.
- **tests** — a `RazorpayGateway` unit test with the SDK **mocked** (no network): assert we call
  `payment_link.create`/`fetch` with the right shape and map "paid"→captured. The 54 offline tests
  stay on `FakeRazorpay`. **No live call in CI.**

### 4.3 Vonage + Salesforce MCP (blocked — scoped, not built this step)

| Swap | Seam that already exists | Status (2026-10-08) | Rough shape |
|------|--------------------------|---------------------|-------------|
| **Real Vonage (9b)** | `VonageClient` Protocol (`app/tools/vonage.py`) | **UNBLOCKED** — access + $100 credit; Vonage side set up | Real RCS **send** + **real inbound/status webhooks** (customer taps + delivery/read). Planned in full: [`build-step-9b.md`](build-step-9b.md). |
| **Real Salesforce MCP (9c)** | `build_toolbox()` (`app/tools/registry.py`) | **Prep underway** — DE org in hand; needs Field Service data + an integration user + hosted MCP | Swap `FakeSalesforce` for a real MCP client behind the same tool names; reads go live before actions. See [`salesforce-handoff.md`](salesforce-handoff.md). |

Both are **one-seam swaps** by design. Vonage is codeable now (I'll plan 9b next); Salesforce needs
the org set up per [`salesforce-handoff.md`](salesforce-handoff.md) first, then I generate the client.

> **Spend note (Vonage $100):** RCS/SMS sends cost real money. Rule for the POC: use the Vonage
> sandbox / a single test number, fire one message per manual demo, never in a loop or a test run.

### 4.4 Build order (Razorpay, gated)

1. `RazorpayGateway` + `build_gateway` factory + the test-key guard (lazy import; no behaviour change
   while keys are fake).
2. `razorpay` dep added; `RazorpayGateway` unit test with the SDK mocked; 54 + new green, ruff clean.
3. **(GATED — your go)** flip to your test keys, fire the paid flow, open the real `short_url`, pay
   with a test card, fire `/sim/payment`, watch the poll confirm `paid` → `CLOSED`. Verify in the
   Razorpay **Test-Mode dashboard** that exactly one payment landed.
4. Update `playbook.md` + this file's Explanation; (gated) one-line `context/00` update.

### 4.5 Alternatives rejected

- Real webhook + signature verify now — breaks the no-webhook POC rule (polling is the POC-correct way).
- Razorpay order + Checkout widget — needs a frontend; the shareable payment link fits RCS Open-URL.
- Trusting the caller's `status` when live — wouldn't prove a real payment happened.
- Building Vonage / Salesforce swaps now — blocked on external access; planned, not coded.

## 5. Tasks

- [x] 1. `RazorpayGateway` (create_payment_link / capture=fetch+verify / refund) + `build_gateway`
  factory + test-key guard, wired into `main.py`. Client is INJECTED; fake unchanged.
- [x] 2. Unit-tested `RazorpayGateway` with a **stub client** (no dep) + `build_gateway` (fake vs
  refuse-live) + a failed-payment re-offer. **58 green, ruff clean, import OK.** `razorpay` dep
  **deferred** — not needed offline; added only at the live fire (step 3).
- [ ] 3. **(GATED — your go + test keys live)** add `razorpay` dep, one real Test-Mode payment end to
  end, confirm one payment in the Razorpay dashboard.
- [ ] 4. `playbook.md` + this Explanation; (gated) `context/00` one-liner.
- [ ] 5. **(9b — UNBLOCKED, plan next)** real Vonage swap — access + $100 credit in hand.
- [ ] 6. **(9c — prep)** real Salesforce MCP swap — once the org is set up per
  [`salesforce-handoff.md`](salesforce-handoff.md); then I generate the client.

## 6. Updates

- **2026-10-08** — Plan created. SDK shapes verified against the current `razorpay-python` docs
  (`payment_link.create` → `short_url`; `payment_link.fetch` → `status: "paid"`;
  `utility.verify_payment_link_signature` exists but unused under the no-webhook rule).
- **2026-10-08 (OQs answered)** — OQ2 poll / OQ3 payment-link-only / OQ4 test-key guard, all as
  recommended. OQ1: Razorpay first, but **Vonage is now unblocked** (access + $100 credit,
  2026-10-08) → Step 9b next; **Salesforce** handoff captured in
  [`salesforce-handoff.md`](salesforce-handoff.md) → Step 9c.
- **2026-10-08 (gateway built)** — User said go. Built `RazorpayGateway` + `build_gateway` + the
  test-key guard, wired into `main.py` (blank keys → `FakeRazorpay`, unchanged). Confirmation is by
  **polling** `payment_link.fetch` in `settle_payment` (keyed by the payment-LINK id), so the real
  gateway verifies the true status with no webhook; the fake honours the `/sim`-reported status for
  test control. **58 green, ruff clean, import OK.** Two refinements to the plan:
  1. **`razorpay` dep deferred.** The gateway takes an **injected client**; the SDK imports lazily
     only on a real test-key boot. So nothing offline needs the dep — it's added at the live fire.
     Cleaner than the plan's "add dep now" (CI stays SDK-free). Unit-tested via a stub client.
  2. **`capture` signature is now `(payment_ref, amount_paise, reported_status="captured")`** — the
     real gateway ignores `reported_status` and polls; the fake honours it (so a test can force a
     failed payment). `settle_payment` passes the payment-link id as the ref. The direct
     FakeRazorpay unit tests still pass (the new param defaults to "captured").

## 7. Explanation (Razorpay gateway — built; live fire still gated)

### 1. What changed
The commerce payment can now run against **real Razorpay Test-Mode**, behind the existing
`PaymentGateway` seam. A new `RazorpayGateway` creates a real payment link and confirms payment by
**polling** Razorpay (no webhook); a `build_gateway(settings)` factory picks fake vs real from the
env keys with a **test-key-only guard**. The fake is unchanged, so the whole suite stays offline.

### 2. Why it was needed
Step 6 shipped the commerce flow on `FakeRazorpay`. To make the money real we needed the real client
— but without breaking the no-webhook POC rule, without a new dependency weighing on CI, and without
any chance of an accidental real charge.

### 3. How it works, step by step
1. `create_payment` calls `commerce.create_payment_link` → the gateway. The real gateway calls
   `client.payment_link.create(...)` and returns the real `short_url` (the RCS "Approve & Pay" target).
2. The customer pays on the real hosted page. There is **no webhook**: when `/sim/payment` fires,
   `settle_payment` calls `commerce.capture_payment` keyed by the **payment-link id**.
3. The real gateway `capture` does `client.payment_link.fetch(id)` and only reports `captured` if the
   link's status is truly `paid` (pulling the real `razorpay_payment_id`). Not paid → the tool
   refuses → the pay card is re-offered. The fake honours the `/sim`-reported status so tests can
   drive success or failure.
4. `build_gateway` returns the real gateway **only** when a `rzp_test_…` key is set; a live key aborts
   the boot; blank keys return the fake. The `razorpay` SDK is imported lazily on that test-key path.

### 4. Files / functions changed
- **`app/commerce/razorpay.py`**: new `RazorpayGateway` (`create_payment_link`, poll-based `capture`,
  `refund`) + `build_gateway(settings)` (the fake/real/refuse-live factory); `FakeRazorpay.capture`
  gained `reported_status`; both `capture`s now key on a `payment_ref` (the link id).
- **`app/tools/registry.py`**: `commerce.capture_payment` takes `paymentRef` + optional
  `reportedStatus` and refuses a non-captured outcome.
- **`app/graph/build.py`**: `settle_payment` confirms via the gateway using the payment-link id.
- **`app/main.py`**: `app.state.razorpay = build_gateway(settings)` — the one swap line.
- **`tests/test_commerce.py`**: `RazorpayGateway` stub-client tests (create maps the SDK; poll
  paid→captured, not-paid→not; `build_gateway` fake vs refuse-live) + a failed-payment re-offer.

### 5. Important decisions
- **Poll, not webhook** (OQ2): confirmation is a `payment_link.fetch`, so the POC keeps its /sim-only
  rule while using Razorpay as the source of truth.
- **Injected client, dep deferred**: the module imports with no `razorpay` installed; the SDK is
  pulled in only at the live fire. CI stays SDK-free; the gateway is fully unit-tested via a stub.
- **Test-key guard** (OQ4): a non-`rzp_test_` key aborts the boot — a real charge is impossible.
- **Payment link only** (OQ3): the link is the shareable payable + auto-captures; no Razorpay order.

### 6. Tests / verification
- `cd apps/orchestrator && uv run pytest -q` → **58 passed** (54 prior + 4 new). `uv run ruff check .`
  → **All checks passed!**. `import app.main` → OK. All offline (fake gateway; no keys, no network).

### 7. Edge cases and limitations
- **The live Test-Mode fire is NOT done** (gated): no `razorpay` dep installed, no real link created,
  no real poll exercised against the API. That one run needs your go + your test keys.
- **Refund against the real gateway is unverified live** (tool + fake test only).
- **Polling is on-demand** (when `/sim/payment` fires), not a background poller — fine for the POC.
- **Vonage (9b) and Salesforce (9c)** are not in this change.
