# Build Step 10 — Realistic domain data (catalog + rich corpus) + proposer grounding (fix A)

## 1. Task

- **Name:** Step 10 — a real product catalog, a rich RAG corpus generated from it, aligned
  inventory/Salesforce fakes, and a grounded proposer (fix A).
- **Status:** shipped (offline-green + live-verified).
- **Started:** 2026-10-09.
- **Last updated:** 2026-10-09.

Replace the thin single-asset demo data with a **12–15 model product catalog** (6–8 parts each),
drive the whole system from it (inventory, Salesforce assets, and a rich RAG corpus), and **ground
the proposer** so it proposes real catalog parts and leaves a pure delay part-free.

## 2. What you asked for (your words)

- **12–15 products**, **6–8 parts each**, almost-real data.
- A **structured catalog saved in the project** — reusable later to **seed Salesforce or the e-com
  system**.
- Docs must be **very rich, mimic real-world complexity — many pages, dense**.
- **Real PDFs** (not text with a .pdf name).
- **Use Jina** to re-ingest.
- (From before) **Fix A:** tune the proposer so a *delay* proposes no part, and when a part is
  needed it's a real catalog part — keep the **70 tests green**.

## 3. Open questions — ANSWERED 2026-10-09

| # | Question | Your answer |
|---|----------|-------------|
| 1 | Catalog size? | **12–15 models, 6–8 parts each**, almost-real. |
| 2 | Structured catalog as source of truth, saved in-project? | **Yes** — it'll later seed SF / e-com. |
| 3 | How rich are the docs? | **Very rich** — many pages, dense, real-world complexity. |
| 4 | File format? | **Real PDFs.** |
| 5 | Re-ingest to live pgvector with Jina? | **Yes.** |

**Execution decisions I'm taking (flag me if any is wrong):**
- **Catalog-driven, template-generated PDFs** — the richness lives in a rich catalog + dense
  reportlab templates (real PDFs; `pypdf` already reads them). Deterministic + regenerable, scales to
  15 models. *Rejected:* hand-authoring 15 giant PDFs (not regenerable, drifts from the data).
- **I author the catalog myself, not via subagents** — a seed dataset must be internally consistent
  (parts ↔ fault codes ↔ warranty ↔ inventory cross-refs); one author keeps it coherent. (Can revisit
  for speed if you want.)
- **Fictional brands, not real ones** — "almost real" = realistic but invented (the project rule is
  *fake everything*; the current code's "Daikin" is a pre-existing real-brand slip I'll retire).
- **Keep the canonical demo entry** — the current `XYZ-492` asset with parts `PCB-492`/`CAP-492`/
  `SENSOR-11`/`FILTER-100` and appointments `SA-19281`/`SA-OOW` stays as one catalog model (under a
  fictional brand) so the 70 tests keep passing with minimal churn.

## 4. Plan

### Approach
One **`catalog.json`** is the source of truth. Everything reads from it:
- **FakeInventory** seeds its stock from the catalog parts (most in stock; a couple scarce for the
  NFR-5 race).
- **FakeSalesforce** assets/appointments reference catalog models (canonical `SA-19281`/`SA-OOW`
  kept).
- **`generate_corpus.py`** expands each model into **dense, multi-page real PDFs** + global docs.
- **The proposer** is given the catalog + the retrieved passages, with the rule: *delay → no part; if
  a part is genuinely needed, pick a real catalog part and prefer one in stock.*

### Catalog shape (per model)
`brand` (fictional) · `model` · `category` (HVAC / water-purifier / refrigeration / washer / …) ·
`specs` · `warrantyMonths` + coverage clauses · `parts[]` (`partNo`, `name`, `kind`
board/sensor/mechanical/consumable, `pricePaise`, `warrantyCovered`, `requiresSkill`, `scarce`) ·
`faultCodes[]` (`code`, `meaning`, `likelyPart`, `needsPart`, `skill`, `safetyRisk`).

