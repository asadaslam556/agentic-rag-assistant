"""Embedder interface. All backends return L2-normalized float32 vectors."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class Embedder(ABC):
    name: str = "base"
    dim: int = 0

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> np.ndarray:
        """Return an (n, dim) L2-normalized float32 matrix."""

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_texts([text])[0]


def l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return (matrix / norms).astype(np.float32)
