"""Embedders behind one Protocol, so the store is model-agnostic (swap = config, not code).

- DeterministicEmbedder — a tiny token-hashing embedder. No network, no key, fully deterministic.
  Used by the FakeKnowledgeStore in unit tests: cosine similarity reflects token overlap, so a
  query about "PCB-492 fault" retrieves the control-board chunk. Not for production quality.
- JinaEmbedder — the real hosted embeddings (LlamaIndex's Jina integration). Used live only.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

_TOKEN = re.compile(r"[a-z0-9\-]+")


class Embedder(Protocol):
    dim: int
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class DeterministicEmbedder:
    """Token-hashing bag-of-words → L2-normalised vector. Deterministic, offline, test-only."""

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in _tokens(text):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)  # noqa: S324 - not security, just hashing
            v[h % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


class JinaEmbedder:
    """Real hosted embeddings via LlamaIndex's Jina integration. Live path only (needs a key)."""

    def __init__(self, api_key: str, model: str = "jina-embeddings-v3", dim: int = 1024) -> None:
        from llama_index.embeddings.jinaai import JinaEmbedding

        self.dim = dim
        self._emb = JinaEmbedding(api_key=api_key, model=model)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._emb.get_text_embedding_batch(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._emb.get_query_embedding(text)
