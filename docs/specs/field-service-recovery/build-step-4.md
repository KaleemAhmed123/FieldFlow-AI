# Build Step 4 — RAG (knowledge retrieval) feeding the decision

**Status:** Shipped + live-verified · **Created:** 2026-10-08 · **Last updated:** 2026-10-08

> Goal: give the brain **grounding**. Before it reasons, retrieve the most relevant passages from
> our own documents (manuals, warranty, SOPs, fault codes, part compatibility) and attach them as
> real `knowledgeSources` in the decision trace — with citations + links. Build order #4
> ([`scaffold.md`](scaffold.md)). Mock-first for tests; real Jina + pgvector for the live demo.

## The one rule (from the docs)

**RAG answers "what is generally true?" (manuals); MCP answers "what is true right now, may I
change it?" (live data + actions).** Knowledge is read-only grounding — never give it side effects.
(See [`context/03-knowledge-and-tools.md`](context/03-knowledge-and-tools.md) Part A.)

## What you asked for (confirmed 2026-10-08)

- **Embeddings: Jina** (hosted — no local compute). Needs a free `JINA_API_KEY`.
- **Corpus: Claude generates it** — rich, multi-page, realistic, multiple formats, with citations
  and links. "Almost production-ready."
- **Ingestor: idempotent + multi-format + incremental** — adding pages anywhere to an already-
  embedded doc must only re-embed what changed.
- **Store: real pgvector** (Supabase). User adds DB creds.
- **Reranker: yes** (Flag 1). Everything else prod-grade (eval harness, hybrid/BM25 search,
  multi-tenant) **deferred**.
- **Tests stay off Supabase/Jina** (Flag 2), but a **real smoke test lands soon**.
- **Placement:** a `retrieve_knowledge` node **after `load_context`**, feeding `knowledgeSources`.

## How incremental ingest works (answers the "+5 pages anywhere" question)

- Split each doc into **chunks** on **structure** (page / heading / paragraph), not a blind window
  — so an insertion creates **new chunks locally** and leaves other chunks' text unchanged.
- Store a **content hash per chunk**. Re-ingest = recompute + diff: new hash → embed + insert;
  missing hash → delete; unchanged → **skip** (no re-embed, saves Jina calls).
- Use **LlamaIndex `IngestionPipeline` + a docstore**, which does this hash-based upsert for us.
- **Caveat:** editing text inside a chunk re-embeds that chunk (correct); a doc with no structure
  falls back to size-splitting where an insert can shift following chunks. Our generated corpus is
  well-structured, so this is a non-issue here.

## Plan

**Flow (text-first; Excalidraw only if asked):**
```
load_context ─▶ retrieve_knowledge ─▶ evaluate_sla ─▶ generate_options ─▶ policy_validate ─▶ …
                      │
                      ├─ build a query from the case (asset model + reason + fault hints)
                      ├─ KnowledgeStore.retrieve(query, k)  → top-k chunks (+ rerank)
                      └─ attach knowledgeSources[] {title, source, page/section, link, score}
                         to state → the decision trace cites them
```

**The seam (mock-first):**
- `app/rag/store.py` — `KnowledgeStore` Protocol: `retrieve(query, k) -> list[Chunk]`.
  - `PgVectorKnowledgeStore` — LlamaIndex PGVectorStore + Jina embeddings + Jina reranker (real).
  - `FakeKnowledgeStore` — in-memory, deterministic fake embedder; used by all unit tests. No
    network, no key, no Supabase.
- `app/rag/ingest.py` — the smart ingestor: load a folder (PDF/md/CSV) → structure-aware split →
  hash-based upsert into the store. Idempotent. Run via `scripts/ingest_knowledge.py`.