### Docs generated per model (dense)
Service manual (overview · specs · installation · a fault-code table · a replacement procedure *per
part* · maintenance schedule · safety), a warranty annex, and a troubleshooting guide — plus
**global** docs: the master warranty policy, a field-tech SOP set, and a part-compatibility matrix
(CSV). Target real-world density (many pages across the corpus).

### Files to touch
```
app/data/catalog.json          NEW — the 12–15 model catalog (source of truth; future SF/ecom seed)
app/data/catalog.py            NEW — loader + helpers (models, parts_for, stock_seed, asset_for)
scripts/generate_corpus.py     REWRITE — catalog-driven dense PDF/MD/CSV generation
app/tools/inventory.py         seed stock from the catalog (keep CAP-492; add the rest; some scarce)
app/tools/salesforce.py        assets/appointments from the catalog (keep SA-19281/SA-OOW canonical)
app/llm/ (proposer + prompt)   ground in catalog + retrieval; delay → no part; real in-stock part
tests/                         update fixtures that assert specifics; canonical IDs kept green
playbook.md                    regen + ingest commands; build-step-10 Explanation
```

### Alternatives rejected
- Hand-authoring each PDF (not regenerable; drifts from the catalog).
- Subagents authoring the catalog in parallel (consistency risk on a cross-referenced seed dataset).
- A separate e-com service now (still a fake behind the Toolbox; the catalog *is* the seed for it
  later — Step 9c).

## 5. Tasks

- [x] 1. `app/data/catalog.json` (14 models, 6–7 parts each, fault codes, warranty) + `catalog.py`
      loader. Canonical `XYZ-492` kept (fictional brand **Frostline**) with `PCB-492`/`CAP-492`/
      `SENSOR-11`/`FILTER-100`; `CAP-492`/`PCB-492` prices aligned to the commerce book.
- [x] 2. Rewrote `generate_corpus.py` → catalog-driven: per-model dense multi-page **real PDFs**
      (overview, install, fault-code table, per-part procedures, maintenance/safety/warranty) +
      global `warranty-policy.pdf`, SOP, troubleshooting guide, part-compat CSV. 18 files.
- [x] 3. `FakeInventory` seeds stock from the catalog (scarce→1 keeps the NFR-5 race; `set_stock`
      unchanged). `FakeSalesforce` asset model matches the catalog; retired the real "Daikin" brand
      and the `daikin-inverter` skill (→ `inverter-ac`).
- [x] 4. Fix **A** in `proposer.py`: `build_prompt` now hands the model the asset's catalog parts +
      the rules (delay → no part; only catalog parts; avoid scarce), and `parse_proposal`
      **enforces** it (strips a part on delay, strips any part not in the asset's catalog). Groq/
      Gemini pass `context` through. Deterministic fallback untouched.
- [x] 5. Regenerated PDFs + **re-ingested to live pgvector via Jina** (+208 chunks). Live dry run
      confirmed: `technician_delay` → `OPTIONS_SENT`, policy APPROVED, conf 0.988, **no part**;
      `part_missing` → grounded `PCB-492` (cited F3 + loaner). 72 offline tests green, ruff clean.

## 6. Updates

- **2026-10-09** — Spec created; OQ1–5 answered. Root cause of the live denial captured: the corpus
  references `PCB-492` but `FakeInventory` only stocked `CAP-492`, and the proposer wasn't grounded
  in a catalog — so the live LLM invented a part policy then denied. This step fixes the data + the
  grounding together.

## 6b. Updates

- **2026-10-09 (SHIPPED).** Built tasks 1–5. 72 offline tests green, ruff clean, `import app.main`
  OK. Live-verified on the real stack (CloudAMQP + Supabase pgvector + Jina + Groq, Vonage/Razorpay
  faked): the delay case that used to invent a part and escalate to a human now auto-sends cleanly.
  **Perf note:** the first live retrieval after a cold start was slow (~60s for the Jina
  embed+rerank over 208 chunks); subsequent fires were ~2–6s. Warm the RAG with one throwaway fire
  before a live demo.

## 7. Explanation

### 1. What changed
The thin single-asset demo data became a **14-model product catalog** (`app/data/catalog.json`) that
is now the single source of truth. Inventory stock, the Salesforce asset, and a **rich multi-page
PDF knowledge corpus** are all generated from it, and the live LLM proposer is **grounded** in it.

### 2. Why it was needed
The live dry run showed the Groq model inventing an out-of-stock part (`PCB-492`) on a pure delay;
policy denied it and escalated to a human, so the clean "delay → auto-sent carousel" never happened
live. Root cause: the corpus/inventory were out of sync and the proposer wasn't grounded in any real
catalog. The data was also too thin for a credible domain demo.

### 3. How it works, end to end
- **`catalog.json`** holds each model's specs, warranty, 6–7 real parts (price, warranty-cover,
  skill, scarcity), and fault codes. **`catalog.py`** loads it and serves `stock_seed()`,
  `parts_for_model()`, `model_for_asset()`, etc.
