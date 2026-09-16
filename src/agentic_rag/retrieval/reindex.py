"""Rebuild the index for documents already ingested.

Needed when the embedder changes, since the vectors then have a
different dimension and the store refuses to load a mismatched index
rather than return nonsense. Chunk text comes from chunks.jsonl, so the
source files need not be present, and chunk ids are preserved so
citations still line up.

BM25 needs no separate step: it is built in memory from the same chunks
on the next search. It is exercised here as a check.

Entry points: `rag reindex`, or `python scripts/reindex.py`.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from agentic_rag.config import Settings
from agentic_rag.core.types import Chunk
from agentic_rag.embeddings import get_embedder
from agentic_rag.retrieval.bm25 import BM25Index
from agentic_rag.retrieval.vector_store import VectorStore

_VECTORS_FILE = "vectors.npy"
_CHUNKS_FILE = "chunks.jsonl"
_MANIFEST_FILE = "manifest.json"

# Chunks are re-embedded in batches so a large corpus does not have to fit
# in one call to the model.
_BATCH = 256


def read_chunks(index_dir: Path) -> list[Chunk]:
    """Load stored chunks directly, bypassing the embedder guard.

    VectorStore raises when the manifest names a different embedder, which
    is exactly the situation a rebuild is for, so the file is read here
    instead of going through the store.
    """
    chunks_path = index_dir / _CHUNKS_FILE
    if not chunks_path.exists():
        return []
    chunks: list[Chunk] = []
    with chunks_path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                chunks.append(Chunk(**json.loads(line)))
    return chunks


def reindex(settings: Settings | None = None, keep_backup: bool = True) -> dict:
    """Re-embed every stored chunk with the currently configured embedder."""
    settings = settings or Settings.from_env()
    index_dir = settings.index_path
    chunks = read_chunks(index_dir)
    if not chunks:
        return {
            "status": "empty",
            "chunks": 0,
            "message": f"No chunks found in {index_dir}. Run `rag ingest` first.",
        }

    embedder = get_embedder(settings)
    previous = ""
    manifest_path = index_dir / _MANIFEST_FILE
    if manifest_path.exists():
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8")).get("embedder", "")
        except (json.JSONDecodeError, OSError):
            previous = ""

    backup = index_dir / f"{_CHUNKS_FILE}.bak"
    if keep_backup:
        shutil.copy2(index_dir / _CHUNKS_FILE, backup)

    # Clear the old files so the store loads empty instead of tripping the
    # embedder guard on the way in.
    for name in (_VECTORS_FILE, _CHUNKS_FILE, _MANIFEST_FILE):
        path = index_dir / name
        if path.exists():
            path.unlink()

    store = VectorStore(index_dir, embedder)
    for start in range(0, len(chunks), _BATCH):
        store.add_chunks(chunks[start : start + _BATCH])

    # Rebuilding BM25 here is a check, not a save: it lives in memory and is
    # built from these same chunks whenever a search runs.
    bm25_terms = len(BM25Index(store.chunks())._idf)

    return {
        "status": "ok",
        "chunks": store.count,
        "documents": len(store.doc_ids()),
        "previous_embedder": previous,
        "embedder": embedder.name,
        "dim": embedder.dim,
        "bm25_terms": bm25_terms,
        "backup": str(backup) if keep_backup else "",
    }
