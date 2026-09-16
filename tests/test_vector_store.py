import pytest

from agentic_rag.core.types import Document
from agentic_rag.embeddings.local_hash import HashedTfEmbedder
from agentic_rag.ingestion.chunking import chunk_document
from agentic_rag.retrieval.vector_store import VectorStore


def _chunks():
    doc = Document(
        id="doc1",
        path="specs.md",
        title="Specs",
        text=(
            "The Atlas P2 payload capacity is 450 kg.\n\n"
            "The Scale plan costs 649 EUR per robot per month.\n\n"
            "Deployments take 2 to 6 weeks from survey to go-live."
        ),
    )
    return chunk_document(doc, target_chars=60, overlap_chars=0)


def test_add_search_and_persist_roundtrip(tmp_path):
    embedder = HashedTfEmbedder(dim=256)
    store = VectorStore(tmp_path, embedder)
    added = store.add_chunks(_chunks())
    assert added == store.count > 1
    hits = store.search("payload capacity", k=2)
    assert hits and "450" in hits[0][0].text

    reloaded = VectorStore(tmp_path, HashedTfEmbedder(dim=256))
    assert reloaded.count == store.count
    assert "450" in reloaded.search("payload capacity", k=1)[0][0].text
    assert reloaded.doc_ids() == {"doc1"}


def test_embedder_mismatch_is_rejected(tmp_path):
    store = VectorStore(tmp_path, HashedTfEmbedder(dim=256))
    store.add_chunks(_chunks())
    other = HashedTfEmbedder(dim=256)
    other.name = "different-embedder"
    with pytest.raises(RuntimeError):
        VectorStore(tmp_path, other)


def test_empty_store_returns_no_hits(tmp_path):
    store = VectorStore(tmp_path, HashedTfEmbedder(dim=64))
    assert store.search("anything", k=3) == []


def test_corrupt_manifest_points_at_rag_reset(tmp_path):
    store = VectorStore(tmp_path, HashedTfEmbedder(dim=64))
    doc = Document(id="d1", path="d.md", title="D", text="hello world one two three four")
    store.add_chunks(chunk_document(doc))
    (tmp_path / "manifest.json").write_text("{this is not json")
    try:
        VectorStore(tmp_path, HashedTfEmbedder(dim=64))
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "rag reset" in str(exc)


def test_corrupt_chunks_file_points_at_rag_reset(tmp_path):
    store = VectorStore(tmp_path, HashedTfEmbedder(dim=64))
    doc = Document(id="d1", path="d.md", title="D", text="hello world one two three four")
    store.add_chunks(chunk_document(doc))
    (tmp_path / "chunks.jsonl").write_text('{"broken": \n')
    try:
        VectorStore(tmp_path, HashedTfEmbedder(dim=64))
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "corrupt or unreadable" in str(exc)
