"""Hybrid retrieval: vector similarity fused with BM25 keyword scores.

Both retrievers rank the corpus independently and the lists are merged
with reciprocal rank fusion, the same technique context assembly uses
across tools. Semantic recall catches paraphrases, BM25 catches exact
terms like SKUs and standard numbers, and RRF needs no score
calibration between the two. The searcher exposes the same interface
as the vector store (count, search), so the vector_search tool works
unchanged in any mode.
"""

from __future__ import annotations

import threading

from agentic_rag.core.types import Chunk
from agentic_rag.retrieval.bm25 import BM25Index
from agentic_rag.retrieval.vector_store import VectorStore

_RRF_K = 60


class HybridSearcher:
    def __init__(self, store: VectorStore, mode: str = "hybrid"):
        self.store = store
        self.mode = mode if mode in {"hybrid", "vector", "bm25"} else "hybrid"
        self._bm25: BM25Index | None = None
        self._bm25_count = -1
        # branches search this object from several threads at once, and the
        # lazy build below is a read-modify-write of two fields
        self._bm25_lock = threading.Lock()

    @property
    def count(self) -> int:
        return self.store.count

    def _bm25_index(self) -> BM25Index:
        with self._bm25_lock:
            if self._bm25 is None or self._bm25_count != self.store.count:
                self._bm25 = BM25Index(self.store.chunks())
                self._bm25_count = self.store.count
            return self._bm25

    def search(self, query: str, k: int = 5) -> list[tuple[Chunk, float]]:
        if self.store.count == 0:
            return []
        if self.mode == "vector":
            return self.store.search(query, k=k)

        chunks = self.store.chunks()
        keyword_hits = self._bm25_index().search(query, k=max(k, 8))

        if self.mode == "bm25":
            top = keyword_hits[:k]
            if not top:
                return []
            best = top[0][1] or 1.0
            return [(chunks[index], round(score / best, 4)) for index, score in top]

        vector_hits = self.store.search(query, k=max(k, 8))
        fused: dict[str, float] = {}
        by_id: dict[str, Chunk] = {}
        for rank, (chunk, _score) in enumerate(vector_hits):
            by_id[chunk.id] = chunk
            fused[chunk.id] = fused.get(chunk.id, 0.0) + 1.0 / (_RRF_K + rank)
        for rank, (index, _score) in enumerate(keyword_hits):
            chunk = chunks[index]
            by_id[chunk.id] = chunk
            fused[chunk.id] = fused.get(chunk.id, 0.0) + 1.0 / (_RRF_K + rank)
        ordered = sorted(fused.items(), key=lambda pair: -pair[1])[:k]
        best = ordered[0][1]
        return [(by_id[chunk_id], round(score / best, 4)) for chunk_id, score in ordered]