- `app/rag/corpus/` (generated) — the synthetic knowledge set for the Daikin XYZ-492:
  - `service-manual.pdf` (multi-page: sections, fault-code table, page numbers)
  - `warranty-policy.pdf` (clauses, coverage table, links)
  - `troubleshooting-faultcodes.md`
  - `technician-sop.md`
  - `part-compatibility.csv` (which PCB/part fits which model)
- `scripts/generate_corpus.py` — regenerates the corpus deterministically (reportlab for PDFs).
- `app/graph/build.py` — new `retrieve_knowledge` node + `knowledgeSources` in state + trace.
- `app/config.py`, `.env.example` — `JINA_API_KEY`, embedding model/dims, corpus path.
- **new** `tests/test_rag.py` — retrieve returns relevant chunks (fake store); ingest is idempotent
  (re-run = no dupes); inserting a chunk only adds one (incremental); `knowledgeSources` land in the
  trace; Step-1/2/§3 tests stay green.

**Dependencies to add (uv — modifies the lockfile; needs your ok):**
`llama-index-core`, `llama-index-vector-stores-postgres`, `llama-index-embeddings-jinaai`,
`llama-index-postprocessor-jinaai-rerank`, `pypdf` (read PDFs), `reportlab` (generate PDFs).

**Alternatives rejected:** local embeddings (slows the PC — user vetoed); whole-doc embedding (can't
do incremental); hand-rolled vector math (LlamaIndex already does chunk/embed/retrieve/upsert);
hybrid search + eval harness now (prod-grade, deferred per Flag 1).

## Tasks

- [x] Add deps (llama-index-core, embeddings-jinaai, postprocessor-jinaai-rerank, vector-stores-postgres, pypdf, reportlab).
- [x] `KnowledgeStore` Protocol + `FakeKnowledgeStore` (deterministic) + `PgVectorKnowledgeStore`.
- [x] `generate_corpus.py` → the 5-doc multi-format corpus with citations/links.
- [x] `ingest.py` + `scripts/ingest_knowledge.py` — multi-format, structure-aware, hash-upsert, idempotent.
- [x] `retrieve_knowledge` node + real `knowledgeSources` in the decision trace.
- [x] `JINA_API_KEY` + config/env.
- [x] `tests/test_rag.py` (mock-first) + all prior tests green (28/28); ruff clean.
- [x] A **live smoke test** against real Supabase + Jina — run 2026-10-08. 17 chunks embedded into real pgvector; retrieval returned cited passages (warranty query → warranty Clause 1, score 0.752).

## Acceptance (self-checks, no infra)

`pytest` (in-memory SQLite + FakeKnowledgeStore + fake embedder), all green:
- retrieve returns the right chunk for an asset/fault query; `knowledgeSources` carry title + source
  + page/section + link;
- ingest is idempotent (re-run adds nothing); inserting one chunk re-embeds only that chunk;
- the decision trace shows real `knowledgeSources`; every Step-1/2/§3 test still passes.
Ruff clean. The live pgvector+Jina path is covered by the separate smoke test once creds land.

## Rules

Speed-first but robust where it's the story (incremental ingest, citations); mock-first; the LLM
proposes, policy decides; knowledge is read-only. Commands live in [`../../../playbook.md`](../../../playbook.md).

## Updates

- **2026-10-08** — Plan created after §3 shipped. Awaiting go on the dependency install, then build
  mock-first (creds gate only the live ingest + smoke test).
- **2026-10-08** — **Built RAG mock-first.** Deps installed (note: LlamaIndex pinned SQLAlchemy
  2.1→2.0.54; all prior tests stayed green). `KnowledgeStore` seam + fake + pgvector store; 5-doc
  corpus generated; structure-aware splitters; idempotent/incremental ingestor (content-hash ids);
  `retrieve_knowledge` node feeding real cited `knowledgeSources`; `tests/test_rag.py`. **28/28
  pytest, ruff clean**, `app.main` imports. Retrieval sanity-checked on the fake (warranty query →
  warranty doc, PCB query → control-board chunk). Live Jina+pgvector path written but not yet run.

