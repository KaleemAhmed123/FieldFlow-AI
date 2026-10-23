# Video demo script — real end-to-end (SA-0002)

**Shows the live pipeline:** a scheduled appointment goes **at risk** → FieldFlow messages the customer
over **RCS** → they tap a new slot → the **appointment reschedules in Salesforce** → an out-of-warranty
part needs paying → they **pay on the phone** → the **payment is written back to Salesforce**, all on its
own. No scripts, no typing — you just tick a box and narrate.

**Open side by side:** (1) Salesforce **Field Service** app on **SA-0002**; (2) your **phone** (the RCS
test device). Optional: the **panel** (`fieldflowpanel.vercel.app`) to show the case trace.

---

## Pre-flight (off camera — set once)
1. **Live build:** `curl https://fieldflow-ai-w6bm.onrender.com/version` returns a commit (not 404).
2. **SA-0002 starts scheduled:** edit it → **Scheduled Start/End** = today e.g. 2:00–4:00 pm → Save.
   (Asset warranty is already expired; territory "FieldFlow Noida" is set.)
3. **Reset its flags:** `At Risk` = unchecked, `At Risk Reason` = blank, and delete any old
   **FieldFlow Payments** rows.
4. **Part stock:** on the e-com dashboard (`fieldflowinventory.vercel.app`) set **CAP-492** to e.g. 5
   (each take reserves one).
5. **Phone ready** on the Vonage test number, RCS visible.

---

## The demo

**Scene 1 — the scheduled job (~15s)**
Show SA-0002: a normal appointment with a time, an out-of-warranty AC, a customer.
*Say:* "A scheduled service visit in Salesforce. Now the technician can't make it and the fix needs a part."

**Scene 2 — mark it at risk (~15s)**
Tick **At Risk**, set **At Risk Reason** = `part_missing` (optional: Delay Minutes = 90). **Save.**
*Say:* "I just flag the appointment at risk — that's the only human action in this whole flow."

**Scene 3 — the customer gets an RCS message (~20s)**
Switch to the phone — a rich RCS carousel of new slots arrives within seconds.
*Say:* "FieldFlow read the case, picked valid slots, and messaged the customer over RCS automatically."

**Scene 4 — they tap a slot → the appointment reschedules (~20s)**
On the phone, **tap the part-fit slot** (the one that mentions the part). Switch back to Salesforce and
**refresh SA-0002**.
*Say:* "The appointment rebooked itself to the slot the customer chose — Scheduled Start and End just changed."

**Scene 5 — pay on the phone → payment written back (~30s)**
Back on the phone, the **Approve & Pay** card arrives (₹3,700). Tap it, pay with a Razorpay **test** card.
Wait ~10 seconds, then **refresh SA-0002**.
*Say:* "Because the part's out of warranty, they pay — the price is from a fixed price book, not the AI.
Seconds after paying, the payment is captured and written back to Salesforce, no one touching a keyboard."
Show the **FieldFlow Payments** related list — the captured ₹3,700, linked to this appointment. Click into
it (or the **FieldFlow Payments** tab) to show it's a real object: payment id, order id, amount, status.

---

## Reset between takes (off camera)
- SA-0002: **uncheck At Risk**, clear **At Risk Reason**, set a Scheduled time again, delete the new
  **FieldFlow Payments** row. (The trigger only fires on a fresh unchecked→checked change.)
- e-com: top **CAP-492** stock back up if it ran low.

## If something stalls on camera
- **No RCS on the phone** → confirm Render's `VONAGE_TEST_TO` is your number; re-fire by unticking +
  re-ticking At Risk (it only fires on the transition).
- **No pay card, case paused at "approval"** → the AI picked a pricier part (quote ≥ ₹5,000, a human
  gate). Approve it in the panel, or re-fire — the cheaper part (CAP-492, ₹3,700) skips the gate.
- **Only a loaner slot, no paid option** → the part is out of stock; top it up on the e-com dashboard.
- **Payment not in Salesforce after ~15s** → refresh the SA-0002 record page; unpaid links expire after
  3 minutes.

## Talking points
- Only human action: ticking **At Risk**. Everything after — slots, RCS, reschedule, pricing, payment,
  the Salesforce write-back — is automatic.
- Slot time → standard `ServiceAppointment`; payment → custom `FieldFlow_Payment__c` linked to it.
- Price comes from a fixed price book, not the AI. Honest caveat: the *list* of slots is AI-proposed, not
  yet read from Salesforce's real calendar (the planned "real availability" upgrade).
