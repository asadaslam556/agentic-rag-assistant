"""Pure-Python BM25 (Okapi) over chunk tokens.

Rebuilt in memory from the stored chunks, which is instant at the corpus
sizes this project targets and keeps the on-disk format unchanged. Used
by the hybrid searcher to catch exact terms (SKUs, standard numbers,
rare names) that embedding similarity can miss.
"""

from __future__ import annotations

import math
from collections import Counter

from agentic_rag.core.textutils import tokenize
from agentic_rag.core.types import Chunk

_K1 = 1.5
_B = 0.75


class BM25Index:
    def __init__(self, chunks: list[Chunk]):
        self._docs = [tokenize(chunk.text) for chunk in chunks]
        self._doc_len = [len(doc) for doc in self._docs]
        self._avg_len = (sum(self._doc_len) / len(self._docs)) if self._docs else 0.0
        self._tf = [Counter(doc) for doc in self._docs]
        document_frequency: Counter = Counter()
        for tf in self._tf:
            document_frequency.update(tf.keys())
        n = len(self._docs)
        self._idf = {
            term: math.log(1 + (n - freq + 0.5) / (freq + 0.5))
            for term, freq in document_frequency.items()
        }

    def search(self, query: str, k: int = 5) -> list[tuple[int, float]]:
        """Top-k (chunk_index, score) pairs with score > 0."""
        query_tokens = tokenize(query)
        if not query_tokens or not self._docs:
            return []
        scored: list[tuple[int, float]] = []
        for index, tf in enumerate(self._tf):
            score = 0.0
            length = self._doc_len[index] or 1
            for term in query_tokens:
                frequency = tf.get(term)
                if not frequency:
                    continue
                normaliser = frequency + _K1 * (1 - _B + _B * length / (self._avg_len or 1))
                score += self._idf.get(term, 0.0) * frequency * (_K1 + 1) / normaliser
            if score > 0:
                scored.append((index, score))
        scored.sort(key=lambda pair: -pair[1])
        return scored[:k]
