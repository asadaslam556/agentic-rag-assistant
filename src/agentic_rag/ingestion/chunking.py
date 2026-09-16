"""Chunking strategies.

Two splitters, picked with CHUNK_STRATEGY. "structure" is the default
and the better one for documents with headings. "length" is the plain
fixed-window fallback, useful for transcripts, logs, and anything else
with no structure to respect.

The structure-aware splitter:

Documents are split into paragraphs, paragraphs into sentences, and
sentences are greedily packed into chunks of roughly
``chunk_target_chars`` characters. A tail of the previous chunk
(``chunk_overlap_chars``) is prepended to the next one so facts on a
boundary are never lost. Markdown headings are tracked and stored on
each chunk, which makes citations readable ("Pricing > Scale plan"
instead of "chunk 7").
"""

from __future__ import annotations

import re

from agentic_rag.core.textutils import split_sentences
from agentic_rag.core.types import Chunk, Document

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def _segments(text: str) -> list[tuple[str, str]]:
    """Yield (heading, paragraph) pairs, tracking the current heading."""
    segments: list[tuple[str, str]] = []
    heading = ""
    for block in re.split(r"\n{2,}", text):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        body: list[str] = []
        for line in lines:
            match = _HEADING.match(line.strip())
            if match:
                if body:
                    segments.append((heading, " ".join(body)))
                    body = []
                heading = match.group(2).strip()
            else:
                body.append(line.strip())
        if body:
            segments.append((heading, " ".join(body)))
    return segments


def chunk_document(
    doc: Document, target_chars: int = 900, overlap_chars: int = 150
) -> list[Chunk]:
    chunks: list[Chunk] = []
    position = 0
    buffer: list[str] = []
    buffer_len = 0
    buffer_heading = ""

    def flush(next_heading: str) -> None:
        nonlocal buffer, buffer_len, position, buffer_heading
        if not buffer:
            buffer_heading = next_heading
            return
        text = " ".join(buffer).strip()
        chunks.append(
            Chunk(
                id=f"{doc.id}:{position}",
                doc_id=doc.id,
                text=text,
                title=doc.title,
                heading=buffer_heading,
                position=position,
                source_path=doc.path,
            )
        )
        position += 1
        # keep an overlap tail so boundary facts appear in both chunks
        tail: list[str] = []
        tail_len = 0
        for sentence in reversed(buffer):
            if tail_len + len(sentence) > overlap_chars:
                break
            tail.insert(0, sentence)
            tail_len += len(sentence) + 1
        buffer = tail
        buffer_len = tail_len
        buffer_heading = next_heading

    for heading, paragraph in _segments(doc.text):
        if heading != buffer_heading and buffer_len > overlap_chars:
            flush(heading)
        buffer_heading = buffer_heading or heading
        for sentence in split_sentences(paragraph):
            if buffer_len + len(sentence) > target_chars and buffer:
                flush(heading)
            buffer.append(sentence)
            buffer_len += len(sentence) + 1
        buffer_heading = heading if not buffer else buffer_heading
    flush("")
    return chunks


def chunk_document_by_length(
    doc: Document, target_chars: int = 900, overlap_chars: int = 150
) -> list[Chunk]:
    """Fixed-size windows with overlap, ignoring structure.

    Sentence boundaries are still respected where one falls inside the
    window, so chunks rarely end mid-word. Use this for text with no
    headings to speak of.
    """
    text = " ".join(doc.text.split())
    if not text:
        return []
    chunks: list[Chunk] = []
    step = max(1, target_chars - max(0, overlap_chars))
    position = 0
    start = 0
    while start < len(text):
        window = text[start : start + target_chars]
        if start + target_chars < len(text):
            # back off to the last sentence end so the window closes cleanly
            cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
            if cut > target_chars // 2:
                window = window[: cut + 1]
        body = window.strip()
        if body:
            chunks.append(
                Chunk(
                    id=f"{doc.id}#chunk{position}",
                    doc_id=doc.id,
                    text=body,
                    title=doc.title,
                    heading="",
                    position=position,
                    source_path=doc.path,
                )
            )
            position += 1
        start += max(step, len(window) - max(0, overlap_chars)) if len(window) > overlap_chars else step
    return chunks


def get_chunker(strategy: str = "structure"):
    """Return the splitter named by CHUNK_STRATEGY, defaulting to structure."""
    return chunk_document_by_length if strategy == "length" else chunk_document
