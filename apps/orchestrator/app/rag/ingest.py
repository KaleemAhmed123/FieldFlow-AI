"""The smart ingestor: store-agnostic, idempotent, incremental.

For each file: split into content-stable chunks, then diff against what the store already holds for
that document — embed + upsert only the new/changed chunks, delete the ones that vanished, skip the
unchanged. Re-running with no edits does nothing. Adding N pages anywhere embeds only those N (the
other chunks keep their content-hash ids). This is the "+5 pages in a 20-page doc" guarantee, and
it works identically against the Fake and the pgvector store.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.logging import get_logger
from app.rag.split import split_file
from app.rag.store import KnowledgeStore

log = get_logger("rag.ingest")


@dataclass
class IngestReport:
    added: int = 0
    deleted: int = 0
    unchanged: int = 0


def ingest_dir(store: KnowledgeStore, corpus_dir: Path | str) -> IngestReport:
    corpus_dir = Path(corpus_dir)
    report = IngestReport()
    for path in sorted(corpus_dir.iterdir()):
        if path.suffix.lower() not in (".pdf", ".md", ".csv"):
            continue
        chunks = split_file(path)
        current = {c.id: c for c in chunks}
        existing = store.existing(path.name)  # {chunk_id: content_hash}

        new_or_changed = [c for cid, c in current.items() if existing.get(cid) != c.content_hash]
        removed = [cid for cid in existing if cid not in current]

        store.upsert(new_or_changed)
        store.delete(removed)

        report.added += len(new_or_changed)
        report.deleted += len(removed)
        report.unchanged += len(current) - len(new_or_changed)
        log.info("rag.ingest.doc", doc=path.name, added=len(new_or_changed),
                 deleted=len(removed), total=len(current))
    log.info("rag.ingest.done", added=report.added, deleted=report.deleted,
             unchanged=report.unchanged)
    return report
