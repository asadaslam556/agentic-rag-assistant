"""Dependency-free hashed TF embedder.

Uses the hashing trick: every token (and its character trigrams, at a
lower weight) is hashed into a fixed-size vector with a deterministic
sign, weighted by sublinear term frequency, then L2-normalized. This is
not a neural embedding, but it is deterministic, instant, offline, and
strong enough for keyword-heavy retrieval over small corpora, which
makes the demo, the tests, and CI run with zero model downloads.

Swap in `sbert`, `multilingual`, or `openai` via EMBEDDINGS_PROVIDER for
semantic search quality on real workloads.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter

import numpy as np

from agentic_rag.core.textutils import tokenize
from agentic_rag.embeddings.base import Embedder, l2_normalize


def _bucket(token: str, dim: int) -> tuple[int, float]:
    digest = hashlib.md5(token.encode("utf-8")).digest()
    index = int.from_bytes(digest[:4], "big") % dim
    sign = 1.0 if digest[4] % 2 == 0 else -1.0
    return index, sign


class HashedTfEmbedder(Embedder):
    name = "local-hash-v1"

    def __init__(self, dim: int = 768):
        self.dim = dim

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            counts: Counter[str] = Counter()
            for token in tokenize(text):
                counts[token] += 1
                if len(token) >= 5:  # trigrams catch plurals and small spelling drift
                    for i in range(len(token) - 2):
                        counts[f"cg:{token[i:i + 3]}"] += 1
            for token, count in counts.items():
                weight = 1.0 + math.log(count)
                if token.startswith("cg:"):
                    weight *= 0.4
                index, sign = _bucket(token, self.dim)
                matrix[row, index] += sign * weight
        return l2_normalize(matrix)
