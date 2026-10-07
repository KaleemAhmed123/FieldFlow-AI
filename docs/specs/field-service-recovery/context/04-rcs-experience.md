# Context: RCS Experience

> **Design-time.** The customer-facing layer — and the whole reason Vonage cares. RCS is the
> **control plane**, not a notification channel. Rich version:
> [`../diagrams/02-customer-journey.excalidraw`](../diagrams/02-customer-journey.excalidraw).

## The one rule

**If a step can be done over RCS, it is done over RCS.** The customer should never be pushed to
an app or a phone call for anything the thread can carry. Every primitive we use must map to a
real customer action, not decoration.

## What RCS is

**RCS (Rich Communication Services)** — the carrier-grade successor to SMS. On a supported device
(Android / Google Messages) the message thread becomes interactive: rich cards, swipeable
carousels, tappable suggested replies and actions, inbound image & location, Open-URL webviews,
calendar and dial actions, and (in India, on Google Messages) **PDF** rich cards. Vonage's
**Messages API** is how we send/receive it and how we get delivery/read callbacks and RCS→SMS
failover.

## The primitives we use, and the action each enables

| RCS primitive | Customer action it enables | Stage |
|---------------|----------------------------|-------|
| Rich card + suggested actions | View appointment, Add to Calendar, Change Slot, Share Location | 1 |
| **Carousel** (2–10 cards) | Pick one of several valid recovery slots | 5 |
| Suggested reply | Confirm a choice in one tap | 6 |
| **Share location** (inbound) | Phone sends GPS → we compute technician ETA | 7 |
| **Inbound image** | Upload a photo of the unit label → OCR/vision | 8 |
| Rich card (quote) | Approve & Pay / Ask / Decline | 11 |
| **Open-URL / webview** | Launch the secure Razorpay page without leaving the thread | 12 |
| Calendar action | Add the confirmed appointment | 1, 13 |
| Dial action | Call the technician | 13 |
| **PDF rich card** (India) | Open the service report in-thread | 13 |
| Delivery / read status callback | (our telemetry) | all |
| **RCS → SMS failover** | Message still arrives if RCS is unavailable | failure A |
| Capability check | Pick the right primitive for the device, or fall back | pre-send |

## The journey in one line each (the "wow" story)

1. Appointment card arrives with actions. → 2. Technician delay fires `appointment.at_risk`. →
3. AI investigates context + SLA. → 4. Policy removes illegal options. → 5. Valid slots as a
**carousel**. → 6. Customer taps a slot. → 7. Customer **shares location**; ETA confirmed. →
8. Customer **uploads a photo** of the label. → 9. Vision + **RAG**: model, warranty, likely
part. → 10. Inventory **reserved** atomically. → 11. **Quote** card. → 12. **Pay** via webview
(Razorpay Test). → 13. **Confirmation** + calendar + dial + **PDF** service report.

Then stage 13's failure demos (see [`05-reliability-and-observability.md`](05-reliability-and-observability.md)).

## Hard constraints (decide before building the agent)

- **Target = Android + Google Messages + India.** iOS RCS isn't in Vonage's India coverage; an
  iPhone demo silently fails (risk R2).
- **Agent class = Transactional.** Multi-use agents aren't available in India; our flow is all
  service messaging anyway. Use case + billing category are **irreversible** once the agent is
  created (risk R4) — get them right the first time.
- **Capability-check before exotic primitives.** If the device can't render a primitive, fall
  back gracefully rather than sending a broken card (risk R6). Test on the real device.
- **Payment is a webview, not RCS.** The "Pay" button is an Open-URL action to the Razorpay page.
  RCS never sees card data (risk R7).

## Things that will look one way but aren't

- **"Share location" is the customer's phone participating in the workflow**, not us tracking
  them — it's a one-tap, user-initiated send that feeds the ETA calc. That's the demo's strongest
  "RCS is a control plane, not a billboard" moment.
- **A carousel is not a menu of anything the AI thought of** — it only ever contains
  policy-validated options. The filtering happened upstream (Level 1).
- **PDF-in-card is India-specific** on Google Messages right now. It's a genuine local capability
  to show Vonage, not a universal feature — frame it as such.

---

*Design-time snapshot: 2026-10-06 — Kaleem Ahmed*
