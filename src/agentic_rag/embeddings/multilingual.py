"""Multilingual sentence-transformers backend (optional dependency).

Defaults to intfloat/multilingual-e5-small: 470 MB, 384 dimensions, ~100
languages. Set MULTILINGUAL_EMBEDDING_MODEL for anything else.

The e5 family wants a "query: " or "passage: " prefix and degrades
without one, so this adds them; other models are used as they are.

The reported name includes the model, so the store manifest will refuse
an index built by a different embedder. Switching here needs
`rag reindex`.
"""

from __future__ import annotations

import numpy as np

from agentic_rag.embeddings.base import Embedder

_QUERY_PREFIX = "query: "
_PASSAGE_PREFIX = "passage: "


def _is_e5(model_name: str) -> bool:
    return "e5" in model_name.lower()


class MultilingualEmbedder(Embedder):
    def __init__(self, model_name: str):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "EMBEDDINGS_PROVIDER=multilingual requires sentence-transformers. "
                "Install it with: pip install sentence-transformers"
            ) from exc
        self._model = SentenceTransformer(model_name)
        self._use_prefixes = _is_e5(model_name)
        self.name = f"multilingual:{model_name}"
        # sentence-transformers 6 renamed this; the old name still works but
        # warns, and will eventually go
        get_dim = getattr(
            self._model, "get_embedding_dimension", None
        ) or self._model.get_sentence_embedding_dimension
        self.dim = int(get_dim())

    def _encode(self, texts: list[str]) -> np.ndarray:  # pragma: no cover
        vectors = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vectors, dtype=np.float32)

    def embed_texts(self, texts: list[str]) -> np.ndarray:  # pragma: no cover
        if self._use_prefixes:
            texts = [_PASSAGE_PREFIX + text for text in texts]
        return self._encode(texts)

    def embed_query(self, text: str) -> np.ndarray:  # pragma: no cover
        if self._use_prefixes:
            text = _QUERY_PREFIX + text
        return self._encode([text])[0]