- **2026-10-08** — **Live smoke test run and passed.** `scripts/ingest_knowledge.py` embedded 17
  chunks across all 5 docs into the user's real Supabase pgvector via Jina (`added=17`). A live
  `retrieve()` (real Jina embed + pgvector cosine + Jina rerank) returned correctly cited passages:
  "PCB covered under warranty?" → warranty Clause 1 (coverage), score 0.752; "fault code E5" → F3
  control-board entries in the manual + troubleshooting doc. Fixed one cp1252 console crash in the
  script's final `print` (`→` → `->`). 28/28 pytest still green, ruff clean. **Step 4 fully done.**

## Explanation

**1. What changed.** The brain now grounds its reasoning in documents. Before options are proposed,
a new `retrieve_knowledge` node fetches the most relevant manual/warranty/SOP/part passages and
attaches them as cited `knowledgeSources` in the decision trace.

**2. Why.** Salesforce holds *data* (asset, warranty flag) but not *knowledge* (fault codes, repair
SOP, policy wording, part compatibility). Grounding lets the demo show *"concluded likely PCB-492
control-board failure, warranty-covered — per the service manual p.2 and warranty policy clause 1."*

**3. How it works.**
- `app/rag/split.py` splits each file on structure (md heading / csv row / pdf page) into chunks
  with a **content-stable id** `doc#<sha1(text)>` + citation metadata (source, locator, link).
- `app/rag/ingest.py` diffs those chunks against what the store already holds for that doc and
  embeds/upserts only new-or-changed, deletes vanished, skips unchanged — idempotent + incremental
  (inserting pages anywhere embeds only the new chunks). Store-agnostic, so it behaves identically
  on the fake and the pgvector store.
- `app/rag/store.py` — `FakeKnowledgeStore` (in-memory + deterministic token-hash embedder, for
  tests). `app/rag/pgstore.py` — `PgVectorKnowledgeStore` (sync pgvector + Jina embeddings + Jina
  reranker, for live). Both behind one `KnowledgeStore` Protocol.
- `retrieve_knowledge` (graph) builds a query from asset model + reason, retrieves top-k, and writes
  `knowledgeSources`; `policy_validate` carries them into the trace. A retrieval error degrades to
  zero sources — knowledge never breaks the decision (R9).

**4. Files.** new `app/rag/{embed,store,split,ingest,pgstore}.py` + `app/rag/__init__.py` factory;
`scripts/{generate_corpus,ingest_knowledge}.py`; `app/rag/corpus/*` (5 generated docs); graph node +
`knowledgeSources` in state/trace; `app/config.py` + `.env.example` (Jina/RAG settings); `main.py`
(builds the store, picks real vs fake); `tests/conftest.py` (knowledge fixture) + `tests/test_rag.py`.

**5. Decisions.** Store-agnostic incremental diff owned by us (testable, same code on fake + real)
rather than LlamaIndex's docstore, so the "+pages anywhere" behaviour is proven in `pytest`.
Deterministic embedder for tests (offline, no key); Jina only live. Vector table kept in our own
Postgres (transparent, reuses our stack); LlamaIndex supplies the Jina embedding + reranker. Sync
engine for the pgvector store so the sync graph nodes can call `retrieve()` directly.

**6. Verification.** `pytest -q` → **28 passed** (+6 RAG). `ruff check` → clean. `import app.main`
→ OK. Live ingest printed 17 chunks across 5 docs; retrieval returned the expected docs per query.

**7. Edge cases & limits.** The live Jina+pgvector path is written but **not yet executed** (gated
on running against the user's real DB/Jina). Deferred per Flag 1: eval harness, hybrid/BM25 search,
multi-tenant corpora. Deterministic embedder is token-overlap, not semantic — real retrieval quality
comes from Jina. Unstructured PDFs would fall back to page-level chunks (our corpus is structured).
