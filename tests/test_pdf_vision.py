"""Page-image understanding for PDFs, exercised with the deterministic mock."""

from agentic_rag.config import Settings
from agentic_rag.core.types import Document
from agentic_rag.ingestion.pdf_vision import (
    describe_pages,
    page_chunks,
    vision_enabled,
)
from agentic_rag.llm.mock import MockLLM


class BlindLLM:
    name = "blind"
    is_mock = True
    supports_vision = False


DOC = Document(id="d1", path="report.pdf", title="Report", text="short")


def test_auto_mode_only_fires_when_text_extraction_came_back_thin():
    settings = Settings(pdf_vision="auto")
    thin = "a few words on the page"
    fat = "x" * 5000
    assert vision_enabled(settings, MockLLM(), thin, page_count=3)
    assert not vision_enabled(settings, MockLLM(), fat, page_count=3)


def test_off_and_on_modes_ignore_the_text_heuristic():
    assert not vision_enabled(Settings(pdf_vision="off"), MockLLM(), "tiny", 5)
    assert vision_enabled(Settings(pdf_vision="on"), MockLLM(), "x" * 9000, 5)


def test_a_provider_without_vision_is_never_asked():
    assert not vision_enabled(Settings(pdf_vision="on"), BlindLLM(), "tiny", 3)


def test_descriptions_become_citable_page_chunks():
    descriptions = [
        "Bar chart of quarterly revenue rising from 12 to 31 million euro.",
        "NO VISUAL CONTENT",
        "Table listing three plans with monthly prices.",
    ]
    chunks = page_chunks(DOC, descriptions, start_position=4)
    assert len(chunks) == 2, "pages with nothing visual are dropped"
    assert chunks[0].heading == "page 1 (visual)"
    assert chunks[1].heading == "page 3 (visual)"
    assert "quarterly revenue" in chunks[0].text
    assert chunks[0].position == 4 and chunks[1].position == 5
    assert len({c.id for c in chunks}) == 2


def test_a_failed_page_is_skipped_rather_than_indexed():
    chunks = page_chunks(DOC, ["PAGE READ FAILED: timeout", "A schematic of the drive unit."], 0)
    assert len(chunks) == 1
    assert "schematic" in chunks[0].text


def test_describe_pages_survives_a_model_error():
    class BrokenLLM:
        name = "broken"
        is_mock = False
        supports_vision = True

        def complete_vision(self, *args, **kwargs):
            raise RuntimeError("model exploded")

    results = describe_pages(BrokenLLM(), [b"png-bytes"])
    assert results[0].startswith("PAGE READ FAILED")


def test_mock_provider_produces_a_description_without_a_real_model():
    text = describe_pages(MockLLM(), [b"png-a", b"png-b"])
    assert len(text) == 2
    assert "Page overview" in text[0]


def test_render_pages_explains_the_missing_dependency(tmp_path):
    import agentic_rag.ingestion.pdf_vision as module

    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        fake = tmp_path / "x.pdf"
        fake.write_bytes(b"%PDF-1.4 not really")
        try:
            module.render_pages(fake, 1, 2.0)
            raise AssertionError("expected RuntimeError")
        except RuntimeError as exc:
            assert "pypdfium2" in str(exc)
            assert "PDF_VISION=off" in str(exc)


def test_page_descriptions_reach_the_index_and_are_searchable(tmp_path):
    """Ingest a PDF with the renderer stubbed, then find the chart by asking for it."""
    import agentic_rag.ingestion.loaders as loaders_module
    import agentic_rag.ingestion.pdf_vision as vision_module
    from agentic_rag.pipeline import AgenticRAG

    pdf = tmp_path / "quarterly.pdf"
    pdf.write_bytes(b"%PDF-1.4 stub")

    original_render = vision_module.render_pages
    original_read = loaders_module._read_pdf
    vision_module.render_pages = lambda path, max_pages, scale: [b"fake-png-page-1"]
    loaders_module._read_pdf = lambda path: "Quarterly report."

    class ChartLLM:
        name = "chart-reader"
        is_mock = True
        supports_vision = True

        def complete_vision(self, system, prompt, images, **kwargs):
            class Response:
                text = (
                    "Bar chart titled Fleet growth, plotting deployed robots per quarter, "
                    "rising from 400 in Q1 to 1850 in Q4."
                )

            return Response()

    try:
        rag = AgenticRAG(
            Settings(
                llm_provider="mock",
                search_provider="none",
                pdf_vision="on",
                storage_dir=str(tmp_path / "storage"),
            )
        )
        rag.router._clients["vision-stub"] = ChartLLM()
        rag.router.model_for = lambda role: "vision-stub" if role == "vision" else ""
        stats = rag.ingest(pdf)
        assert stats["chunks_added"] >= 2, "text chunk plus at least one page description"

        hits = rag.searcher.search("fleet growth bar chart robots per quarter", k=3)
        assert hits, "the chart description should be retrievable"
        assert "Fleet growth" in hits[0][0].text
        assert hits[0][0].heading == "page 1 (visual)"
    finally:
        vision_module.render_pages = original_render
        loaders_module._read_pdf = original_read


def test_synthesis_attaches_page_images_when_the_model_can_see(tmp_path):
    """A retrieved page should reach the answering model as a picture."""
    from agentic_rag.core.types import Evidence
    from agentic_rag.pipeline import AgenticRAG

    image = tmp_path / "page2.png"
    image.write_bytes(b"fake-png-bytes")

    rag = AgenticRAG(
        Settings(llm_provider="mock", search_provider="none", storage_dir=str(tmp_path / "storage"))
    )
    evidence = [
        Evidence(
            id="d#page2",
            text="Bar chart of fleet growth.",
            source_type="page",
            source_ref="d.pdf#page2",
            title="Doc (page 2)",
            tool_name="visual_search",
            image_path=str(image),
        )
    ]
    assert rag._evidence_images(evidence) == [b"fake-png-bytes"]

    seen = {}

    class SeeingLLM:
        name, is_mock, supports_vision = "seeing", True, True

        def complete_vision(self, system, prompt, images, **kwargs):
            seen["images"] = images
            seen["prompt"] = prompt
            return type("R", (), {"text": "Fleet growth reached about 1850 robots. [1]"})()

    rag.llm = SeeingLLM()
    answer = rag._synthesize("How many robots by Q4?", evidence)
    assert "1850" in answer
    assert seen["images"] == [b"fake-png-bytes"], "the page image was sent, not just its description"


def test_a_missing_image_file_is_skipped_rather_than_raising(tmp_path):
    from agentic_rag.core.types import Evidence
    from agentic_rag.pipeline import AgenticRAG

    rag = AgenticRAG(
        Settings(llm_provider="mock", search_provider="none", storage_dir=str(tmp_path / "storage"))
    )
    evidence = [
        Evidence(
            id="gone",
            text="t",
            source_type="page",
            source_ref="r",
            title="T",
            tool_name="visual_search",
            image_path=str(tmp_path / "does-not-exist.png"),
        )
    ]
    assert rag._evidence_images(evidence) == []
