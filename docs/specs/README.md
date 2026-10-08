# Specs Index

This folder holds all planning and specification work, kept apart from the project's own
documentation. One row per task with its status.

| Task | Folder | Status | Last updated |
|------|--------|--------|--------------|
| **FieldFlow AI** — AI field-service recovery POC (RCS + Vonage) | [`field-service-recovery/`](field-service-recovery/) | In progress | 2026-10-07 |

**FieldFlow AI build steps:** spine ✅ · [Step 1](field-service-recovery/build-step-1.md) ✅ (policy + graph + interrupt/resume + NFR-4/5/6) · [Step 2](field-service-recovery/build-step-2.md) ✅ (MCP tool surface) · [Step 4](field-service-recovery/build-step-4.md) ✅ (RAG, live-verified) · [Step 5](field-service-recovery/build-step-5.md) ✅ (LLM proposer ladder + evidence-weighted confidence, live-verified) · [Step 6](field-service-recovery/build-step-6.md) ✅ shipped mock-first (commerce + Razorpay; live call gated) · [Step 9 Razorpay](field-service-recovery/build-step-9.md) ✅ gateway built + offline-tested (live Test-Mode fire gated) · [Step 9b Vonage](field-service-recovery/build-step-9b.md) ✅ send + webhooks built + offline-tested (live device send gated) · [Step 7 Failure demos](field-service-recovery/build-step-7.md) ✅ RCS→SMS fallback + Salesforce-down/DLQ built + offline-tested (DLQ land+replay = manual RabbitMQ demo) · [Salesforce handoff (9c)](field-service-recovery/salesforce-handoff.md) 📋 offload sheet.

---

## What "status" means

- **Planning** — spec being written, no code yet.
- **In progress** — build has started.
- **Shipped** — demo-ready and verified.
