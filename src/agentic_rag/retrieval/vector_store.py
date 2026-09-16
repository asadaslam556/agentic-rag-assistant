"""A small persistent vector store built on NumPy.

Design goals: transparent on-disk format (a .npy matrix plus a JSONL
metadata file and a manifest), exact cosine top-k search, and a guard
that refuses to mix indexes built with different embedders. For corpora
in the tens of thousands of chunks this is fast and has zero moving
parts; the interface is intentionally small so a pgvector, Qdrant, or
Chroma backend can be dropped in behind it.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from agentic_rag.core.types import Chunk
from agentic_rag.embeddings.base import Embedder

_VECTORS_FILE = "vectors.npy"
_CHUNKS_FILE = "chunks.jsonl"
_MANIFEST_FILE = "manifest.json"


class VectorStore:
    def __init__(self, directory: Path, embedder: Embedder):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder
        self._vectors: np.ndarray | None = None
        self._chunks: list[Chunk] = []
        self._load()

    # ------------------------------------------------------------ persistence

    def _load(self) -> None:
        manifest_path = self.directory / _MANIFEST_FILE
        vectors_path = self.directory / _VECTORS_FILE
        chunks_path = self.directory / _CHUNKS_FILE
        if not manifest_path.exists() or not vectors_path.exists():
            return
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(
                f"Index manifest at {manifest_path} is unreadable ({exc}). "
                "Run `rag reset --yes` and re-ingest."
            ) from exc
        if manifest.get("embedder") != self.embedder.name:
            raise RuntimeError(
                f"Index at {self.directory} was built with embedder "
                f"{manifest.get('embedder')!r} but the current embedder is "
                f"{self.embedder.name!r}. Run `rag reset` and re-ingest."
            )
        try:
            self._vectors = np.load(vectors_path)
            self._chunks = []
            with chunks_path.open(encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        self._chunks.append(Chunk(**json.loads(line)))
        except (json.JSONDecodeError, ValueError, TypeError, KeyError, OSError) as exc:
            raise RuntimeError(
                f"Index at {self.directory} is corrupt or unreadable ({exc}). "
                "Run `rag reset --yes` and re-ingest."
            ) from exc

    def _save(self) -> None:
        assert self._vectors is not None
        np.save(self.directory / _VECTORS_FILE, self._vectors)
        with (self.directory / _CHUNKS_FILE).open("w", encoding="utf-8") as handle:
            for chunk in self._chunks:
                handle.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")
        manifest = {
            "embedder": self.embedder.name,
            "dim": int(self._vectors.shape[1]),
            "count": len(self._chunks),
        }
        (self.directory / _MANIFEST_FILE).write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------- operations

    @property
    def count(self) -> int:
        return len(self._chunks)

    def doc_ids(self) -> set[str]:
        return {chunk.doc_id for chunk in self._chunks}

    def chunks(self) -> list[Chunk]:
        return list(self._chunks)

    def add_chunks(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        new_vectors = self.embedder.embed_texts([c.text for c in chunks])
        if self._vectors is None or self._vectors.size == 0:
            self._vectors = new_vectors
        else:
            if self._vectors.shape[1] != new_vectors.shape[1]:
                raise RuntimeError("Embedding dimension changed; run `rag reset` and re-ingest.")
            self._vectors = np.vstack([self._vectors, new_vectors])
        self._chunks.extend(chunks)
        self._save()
        return len(chunks)

    def search(self, query: str, k: int = 5) -> list[tuple[Chunk, float]]:
        if self._vectors is None or self.count == 0:
            return []
        query_vector = self.embedder.embed_query(query)
        scores = self._vectors @ query_vector  # cosine: everything is L2-normalized
        k = min(k, self.count)
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [(self._chunks[i], float(scores[i])) for i in top]

    def clear(self) -> None:
        for name in (_VECTORS_FILE, _CHUNKS_FILE, _MANIFEST_FILE):
            path = self.directory / name
            if path.exists():
                path.unlink()
        self._vectors = None
        self._chunks = []

    def stats(self) -> dict:
        docs = {c.doc_id for c in self._chunks}
        return {
            "chunks": self.count,
            "documents": len(docs),
            "embedder": self.embedder.name,
            "directory": str(self.directory),
        }
