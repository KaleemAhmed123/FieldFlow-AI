# Specs Index

This folder holds all planning and specification work, kept apart from the project's own
documentation. One row per task with its status.

| Task | Folder | Status | Last updated |
|------|--------|--------|--------------|
| **FieldFlow AI** — AI field-service recovery POC (RCS + Vonage) | [`field-service-recovery/`](field-service-recovery/) | In progress | 2026-10-07 |
| **Realistic demo seed** — 28 rich cases across 14 models (SF+RAG+e-com) + carousel image fix | [`realistic-demo-seed.md`](realistic-demo-seed.md) | In progress | 2026-10-12 |
| **Production-readiness audit** — evidence-based audit vs SRS (code/tests/live); verdict + top-5 gaps | [`../../production-readiness-audit.md`](../../production-readiness-audit.md) | Shipped | 2026-10-14 |
| **Demo video** — HyperFrames→MP4 product video; SF trigger → AI decision → Vonage RCS phone flow (~90s). **Moved out to** `C:\Users\hp\Desktop\Projects-Root\project-videos\demo-video\` (+ `demo-video.md`) | — | In progress | 2026-10-14 |
| **Demo video v7 — FSL + Headless 360 + Vonage reframe** — manager review: AI demoted, confidence removed, headless=Headless 360/MCP, + real-SF beats (appt in FSL, slot-pick updates appt, payment record, WO completed). Spec: `project-videos\demo-video\review-v2-fsl-reframe.md` | — | In progress | 2026-10-16 |
| **SF payment object** — write captured payments back to SF as `FieldFlow_Payment__c` (lookup to appointment); Apex `/payment` endpoint + `deploy_sf.py` object/fields/FLS; wired into `settle_payment` | [`sf-payment-object.md`](sf-payment-object.md) | Shipped (live-verified) | 2026-10-21 |
| **Operational data** — rich/connected SF seed (territories, skills, members, assignments, rich fields) so any scenario is firable; quote price from e-com (book fallback) | [`operational-data.md`](operational-data.md) | Shipped (seeded + verified; live fire pending) | 2026-10-21 |

**FieldFlow AI build steps:** spine ✅ · [Step 1](field-service-recovery/build-step-1.md) ✅ (policy + graph + interrupt/resume + NFR-4/5/6) · [Step 2](field-service-recovery/build-step-2.md) ✅ (MCP tool surface) · [Step 4](field-service-recovery/build-step-4.md) ✅ (RAG, live-verified) · [Step 5](field-service-recovery/build-step-5.md) ✅ (LLM proposer ladder + evidence-weighted confidence, live-verified) · [Step 6](field-service-recovery/build-step-6.md) ✅ shipped mock-first (commerce + Razorpay; live call gated) · [Step 9 Razorpay](field-service-recovery/build-step-9.md) ✅ gateway built + offline-tested (live Test-Mode fire gated) · [Step 9b Vonage](field-service-recovery/build-step-9b.md) ✅ send + webhooks built + offline-tested (live device send gated) · [Step 7 Failure demos](field-service-recovery/build-step-7.md) ✅ RCS→SMS fallback + Salesforce-down/DLQ built + offline-tested (DLQ land+replay = manual RabbitMQ demo) · [Salesforce handoff (9c)](field-service-recovery/salesforce-handoff.md) 📋 offload sheet · [Durable checkpointer](field-service-recovery/durable-checkpointer.md) ✅ Postgres checkpointer + 409 resume guard (fixes the approve `KeyError` 500; live-verified).

---

## What "status" means

- **Planning** — spec being written, no code yet.
- **In progress** — build has started.
- **Shipped** — demo-ready and verified.
