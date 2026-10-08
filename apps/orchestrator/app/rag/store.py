"""The knowledge store seam. Mock-first: FakeKnowledgeStore (in-memory, deterministic) for all
unit tests; PgVectorKnowledgeStore (app/rag/pgstore.py) for the live demo. Both satisfy the same
Protocol so the graph + ingestor don't know or care which is wired.

A Chunk is one retrievable passage with a *content-stable id* (`doc#<hash-of-text>`), so an edit
elsewhere in the document doesn't change this chunk's id — that's what makes incremental re-ingest
touch only what actually changed (see app/rag/ingest.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.rag.embed import DeterministicEmbedder, Embedder


@dataclass
class Chunk:
    id: str
    doc_id: str
    text: str
    metadata: dict = field(default_factory=dict)  # source, locator (page/section), link
    content_hash: str = ""


@dataclass
class RetrievedChunk:
    chunk: Chunk
    score: float


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))  # inputs are L2-normalised already


class KnowledgeStore(Protocol):
    def upsert(self, chunks: list[Chunk]) -> None: ...
    def delete(self, chunk_ids: list[str]) -> None: ...
    def existing(self, doc_id: str) -> dict[str, str]: ...  # {chunk_id: content_hash}
    def retrieve(self, query: str, k: int) -> list[RetrievedChunk]: ...


class FakeKnowledgeStore:
    """In-memory store + deterministic embedder. No network, no infra — the unit-test backend."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        self._embedder = embedder or DeterministicEmbedder()
        self._chunks: dict[str, Chunk] = {}
        self._vectors: dict[str, list[float]] = {}

    def upsert(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        vectors = self._embedder.embed_documents([c.text for c in chunks])
        for chunk, vec in zip(chunks, vectors, strict=True):
            self._chunks[chunk.id] = chunk
            self._vectors[chunk.id] = vec

    def delete(self, chunk_ids: list[str]) -> None:
        for cid in chunk_ids:
            self._chunks.pop(cid, None)
            self._vectors.pop(cid, None)

    def existing(self, doc_id: str) -> dict[str, str]:
        return {c.id: c.content_hash for c in self._chunks.values() if c.doc_id == doc_id}

    def retrieve(self, query: str, k: int) -> list[RetrievedChunk]:
        q = self._embedder.embed_query(query)
        scored = [
            RetrievedChunk(self._chunks[cid], _cosine(q, vec))
            for cid, vec in self._vectors.items()
        ]
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:k]
