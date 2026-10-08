"""Knowledge layer (RAG): LlamaIndex Jina embeddings + reranker over a pgvector store, behind a
mock-first `KnowledgeStore` seam (build step 4).

`make_knowledge_store` picks the backend from config: real Jina+pgvector when a key is present,
else the in-memory fake (ingested on the spot so local dev still has working retrieval).
"""

from __future__ import annotations

from pathlib import Path

from app.logging import get_logger
from app.rag.ingest import ingest_dir
from app.rag.store import FakeKnowledgeStore, KnowledgeStore

log = get_logger("rag")


def make_knowledge_store(settings) -> KnowledgeStore:
    corpus = Path(settings.knowledge_corpus_dir)
    if settings.jina_api_key and settings.database_url.startswith("postgresql"):
        # Real, persistent store. Ingest is a one-off via scripts/ingest_knowledge.py, not on boot.
        from app.rag.pgstore import PgVectorKnowledgeStore

        log.info("rag.store", backend="pgvector+jina")
        return PgVectorKnowledgeStore(
            settings.database_url, settings.jina_api_key,
            dim=settings.embedding_dim, model=settings.jina_model,
            reranker=settings.jina_reranker,
        )
    # Fake backend: empty until ingested, so ingest the corpus now (cheap, in-memory).
    log.info("rag.store", backend="fake")
    store = FakeKnowledgeStore()
    if corpus.exists():
        ingest_dir(store, corpus)
    return store
