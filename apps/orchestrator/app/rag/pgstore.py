"""The live knowledge store: Supabase pgvector + Jina embeddings + Jina reranker.

Runs only when real creds are present (the live ingest + smoke test) — unit tests use
FakeKnowledgeStore. It keeps its OWN synchronous engine (psycopg2) so the sync graph nodes can
call `retrieve()` directly; that's separate from the app's async case store, though both point at
the same Supabase Postgres. Build vs buy: embeddings + reranking are LlamaIndex's Jina
integrations; the vector table is plain pgvector in our own DB for transparency.
"""

from __future__ import annotations

import json

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, MetaData, String, Table, Text, create_engine, delete, select, text
from sqlalchemy.dialects.postgresql import JSONB

from app.logging import get_logger
from app.rag.embed import JinaEmbedder
from app.rag.store import Chunk, RetrievedChunk

log = get_logger("rag.pgstore")


class PgVectorKnowledgeStore:
    def __init__(self, database_url: str, jina_api_key: str, *, dim: int = 1024,
                 model: str = "jina-embeddings-v3", reranker: str = "jina-reranker-v1-base-en",
                 rerank_pool: int = 20) -> None:
        # The app stores DATABASE_URL for asyncpg; RAG needs a sync driver.
        sync_url = database_url.replace("+asyncpg", "+psycopg2")
        self._engine = create_engine(sync_url, future=True)
        self._embedder = JinaEmbedder(api_key=jina_api_key, model=model, dim=dim)
        self._reranker_model = reranker
        self._jina_api_key = jina_api_key
        self._rerank_pool = rerank_pool

        md = MetaData()
        self._t = Table(
            "knowledge_chunks", md,
            Column("id", String, primary_key=True),
            Column("doc_id", String, index=True),
            Column("text", Text),
            Column("meta", JSONB),
            Column("embedding", Vector(dim)),
        )
        with self._engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            md.create_all(conn)

    def upsert(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        vectors = self._embedder.embed_documents([c.text for c in chunks])
        with self._engine.begin() as conn:
            for chunk, vec in zip(chunks, vectors, strict=True):
                conn.execute(delete(self._t).where(self._t.c.id == chunk.id))
                conn.execute(self._t.insert().values(
                    id=chunk.id, doc_id=chunk.doc_id, text=chunk.text,
                    meta=chunk.metadata, embedding=vec,
                ))

    def delete(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        with self._engine.begin() as conn:
            conn.execute(delete(self._t).where(self._t.c.id.in_(chunk_ids)))

    def existing(self, doc_id: str) -> dict[str, str]:
        # content_hash is the id suffix after '#', so we recover it without a separate column.
        with self._engine.connect() as conn:
            rows = conn.execute(select(self._t.c.id).where(self._t.c.doc_id == doc_id)).all()
        return {r.id: r.id.split("#", 1)[-1] for r in rows}

    def retrieve(self, query: str, k: int) -> list[RetrievedChunk]:
        q = self._embedder.embed_query(query)
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(self._t.c.id, self._t.c.doc_id, self._t.c.text, self._t.c.meta)
                .order_by(self._t.c.embedding.cosine_distance(q))
                .limit(self._rerank_pool)
            ).all()
        pool = [
            RetrievedChunk(
                Chunk(id=r.id, doc_id=r.doc_id, text=r.text,
                      metadata=r.meta if isinstance(r.meta, dict) else json.loads(r.meta or "{}")),
                score=0.0,
            )
            for r in rows
        ]
        return self._rerank(query, pool, k)

    def _rerank(self, query: str, pool: list[RetrievedChunk], k: int) -> list[RetrievedChunk]:
        """Jina reranker over the vector-search pool → the top k most relevant."""
        if not pool:
            return []
        from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
        from llama_index.postprocessor.jinaai_rerank import JinaRerank

        reranker = JinaRerank(top_n=k, model=self._reranker_model, api_key=self._jina_api_key)
        nodes = [NodeWithScore(node=TextNode(text=rc.chunk.text, id_=rc.chunk.id)) for rc in pool]
        ranked = reranker.postprocess_nodes(nodes, query_bundle=QueryBundle(query))
        by_id = {rc.chunk.id: rc.chunk for rc in pool}
        return [RetrievedChunk(by_id[n.node.id_], float(n.score or 0.0)) for n in ranked]
