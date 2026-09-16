"""Page-image retrieval: late interaction maths, both ranking paths, and the demo PDF."""

from pathlib import Path

import numpy as np

from agentic_rag.config import Settings
from agentic_rag.retrieval.late_interaction import PageIndex, PageRecord, maxsim, normalise
from agentic_rag.tools.visual_search import VisualSearchTool

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PDF = ROOT / "data" / "sample_pdfs" / "auralis-quarterly-review.pdf"


# ------------------------------------------------------------ late interaction


def test_maxsim_rewards_the_page_holding_the_matching_patch():
    query = normalise(np.array([[1.0, 0.0], [0.0, 1.0]]))
    covers_both = normalise(np.array([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]))
    covers_one = normalise(np.array([[1.0, 0.0], [0.9, 0.1]]))
    assert maxsim(query, covers_both) > maxsim(query, covers_one)


def test_maxsim_is_defined_for_empty_input():
    assert maxsim(np.zeros((0, 4)), np.ones((3, 4))) == 0.0
    assert maxsim(np.ones((2, 4)), np.zeros((0, 4))) == 0.0


def _index(tmp_path):
    index = PageIndex(tmp_path)
    index.add(
        PageRecord("d#page1", "d", "Doc", "d.pdf", 1, str(tmp_path / "p1.png"), "a bar chart of revenue"),
        np.array([[1.0, 0.0]]),
    )
    index.add(
        PageRecord("d#page2", "d", "Doc", "d.pdf", 2, str(tmp_path / "p2.png"), "a table of regions"),
        np.array([[0.0, 1.0]]),
    )
    return index


def test_page_index_ranks_and_survives_a_reload(tmp_path):
    index = _index(tmp_path)
    hits = index.search(np.array([[1.0, 0.05]]), k=2)
    assert hits[0][0].id == "d#page1"
    assert hits[0][1] == 1.0

    reloaded = PageIndex(tmp_path)
    assert reloaded.count == 2
    assert reloaded.vectors_for("d#page1") is not None
    assert reloaded.doc_ids() == {"d"}


def test_a_corrupt_page_manifest_points_at_rag_reset(tmp_path):
    _index(tmp_path)
    (tmp_path / "pages.jsonl").write_text("{not json")
    try:
        PageIndex(tmp_path)
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "rag reset" in str(exc)


# ----------------------------------------------------------------- the tool


class FakeEncoder:
    """Query embedding always points at page two."""

    def embed_query(self, query):
        return np.array([[0.0, 1.0]])


def test_colpali_path_ranks_by_page_embedding(tmp_path):
    tool = VisualSearchTool(_index(tmp_path), encoder=FakeEncoder())
    result = tool.run(query="anything at all")
    assert result.evidence[0].id == "d#page2"
    assert result.evidence[0].source_type == "page"
    assert result.evidence[0].image_path.endswith("p2.png")
    assert "page 2" in result.observation


def test_description_path_ranks_without_an_encoder(tmp_path):
    tool = VisualSearchTool(_index(tmp_path), embedder=None, encoder=None)
    result = tool.run(query="table of regions")
    assert result.evidence[0].id == "d#page2"


def test_an_empty_page_index_says_so(tmp_path):
    tool = VisualSearchTool(PageIndex(tmp_path))
    result = tool.run(query="anything")
    assert result.evidence == []
    assert "No document pages" in result.observation


def test_the_tool_only_appears_once_pages_exist(tmp_path):
    from agentic_rag.embeddings.local_hash import HashedTfEmbedder
    from agentic_rag.retrieval.hybrid import HybridSearcher
    from agentic_rag.retrieval.vector_store import VectorStore
    from agentic_rag.tools import build_default_tools

    settings = Settings(llm_provider="mock", search_provider="none")
    searcher = HybridSearcher(VectorStore(tmp_path / "idx", HashedTfEmbedder(dim=64)), "hybrid")

    empty = PageIndex(tmp_path / "empty")
    assert "visual_search" not in build_default_tools(settings, searcher, page_index=empty)
    assert "visual_search" in build_default_tools(settings, searcher, page_index=_index(tmp_path / "full"))


# ------------------------------------------------------------- the demo pdf


def test_the_sample_pdf_hides_its_numbers_in_the_pictures():
    """The demo only means something if text extraction really does miss the chart."""
    from agentic_rag.ingestion.loaders import load_document

    assert SAMPLE_PDF.exists(), "the demo PDF ships with the repository"
    text = load_document(SAMPLE_PDF).text
    assert "Fleet growth by quarter" in text, "titles and labels do extract"
    for hidden in ("640", "1180", "1850"):
        assert hidden not in text, f"{hidden} should only exist as a bar height"


def test_reset_clears_page_records_embeddings_and_images(tmp_path):
    """A reset that leaves pages behind would duplicate them on the next ingest."""
    index = _index(tmp_path)
    images = tmp_path / "images"
    images.mkdir(exist_ok=True)
    (images / "d_page1.png").write_bytes(b"png")
    assert index.count == 2

    index.clear()

    assert index.count == 0
    assert not (tmp_path / "pages.jsonl").exists()
    assert list(tmp_path.glob("*.npy")) == []
    assert list(images.glob("*.png")) == []
    assert PageIndex(tmp_path).count == 0


def test_batched_adds_still_persist(tmp_path):
    index = PageIndex(tmp_path)
    for number in range(3):
        index.add(
            PageRecord(f"d#page{number}", "d", "Doc", "d.pdf", number, "x.png", "text"),
            np.array([[1.0, 0.0]]),
            flush=False,
        )
    assert PageIndex(tmp_path).count == 0, "nothing is written until save()"
    index.save()
    assert PageIndex(tmp_path).count == 3
