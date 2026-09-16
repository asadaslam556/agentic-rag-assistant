"""Sentence-transformers backend (optional dependency)."""

from __future__ import annotations

import numpy as np

from agentic_rag.embeddings.base import Embedder


class SbertEmbedder(Embedder):
    def __init__(self, model_name: str):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "EMBEDDINGS_PROVIDER=sbert requires sentence-transformers. "
                "Install it with: pip install sentence-transformers"
            ) from exc
        self._model = SentenceTransformer(model_name)
        self.name = f"sbert:{model_name}"
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def embed_texts(self, texts: list[str]) -> np.ndarray:  # pragma: no cover
        vectors = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vectors, dtype=np.float32)
