import sys

import pytest

from agentic_rag.assembly.context_assembly import assemble
from agentic_rag.config import Settings
from agentic_rag.core.types import Evidence
from agentic_rag.embeddings.local_hash import HashedTfEmbedder
from agentic_rag.retrieval.rerank import CrossEncoderReranker, build_reranker


def _evidence():
    texts = [
        "The Atlas P2 carries up to 450 kg on its standard load deck.",
        "Support tickets are answered within one business day.",
        "Customer sites are spread across twelve countries.",
    ]
    return [
        Evidence(id=f"e{i}", text=text, source_type="vector", source_ref=f"ref{i}", title=f"T{i}",
                 tool_name="vector_search", call_id=1, rank=i)
        for i, text in enumerate(texts)
    ]


class _PrefersSupport:
    """A stand-in cross-encoder with a strong opinion, so the effect is visible."""

    name = "fake"

    def score(self, question, texts):
        return [1.0 if "Support" in text else 0.0 for text in texts]


class _Broken:
    name = "broken"

    def score(self, question, texts):
        raise RuntimeError("model file is corrupt")


def test_no_reranker_by_default():
    assert build_reranker(Settings()) is None


def test_unknown_reranker_is_a_setup_error():
    with pytest.raises(ValueError, match="Unknown RERANKER"):
        build_reranker(Settings(reranker="colbert"))


def test_cross_encoder_without_sentence_transformers_says_what_to_install(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    with pytest.raises(RuntimeError, match=r"pip install -e \"\.\[rerank\]\""):
        build_reranker(Settings(reranker="cross-encoder"))


def test_the_reranker_decides_the_order():
    embedder = HashedTfEmbedder(dim=256)
    question = "What is the payload capacity of the Atlas P2?"
    plain = assemble(question, _evidence(), embedder, Settings())
    reranked = assemble(question, _evidence(), embedder, Settings(), reranker=_PrefersSupport())
    assert "450 kg" in plain[0].text
    assert "Support" in reranked[0].text


def test_a_failing_reranker_falls_back_to_the_embedder(capsys):
    embedder = HashedTfEmbedder(dim=256)
    question = "What is the payload capacity of the Atlas P2?"
    plain = assemble(question, _evidence(), embedder, Settings())
    fallback = assemble(question, _evidence(), embedder, Settings(), reranker=_Broken())
    assert [(e.id, e.fused_score) for e in fallback] == [(e.id, e.fused_score) for e in plain]
    assert "reranker failed" in capsys.readouterr().err


class _Model:
    def __init__(self, values):
        self.values = values

    def predict(self, pairs):
        return self.values[: len(pairs)]


def _reranker_with(values):
    reranker = CrossEncoderReranker.__new__(CrossEncoderReranker)
    reranker._model = _Model(values)
    return reranker


def test_raw_logits_are_squashed_into_zero_to_one():
    scores = _reranker_with([4.0, -4.0]).score("q", ["a", "b"])
    assert 0.98 < scores[0] < 1.0 and 0.0 < scores[1] < 0.02


def test_scores_already_in_zero_to_one_are_kept():
    assert _reranker_with([0.9, 0.1]).score("q", ["a", "b"]) == [0.9, 0.1]
