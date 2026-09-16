"""OpenAI-compatible /embeddings backend."""

from __future__ import annotations

import numpy as np

from agentic_rag.config import Settings
from agentic_rag.core.http import post_json
from agentic_rag.embeddings.base import Embedder, l2_normalize


class OpenAIEmbedder(Embedder):
    def __init__(self, settings: Settings):
        if not settings.openai_api_key:
            raise RuntimeError("EMBEDDINGS_PROVIDER=openai requires OPENAI_API_KEY.")
        self._settings = settings
        self.name = f"openai:{settings.openai_embedding_model}"
        self.dim = 0  # discovered on first call

    def embed_texts(self, texts: list[str]) -> np.ndarray:  # pragma: no cover
        s = self._settings
        response = post_json(
            f"{s.openai_base_url}/embeddings",
            {"model": s.openai_embedding_model, "input": texts},
            headers={"Authorization": f"Bearer {s.openai_api_key}", **s.llm_extra_headers},
            timeout=s.request_timeout,
        )
        rows = sorted(response["data"], key=lambda item: item["index"])
        matrix = np.asarray([row["embedding"] for row in rows], dtype=np.float32)
        self.dim = matrix.shape[1]
        return l2_normalize(matrix)
