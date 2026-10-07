# Build Step 4 — RAG (knowledge retrieval) feeding the decision

**Status:** Planned (awaiting go on deps) · **Created:** 2026-10-08

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

- [ ] Add deps (after go).
- [ ] `KnowledgeStore` Protocol + `FakeKnowledgeStore` (deterministic) + `PgVectorKnowledgeStore`.
- [ ] `generate_corpus.py` → the 5-doc multi-format corpus with citations/links.
- [ ] `ingest.py` + `scripts/ingest_knowledge.py` — multi-format, structure-aware, hash-upsert, idempotent.
- [ ] `retrieve_knowledge` node + real `knowledgeSources` in the decision trace.
- [ ] `JINA_API_KEY` + config/env.
- [ ] `tests/test_rag.py` (mock-first) + keep all prior tests green; ruff clean.
- [ ] A **live smoke test** against real Supabase + Jina (run once creds land) — the "real testing soon".

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
