"""Full pipeline runs offline: mock LLM, local embeddings, no network."""

from pathlib import Path

import pytest

from agentic_rag.config import Settings
from agentic_rag.core.types import INSUFFICIENT_ANSWER
from agentic_rag.pipeline import AgenticRAG

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def rag(tmp_path):
    settings = Settings(
        llm_provider="mock",
        embeddings_provider="local",
        search_provider="none",
        storage_dir=str(tmp_path / "storage"),
        catalog_path=str(ROOT / "data" / "structured" / "catalog.json"),
    )
    pipeline = AgenticRAG(settings)
    stats = pipeline.ingest(ROOT / "data" / "sample_docs")
    assert stats["chunks_added"] > 10
    return pipeline


def test_grounded_answer_with_citation_and_verification(rag):
    answer = rag.ask("What is the payload capacity of the Atlas P2?")
    assert "450" in answer.text
    assert answer.citations and answer.citations[0].marker == 1
    assert answer.verification.passed
    assert answer.verification.groundedness == 1.0


def test_arithmetic_routes_to_the_calculator(rag):
    answer = rag.ask("What is 23 * 649?")
    assert "14,927" in answer.text
    assert any(step.action == "calculator" for step in answer.steps)
    assert answer.citations[0].source_type == "calculation"


def test_pricing_question_uses_structured_then_vector_tools(rag):
    answer = rag.ask("What does the Scale plan cost per robot per month?")
    assert "649" in answer.text
    actions = [step.action for step in answer.steps]
    assert "knowledge_base" in actions
    assert "vector_search" in actions
    assert answer.verification.passed


def test_unanswerable_question_abstains_honestly(rag):
    answer = rag.ask("What is the capital of France?")
    assert answer.text == INSUFFICIENT_ANSWER
    assert answer.verification.passed  # honest abstention is a pass, not a hallucination


def test_web_hinted_question_routes_to_web_search(tmp_path):
    """With a search provider configured, the agent brings in web
    evidence for questions about the outside world, using the offline
    fixture provider so the test stays deterministic."""
    settings = Settings(
        llm_provider="mock",
        embeddings_provider="local",
        search_provider="fixture",
        web_fixtures_path=str(ROOT / "data" / "web_fixtures.json"),
        storage_dir=str(tmp_path / "storage"),
        catalog_path=str(ROOT / "data" / "structured" / "catalog.json"),
    )
    pipeline = AgenticRAG(settings)
    pipeline.ingest(ROOT / "data" / "sample_docs")
    answer = pipeline.ask("How big will the warehouse robotics market be by 2027?")
    assert any(step.action == "web_search" for step in answer.steps)
    assert "25 billion" in answer.text
    assert any(citation.source_type == "web" for citation in answer.citations)
    assert answer.verification.passed


def test_ingest_survives_a_corrupt_file_and_reports_it(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "good.md").write_text("# Good\n\nThe launch window opens at dawn on the fifth day.")
    (docs / "bad.pdf").write_bytes(b"this is not a pdf at all")
    settings = Settings(
        llm_provider="mock",
        embeddings_provider="local",
        search_provider="none",
        storage_dir=str(tmp_path / "storage"),
        catalog_path=str(ROOT / "data" / "structured" / "catalog.json"),
    )
    rag = AgenticRAG(settings)
    stats = rag.ingest(docs)
    assert stats["files_added"] == 1
    assert stats["chunks_added"] >= 1
    assert len(stats["errors"]) == 1
    assert stats["errors"][0]["file"] == "bad.pdf"
    answer = rag.ask("When does the launch window open?")
    assert "dawn" in answer.text


def test_eval_cases_declare_categories_and_reachable_tools():
    import json

    cases = [
        json.loads(line)
        for line in (ROOT / "eval" / "golden_set.jsonl").read_text().splitlines()
        if line.strip()
    ]
    known_tools = {"vector_search", "web_search", "knowledge_base", "calculator"}
    assert len(cases) >= 8
    for case in cases:
        assert case["category"], case["id"]
        assert case["difficulty"] in {"easy", "medium", "hard"}, case["id"]
        assert set(case["expected_tools"]) <= known_tools, case["id"]
