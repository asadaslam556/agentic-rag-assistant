"""BM25 and hybrid retrieval, fully offline and deterministic."""

from agentic_rag.core.types import Document
from agentic_rag.embeddings.local_hash import HashedTfEmbedder
from agentic_rag.ingestion.chunking import chunk_document
from agentic_rag.retrieval.bm25 import BM25Index
from agentic_rag.retrieval.hybrid import HybridSearcher
from agentic_rag.retrieval.vector_store import VectorStore


def _store(tmp_path):
    doc = Document(
        id="doc1",
        path="mixed.md",
        title="Mixed",
        text=(
            "The Atlas platform is certified to the ISO 3691-4:2023 safety standard.\n\n"
            "Robots move pallets between storage zones all day long.\n\n"
            "The Scale plan includes a technical account manager and analytics."
        ),
    )
    store = VectorStore(tmp_path, HashedTfEmbedder(dim=256))
    store.add_chunks(chunk_document(doc, target_chars=70, overlap_chars=0))
    return store


def test_bm25_ranks_exact_terms_first(tmp_path):
    store = _store(tmp_path)
    index = BM25Index(store.chunks())
    hits = index.search("ISO 3691-4 safety standard", k=3)
    assert hits, "expected keyword hits"
    top_chunk = store.chunks()[hits[0][0]]
    assert "3691" in top_chunk.text
    assert index.search("completely unrelated zebra query", k=3)[:0] == []


def test_hybrid_finds_exact_terms_and_returns_normalized_scores(tmp_path):
    searcher = HybridSearcher(_store(tmp_path), "hybrid")
    hits = searcher.search("ISO 3691-4 certification", k=2)
    assert "3691" in hits[0][0].text
    assert hits[0][1] == 1.0
    assert all(0 < score <= 1.0 for _chunk, score in hits)


def test_modes_share_one_interface(tmp_path):
    store = _store(tmp_path)
    for mode in ("vector", "bm25", "hybrid"):
        searcher = HybridSearcher(store, mode)
        assert searcher.count == store.count
        hits = searcher.search("safety standard", k=2)
        assert hits and hasattr(hits[0][0], "text")


def test_index_rebuilds_after_new_chunks(tmp_path):
    store = _store(tmp_path)
    searcher = HybridSearcher(store, "bm25")
    assert not searcher.search("gripper attachment torque", k=2)
    extra = Document(id="doc2", path="extra.md", title="Extra",
                     text="The optional gripper attachment adds 40 Nm of torque.")
    store.add_chunks(chunk_document(extra))
    hits = searcher.search("gripper attachment torque", k=2)
    assert hits and "gripper" in hits[0][0].text
