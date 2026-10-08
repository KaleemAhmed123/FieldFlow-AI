"""RAG, mock-first: retrieval returns the relevant cited chunk, ingest is idempotent + incremental,
and the decision trace carries real knowledgeSources. No Supabase, no Jina — FakeKnowledgeStore +
the deterministic embedder. (The live Jina+pgvector path is covered by the separate smoke test.)"""

from __future__ import annotations

from pathlib import Path

from app.db.models import Case
from app.rag.ingest import ingest_dir
from app.rag.split import split_markdown
from app.rag.store import Chunk, FakeKnowledgeStore
from app.services import case_service
from fieldflow_contract import make_event
from sqlalchemy import select

CORPUS = Path(__file__).resolve().parent.parent / "app" / "rag" / "corpus"


# --- Retrieval: the right passage comes back, with citation metadata ----------------------
def test_retrieve_finds_relevant_chunk_with_citation(knowledge):
    hits = knowledge.retrieve("PCB-492 control board fault code F3", k=3)
    assert hits
    top = hits[0].chunk
    assert "PCB-492" in top.text or "control board" in top.text.lower()
    # citation metadata is present for the decision trace
    assert top.metadata["source"]
    assert top.metadata["locator"]
    assert top.metadata["link"]


def test_warranty_query_retrieves_warranty_doc(knowledge):
    hits = knowledge.retrieve("is the repair covered under active warranty", k=3)
    sources = {h.chunk.metadata["source"] for h in hits}
    assert "warranty-policy.pdf" in sources


# --- Ingest: idempotent + incremental -----------------------------------------------------
def test_ingest_is_idempotent():
    store = FakeKnowledgeStore()
    first = ingest_dir(store, CORPUS)
    assert first.added > 0
    second = ingest_dir(store, CORPUS)          # re-run, nothing changed
    assert second.added == 0 and second.deleted == 0
    assert second.unchanged == first.added


def test_incremental_add_only_embeds_new_chunk():
    # A tiny two-section markdown doc, ingested; then a third section is inserted in the MIDDLE.
    store = FakeKnowledgeStore()
    doc_v1 = "# Guide\n\n## Alpha\nalpha text\n\n## Gamma\ngamma text\n"
    doc_v2 = "# Guide\n\n## Alpha\nalpha text\n\n## Beta\nbeta text\n\n## Gamma\ngamma text\n"

    def upsert_diff(text: str):
        chunks = split_markdown("guide.md", "guide.md", text)
        existing = store.existing("guide.md")
        new = [c for c in chunks if existing.get(c.id) != c.content_hash]
        removed = [cid for cid in existing if cid not in {c.id for c in chunks}]
        store.upsert(new)
        store.delete(removed)
        return len(new), len(removed)

    added1, _ = upsert_diff(doc_v1)
    assert added1 == 3                           # intro + Alpha + Gamma
    added2, removed2 = upsert_diff(doc_v2)
    assert added2 == 1 and removed2 == 0         # only inserted Beta is embedded; others untouched


def test_unsupported_format_rejected():
    store = FakeKnowledgeStore()
    store.upsert([Chunk(id="x#1", doc_id="x", text="hi", content_hash="1")])
    assert store.existing("x") == {"x#1": "1"}


# --- Integration: knowledgeSources land in the decision trace ------------------------------
async def _case(sessionmaker, cid: str) -> Case:
    async with sessionmaker() as s:
        return (await s.execute(select(Case).where(Case.correlation_id == cid))).scalar_one()


async def test_decision_trace_carries_knowledge_sources(sessionmaker, graph):
    event = make_event(work_order_id="WO-RAG", reason="part_missing")
    async with sessionmaker() as s:
        await case_service.handle_event(s, event, graph=graph)

    case = await _case(sessionmaker, "WO-RAG")
    sources = case.decision_trace["knowledgeSources"]
    assert sources, "expected grounded knowledgeSources in the trace"
    assert all("source" in s and "link" in s and "snippet" in s for s in sources)
