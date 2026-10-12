# Realistic demo seed — rich multi-model data across SF + e-com + RAG

## Task
- **Name:** Realistic demo seed (28 appointments across all 14 models) + carousel image fix
- **Status:** in progress
- **Started:** 2026-10-12
- **Last updated:** 2026-10-12

## What you asked for
- Seed **20–30 real records** in the real Salesforce org **with related records**, as **real-world
  cases** so the AI generates **comprehensive, rich options**.
- Make sure **RAG data, e-com data, and all other data** are seeded so everything **connects** and
  demos like a real system.
- Fix **why the carousel images are blank**.

## Open questions (answered — "go with defaults")
1. Spread → **28 appointments = 2 per model (14 models), warranty ~50/50.**
2. Technicians → **pool of 6 distinct ServiceResources** (from the 16 free users), reused.
3. Customers → **~10 distinct** customers reused across the 28 appointments.
4. Images → **A1 now**: one static branded image on the Vercel e-com (`/card.png`); A2 (per-model) later.
5. Cleanup → **additive** (keep SA-0001/0002) + a **`--clean`** flag to remove FieldFlow demo data.

## Plan
**Already catalog-driven (no work needed):** the RAG corpus has 14 per-model service manuals + 4
global docs; the e-com has all 86 parts (every model) live on Vercel. Both come from
`app/data/catalog.json` (the single source of truth). So only Salesforce needs expanding + the live
RAG store needs (idempotent) ingestion.

1. **Salesforce (`seed_demo_data.py` rewrite, catalog-driven):** 10 customers, 6 technicians, and for
   each of the 14 models × {in-warranty, out-of-warranty}: Asset → WorkOrder → ServiceAppointment →
   assigned technician. Idempotent (match on filterable fields), fail-loud, `ParentRecordId`
   create-only. Prints a **fire menu** (AppointmentNumber → model → warranty → suggested reason).
2. **RAG live store:** run `scripts/ingest_knowledge.py` (idempotent/incremental) so Render's live
   pgvector retrieval is grounded for every model.
3. **E-com:** verify 86 parts live (already seeded) — no change.
4. **Image fix A1:** add `apps/ecom/public/card.png` (static branded image) + point `_card_media`
   at `https://field-flow-ai.vercel.app/card.png` (no query param — Google RBM renders static media).
5. **`--clean` flag** on the seed to remove FieldFlow demo records.

Rejected: per-model card images (A2) now — the catalog has no real images; defer. Skill-matched
technician setup (SF Skill/ServiceResourceSkill objects) — policy doesn't hard-gate on skill match
(SA-0001 approved with a mismatched-skill tech), so plain named ServiceResources suffice.

## Tasks
- [x] Rewrite `seed_demo_data.py` catalog-driven (28 appts, 10 customers, 6 techs, warranty mix, fire menu, `--clean`)
- [x] Run the seed against the real org → SA-0003..SA-0030 (fire menu captured)
- [x] Run `ingest_knowledge.py` → live RAG already complete (209 chunks, 14 manuals)
- [x] Image fix A1 (static `card.png` + `_card_media`) — needs e-com + orchestrator redeploy
- [x] Verify rich options end-to-end (local LLM, no send) across fridge/AC/microwave
- [ ] Update `playbook.md`; commit; redeploy

## Updates
- 2026-10-12 — Spec created; defaults approved. RAG corpus + e-com already cover all 14 models
  (both catalog-generated); only SF expansion + live RAG ingest + the image fix are new work.

## Explanation
1. **What changed** — (a) `seed_demo_data.py` rewritten catalog-driven: 10 customers, 6 technicians,
   and 28 Asset→WorkOrder→ServiceAppointment chains (every model × in/out warranty), each with an
   assigned technician, plus a printed **fire menu** and a `--clean` flag. (b) Carousel `media_url`
   switched from a dynamic placehold.co URL to a **static** `https://field-flow-ai.vercel.app/card.png`
   (new file `apps/ecom/public/card.png`).
2. **Why** — one XYZ-492 case wasn't a real demo; the user wanted 20-30 real-world cases across models
   so the AI produces rich, model-specific options. And RCS carousel images were blank.
3. **How it works** — the seed reads `app/data/catalog.json` (the single source of truth that also
   generates the 14 RAG manuals and the 86 e-com parts), so a fired case connects: real SF asset →
   its manual (RAG) → its parts (e-com) → the LLM proposes model-specific options. The reason is
   chosen at fire time (per the menu) and drives the archetype (delay / parts / complex).
4. **Files** — `apps/salesforce-apex/seed_demo_data.py` (rewrite), `apps/orchestrator/app/tools/vonage.py`
   (`_card_media` → static URL; dropped the now-unused `quote` import), `apps/ecom/public/card.png` (new).
5. **Decisions** — single shared card image (A1) not per-model (A2, deferred — catalog has no real
   images); plain named technicians (policy doesn't gate on skill); additive seed + `--clean`.
6. **Verification** — seed ran clean (SA-0003..SA-0030); `ingest_knowledge.py` → 209 chunks unchanged
   (live RAG already complete); 99 tests green + ruff clean; a local LLM run (real SF + live e-com, no
   send) produced model-specific parts: fridge `FANE-410`/`COMP-410`, AC `PCB-492`, microwave `HVT-28`.
7. **Edge cases / limits** — image render is verified by inspection (valid static PNG, no query); final
   proof is one real send after redeploy. Several LLM part-cases route to human approval (conf ~0.62,
   below the 0.7 gate) — existing policy behavior, a separate tuning choice. Earlier demo fires drained
   some e-com stock (e.g. CAP-492→0); re-run e-com `pnpm seed` or the dashboard Set to reset.
