"""Ingest the knowledge corpus into the configured store (idempotent, incremental).

Run once after generating/updating the corpus, with real creds in .env for the live pgvector
store:  uv run python scripts/ingest_knowledge.py
Re-running embeds only what changed. With no Jina key it falls back to the in-memory fake (a no-op
for persistence — useful only to eyeball the report).
"""

from __future__ import annotations

from app.config import settings
from app.rag import make_knowledge_store
from app.rag.ingest import ingest_dir


def main() -> None:
    store = make_knowledge_store(settings)
    report = ingest_dir(store, settings.knowledge_corpus_dir)
    print(f"ingested: +{report.added} added, -{report.deleted} deleted, "
          f"{report.unchanged} unchanged  ->  {type(store).__name__}")


if __name__ == "__main__":
    main()
