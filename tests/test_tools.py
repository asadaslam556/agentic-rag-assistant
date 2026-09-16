from pathlib import Path

import pytest

from agentic_rag.config import Settings
from agentic_rag.tools.structured import (
    CalculatorTool,
    KnowledgeBaseTool,
    format_number,
    safe_eval,
)
from agentic_rag.tools.web_search import WebSearchTool

ROOT = Path(__file__).resolve().parents[1]


def test_safe_eval_arithmetic():
    assert safe_eval("2 + 3 * 4") == 14
    assert safe_eval("(449 + 649) / 2") == 549
    assert format_number(safe_eval("23 * 649")) == "14,927"


def test_safe_eval_rejects_code():
    for hostile in ["__import__('os')", "open('x')", "a + b", "2 ** 10000"]:
        with pytest.raises((ValueError, SyntaxError)):
            safe_eval(hostile)


def test_calculator_safe_run_filters_unknown_arguments():
    result = CalculatorTool().safe_run(expression="2 + 2", bogus="ignored")
    assert "= 4" in result.observation
    assert result.evidence[0].source_type == "calculation"


def test_knowledge_base_lookup_returns_structured_evidence():
    tool = KnowledgeBaseTool(ROOT / "data" / "structured" / "catalog.json")
    result = tool.run(query="Atlas P2 lease price")
    assert result.evidence
    assert any("1190" in item.text for item in result.evidence)
    assert all(item.source_type == "structured" for item in result.evidence)


def test_knowledge_base_metric_lookup():
    tool = KnowledgeBaseTool(ROOT / "data" / "structured" / "catalog.json")
    result = tool.run(query="how many robots deployed")
    assert any("1850" in item.text for item in result.evidence)


def test_web_search_fixture_provider():
    settings = Settings(
        search_provider="fixture",
        web_fixtures_path=str(ROOT / "data" / "web_fixtures.json"),
    )
    result = WebSearchTool(settings).run(query="warehouse robotics market size 2027")
    assert len(result.evidence) == 2
    assert all(item.url.startswith("https://") for item in result.evidence)


def test_web_search_none_provider_reports_unconfigured():
    result = WebSearchTool(Settings(search_provider="none")).run(query="anything")
    assert result.evidence == []
    assert "not configured" in result.observation


def test_preview_does_not_cut_a_number_in_half():
    """A hard slice produced "EUR 64...", which the model read as missing
    data and then re-searched for a figure it already had."""
    from agentic_rag.tools.base import preview

    text = (
        "The Scale plan costs EUR 649 per robot per month, billed annually, and covers "
        "up to 25 robots with business-hours support and quarterly service visits."
    )
    shortened = preview(text, limit=60)
    assert "EUR 64" not in shortened or "EUR 649" in shortened
    assert not shortened.replace(" [...]", "").endswith(("EUR", "6", "64"))
    assert preview("short text") == "short text"


def test_the_search_observation_says_the_preview_is_not_the_whole_passage():
    from agentic_rag.core.types import Chunk
    from agentic_rag.tools.vector_search import VectorSearchTool

    long_text = "Scale plan costs EUR 649 per robot per month. " * 12
    chunk = Chunk(id="c0", doc_id="d", text=long_text, title="Pricing", heading="Scale plan",
                  position=0, source_path="pricing.md")

    class _Searcher:
        count = 1

        def search(self, query, k=5):
            return [(chunk, 0.9)]

    result = VectorSearchTool(_Searcher(), default_k=5).run(query="scale plan cost")
    assert "previews" in result.observation
    assert "do not search again" in result.observation
    # the evidence still carries the untouched passage
    assert result.evidence[0].text == long_text