- **`FakeInventory`** seeds its stock from `stock_seed()` (scarce parts at qty 1 so the NFR-5 race
  still fires); `set_stock` is unchanged so every test holds.
- **`generate_corpus.py`** expands each model into a dense service-manual PDF (overview, install,
  a fault-code table, a replacement procedure per part, maintenance/safety/warranty) plus global
  docs. `pypdf` reads them back; one PDF page = one retrievable chunk.
- **The proposer (fix A):** `build_prompt` gives the model the asset's catalog parts and the rules
  (*delay → no part; only catalog parts; avoid scarce*). `parse_proposal` then **enforces** it in
  code — a delay never carries a part, and any part the model invents that isn't in the asset's
  catalog is stripped — before policy validates stock/skill. The deterministic fallback is untouched.

### 4. Files / functions
- `app/data/catalog.json` (new), `app/data/catalog.py` (new loader + helpers), `app/data/__init__.py`.
- `scripts/generate_corpus.py` (rewritten, catalog-driven dense PDFs).
- `app/tools/inventory.py` (seeds from catalog), `app/tools/salesforce.py` (catalog model, no brand).
- `app/llm/proposer.py` (`_asset_parts`, grounded `build_prompt`, enforcing `parse_proposal`);
  `app/llm/groq.py` + `app/llm/gemini.py` pass `context` through.
- `app/rag/corpus/*` regenerated (18 files); `tests/test_tools.py` updated for the new model/skill.

### 5. Important decisions
- **Catalog-driven template generation** over hand-writing PDFs — regenerable, consistent, scales.
- **Enforce grounding in code, not just the prompt** — the model can't smuggle in a bad part.
- **Keep the canonical `XYZ-492`/`CAP-492`/`PCB-492` entry** so the suite stayed green with minimal
  churn (only two brand/skill assertions updated).
- **Fictional brands** (retired the real "Daikin") per the project's "fake everything" rule.
- Commerce keeps its own price book (money authority); the catalog mirrors the two canonical prices.

### 6. Tests / verification
- `uv run pytest -q` → **72 passed**; `ruff check .` clean; `import app.main` OK.
- `scripts/ingest_knowledge.py` → **+208 chunks** embedded to live pgvector via Jina.
- Live: `technician_delay` → `OPTIONS_SENT` / APPROVED / conf 0.988 / **no part** (no `find_part`);
  `part_missing` → grounded `PCB-492`, cited F3, loaner fallback, APPROVED.

### 7. Edge cases & limitations
- **Cold-start retrieval latency** (~60s first fire; warm after) — Jina embed+rerank over 208
  chunks. Warm it before a demo.
- **Panel fires only the canonical asset** (`SA-19281`); the other 13 models enrich the RAG corpus
  and inventory but aren't reachable as appointments yet (a future panel model-picker + more
  `FakeSalesforce` appointments, both easy, since the catalog is ready to seed them).
- **Commerce prices non-canonical parts at the default** (₹2,500) unless added to its book — fine
  for the demo; unify commerce onto the catalog later.
- Corpus is dense but still synthetic/templated; prose varies by category, not per-unit bespoke.
