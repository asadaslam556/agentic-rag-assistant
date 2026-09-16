from pathlib import Path

from agentic_rag.core.types import Document
from agentic_rag.ingestion.chunking import chunk_document
from agentic_rag.ingestion.loaders import load_document

ROOT = Path(__file__).resolve().parents[1]


def _doc(text: str) -> Document:
    return Document(id="d1", path="test.md", title="Test", text=text)


def test_small_document_yields_single_chunk():
    chunks = chunk_document(_doc("One short paragraph about robots."))
    assert len(chunks) == 1
    assert chunks[0].position == 0
    assert "robots" in chunks[0].text


def test_long_document_splits_with_overlap():
    sentences = " ".join(f"Fact number {i} lives in this sentence about warehouses." for i in range(60))
    chunks = chunk_document(_doc(sentences), target_chars=400, overlap_chars=120)
    assert len(chunks) > 3
    assert [c.position for c in chunks] == list(range(len(chunks)))
    # every chunk stays near the target size (single sentences are never split)
    assert all(len(c.text) <= 400 + 120 for c in chunks)
    # overlap: the start of each chunk repeats the tail of the previous one
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert current.text[:40] in previous.text


def test_markdown_headings_are_tracked():
    doc = load_document(ROOT / "data" / "sample_docs" / "atlas_platform.md")
    chunks = chunk_document(doc)
    headings = {c.heading for c in chunks}
    assert "Key specifications" in headings
    assert all(c.title == "Atlas P2 platform" for c in chunks)


def test_length_chunker_covers_the_text_without_losing_words():
    from agentic_rag.ingestion.chunking import chunk_document_by_length

    body = " ".join(f"Sentence number {i} about warehouse robots." for i in range(80))
    doc = Document(id="d1", path="d.md", title="D", text=body)
    chunks = chunk_document_by_length(doc, target_chars=300, overlap_chars=50)
    assert len(chunks) > 3
    assert all(chunk.text.strip() for chunk in chunks)
    assert len({chunk.id for chunk in chunks}) == len(chunks)
    joined = " ".join(chunk.text for chunk in chunks)
    for probe in ("Sentence number 0", "Sentence number 40", "Sentence number 79"):
        assert probe in joined, f"{probe} was dropped"


def test_length_chunker_handles_short_and_empty_documents():
    from agentic_rag.ingestion.chunking import chunk_document_by_length

    assert chunk_document_by_length(Document(id="e", path="e.md", title="E", text="   ")) == []
    short = chunk_document_by_length(Document(id="s", path="s.md", title="S", text="One line only."))
    assert len(short) == 1 and short[0].text == "One line only."


def test_strategy_selector_returns_the_right_splitter():
    from agentic_rag.ingestion.chunking import chunk_document, chunk_document_by_length, get_chunker

    assert get_chunker("length") is chunk_document_by_length
    assert get_chunker("structure") is chunk_document
    assert get_chunker("anything-else") is chunk_document
