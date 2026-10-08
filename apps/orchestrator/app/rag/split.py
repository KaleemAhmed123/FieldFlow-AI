"""Structure-aware splitters, one per format. Splitting on structure (heading / page / row) — not
a blind sliding window — is what keeps re-ingest incremental: inserting text in one section adds a
new chunk there and leaves every other chunk's text (and therefore its content-stable id) untouched.

Each chunk gets a content-stable id `doc#<sha1(text)[:12]>` + the same hash, and citation metadata
(source filename, a human locator, a link) pulled from the document.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from pathlib import Path

from app.rag.store import Chunk

_LINK = re.compile(r"https?://\S+")


def _chunk(doc_id: str, text: str, *, source: str, locator: str, link: str) -> Chunk:
    text = text.strip()
    h = hashlib.sha1(text.encode()).hexdigest()[:12]  # noqa: S324 - id/dedup, not security
    return Chunk(
        id=f"{doc_id}#{h}",
        doc_id=doc_id,
        text=text,
        metadata={"source": source, "locator": locator, "link": link},
        content_hash=h,
    )


def _link_in(text: str, default: str) -> str:
    m = _LINK.search(text)
    return m.group(0) if m else default


def split_markdown(doc_id: str, source: str, text: str) -> list[Chunk]:
    """One chunk per `##` section (the intro before the first `##` is its own chunk)."""
    link = _link_in(text, f"knowledge://{source}")
    parts = re.split(r"(?m)^##\s+", text)
    chunks: list[Chunk] = []
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        title = "intro" if i == 0 else part.splitlines()[0]
        chunks.append(_chunk(doc_id, part, source=source, locator=f"section: {title}", link=link))
    return chunks


def split_csv(doc_id: str, source: str, text: str) -> list[Chunk]:
    """One chunk per row, rendered as a readable sentence for better retrieval."""
    reader = csv.DictReader(io.StringIO(text))
    chunks: list[Chunk] = []
    for n, row in enumerate(reader, start=1):
        sentence = "; ".join(f"{k}={v}" for k, v in row.items())
        chunks.append(_chunk(doc_id, sentence, source=source, locator=f"row {n}",
                             link=f"knowledge://{source}#row{n}"))
    return chunks


def split_pdf(doc_id: str, source: str, path: Path) -> list[Chunk]:
    """One chunk per page (the PDFs are authored page-structured)."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    chunks: list[Chunk] = []
    for n, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if not text:
            continue
        link = _link_in(text, f"knowledge://{source}")
        chunks.append(_chunk(doc_id, text, source=source, locator=f"page {n}", link=link))
    return chunks


def split_file(path: Path) -> list[Chunk]:
    """Dispatch on extension. doc_id = the filename (stable across re-ingests)."""
    doc_id = path.name
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return split_pdf(doc_id, path.name, path)
    text = path.read_text(encoding="utf-8")
    if suffix == ".md":
        return split_markdown(doc_id, path.name, text)
    if suffix == ".csv":
        return split_csv(doc_id, path.name, text)
    raise ValueError(f"unsupported knowledge format: {path.name}")
