"""Rebuild the vector index and BM25 for documents that are already ingested.

Run this after changing the embedder, for example after switching
EMBEDDINGS_PROVIDER to multilingual, because the vector dimensions change
and the old matrix cannot be reused. Chunk text is read from the index
itself, so the original files do not need to be around.

Usage:  python scripts/reindex.py
Same thing through the CLI:  rag reindex
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentic_rag.retrieval.reindex import reindex  # noqa: E402


def main() -> int:
    result = reindex()
    if result["status"] == "empty":
        print(result["message"])
        return 1
    print("Re-index complete.")
    for key in ("chunks", "documents", "previous_embedder", "embedder", "dim", "bm25_terms", "backup"):
        if result.get(key) not in ("", None):
            print(f"  {key}: {result[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
