"""Multi-vector page retrieval, ColBERT style.

A page is not one embedding here. It is a bag of patch embeddings, one
per region of the rendered page, and a query is a bag of token
embeddings. The score between them is MaxSim: for every query token take
its best matching patch, then sum. That is what lets a query about "the
revenue bar chart" land on the patch that holds the chart rather than
being averaged away by the rest of the page.

The maths lives here, separately from any model, so it can be tested
without torch and so a different encoder can be dropped in without
touching retrieval.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class PageRecord:
    id: str
    doc_id: str
    title: str
    source_path: str
    page_number: int
    image_path: str
    description: str = ""


def maxsim(query_vectors: np.ndarray, page_vectors: np.ndarray) -> float:
    """Sum over query tokens of the best match against any page patch.

    query_vectors: (tokens, dim), page_vectors: (patches, dim), both
    expected to be L2 normalised so the dot product is a cosine.
    """
    if query_vectors.size == 0 or page_vectors.size == 0:
        return 0.0
    similarity = query_vectors @ page_vectors.T  # (tokens, patches)
    return float(similarity.max(axis=1).sum())


def normalise(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.clip(norms, 1e-12, None)


class PageIndex:
    """Page records plus their patch embeddings, saved next to the text index.

    Embeddings are stored one .npy per page rather than one big matrix,
    because pages have different patch counts and a ragged array would
    have to be padded.
    """

    def __init__(self, directory: Path | str):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._records: list[PageRecord] = []
        self._vectors: dict[str, np.ndarray] = {}
        self._load()

    @property
    def manifest_path(self) -> Path:
        return self.directory / "pages.jsonl"

    def _load(self) -> None:
        if not self.manifest_path.exists():
            return
        try:
            for line in self.manifest_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._records.append(PageRecord(**json.loads(line)))
        except (json.JSONDecodeError, TypeError, OSError) as exc:
            raise RuntimeError(
                f"Page index at {self.manifest_path} is unreadable ({exc}). "
                "Run `rag reset --yes` and re-ingest."
            ) from exc

    def _save(self) -> None:
        lines = [json.dumps(record.__dict__, ensure_ascii=False) for record in self._records]
        self.manifest_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    @property
    def count(self) -> int:
        return len(self._records)

    def doc_ids(self) -> set[str]:
        return {record.doc_id for record in self._records}

    def add(self, record: PageRecord, vectors: np.ndarray | None = None, flush: bool = True) -> None:
        """Add one page. Pass flush=False while adding a batch, then call save()."""
        self._records.append(record)
        if vectors is not None and vectors.size:
            path = self.directory / f"{_safe(record.id)}.npy"
            np.save(path, normalise(np.asarray(vectors, dtype=np.float32)))
        if flush:
            self._save()

    def save(self) -> None:
        self._save()

    def clear(self) -> None:
        """Wipe every page record, embedding, and rendered image."""
        for path in self.directory.glob("*.npy"):
            path.unlink()
        images = self.directory / "images"
        if images.exists():
            for path in images.glob("*.png"):
                path.unlink()
        if self.manifest_path.exists():
            self.manifest_path.unlink()
        self._records = []
        self._vectors = {}

    def vectors_for(self, page_id: str) -> np.ndarray | None:
        if page_id in self._vectors:
            return self._vectors[page_id]
        path = self.directory / f"{_safe(page_id)}.npy"
        if not path.exists():
            return None
        loaded = np.load(path)
        self._vectors[page_id] = loaded
        return loaded

    def search(self, query_vectors: np.ndarray, k: int = 3) -> list[tuple[PageRecord, float]]:
        """Rank pages by MaxSim. Pages without embeddings are skipped."""
        query_vectors = normalise(np.asarray(query_vectors, dtype=np.float32))
        scored: list[tuple[PageRecord, float]] = []
        for record in self._records:
            vectors = self.vectors_for(record.id)
            if vectors is None:
                continue
            scored.append((record, maxsim(query_vectors, vectors)))
        if not scored:
            return []
        scored.sort(key=lambda pair: -pair[1])
        top = scored[:k]
        best = top[0][1] or 1.0
        return [(record, round(score / best, 4)) for record, score in top]

    def records(self) -> list[PageRecord]:
        return list(self._records)


def _safe(page_id: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in page_id)
