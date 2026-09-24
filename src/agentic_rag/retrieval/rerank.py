"""Optional cross-encoder reranking for context assembly.

Assembly already rescores every candidate against the question with the
bi-encoder: question and passage are embedded separately, then compared. A
cross-encoder reads the two together in one pass, which is slower but usually
judges relevance more precisely, since it sees how the words of each relate. With RERANKER=cross-encoder its score replaces
the bi-encoder similarity in the fused ranking; rank fusion across tools is
kept, so a strong hit from one tool still counts.

Off by default. It needs sentence-transformers and a model download, and the
offline suite and CI must run without either, so the import is lazy.
"""

from __future__ import annotations

import math

from agentic_rag.config import Settings


class CrossEncoderReranker:
    def __init__(self, model_name: str):
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError(
                "RERANKER=cross-encoder requires sentence-transformers. "
                'Install it with: pip install -e ".[rerank]"'
            ) from exc
        self.name = f"cross-encoder:{model_name}"
        self._model = CrossEncoder(model_name)

    def score(self, question: str, texts: list[str]) -> list[float]:
        """Relevance of each text to the question, in [0, 1]."""
        values = [float(value) for value in self._model.predict([(question, text) for text in texts])]
        # Some sentence-transformers versions already apply a sigmoid for
        # single-label models and some return raw logits. Anything outside
        # [0, 1] is a logit, so squash it the same way.
        if any(value < 0.0 or value > 1.0 for value in values):
            values = [1.0 / (1.0 + math.exp(-value)) for value in values]
        return values


def build_reranker(settings: Settings) -> CrossEncoderReranker | None:
    choice = settings.reranker
    if choice in ("", "none", "off"):
        return None
    if choice == "cross-encoder":
        return CrossEncoderReranker(settings.reranker_model)
    raise ValueError(f"Unknown RERANKER {choice!r}. Use none or cross-encoder.")
