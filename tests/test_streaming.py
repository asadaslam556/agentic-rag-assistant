"""Live pipeline events and token streaming with the deterministic mock."""

from pathlib import Path

from agentic_rag.agent.prompts import SYNTHESIZE_SYSTEM
from agentic_rag.config import Settings
from agentic_rag.llm.mock import MockLLM
from agentic_rag.pipeline import AgenticRAG

ROOT = Path(__file__).resolve().parents[1]


def test_mock_stream_chunks_join_to_the_full_completion():
    llm = MockLLM()
    prompt = (
        "QUESTION: What is the payload?\n\nSOURCES:\n"
        "[1] Doc :: doc.md#chunk0\nThe payload is exactly 450 kg on the deck.\n"
        "END OF SOURCES\n\nWrite the grounded, cited answer now."
    )
    messages = [{"role": "user", "content": prompt}]
    full = llm.complete(SYNTHESIZE_SYSTEM, messages).text
    pieces = list(llm.complete_stream(SYNTHESIZE_SYSTEM, messages))
    assert len(pieces) > 1
    assert "".join(pieces) == full


def test_pipeline_emits_ordered_events_and_matching_tokens(tmp_path):
    settings = Settings(
        llm_provider="mock",
        embeddings_provider="local",
        search_provider="none",
        storage_dir=str(tmp_path / "storage"),
        catalog_path=str(ROOT / "data" / "structured" / "catalog.json"),
    )
    rag = AgenticRAG(settings)
    rag.ingest(ROOT / "data" / "sample_docs")

    events: list[tuple[str, dict]] = []
    answer = rag.ask(
        "What is the payload capacity of the Atlas P2?",
        on_event=lambda name, payload: events.append((name, payload)),
    )

    names = [name for name, _payload in events]
    stages = [payload["name"] for name, payload in events if name == "stage"]
    assert stages[:3] == ["planning", "assembling", "synthesizing"]
    assert "verifying" in stages
    assert names.count("synthesis_start") >= 1
    assert any(name == "step" for name in names)
    step_actions = [payload["action"] for name, payload in events if name == "step"]
    assert "vector_search" in step_actions and "finish" in step_actions

    assert answer.attempts == 0
    tokens = "".join(payload["text"] for name, payload in events if name == "token")
    assert tokens.strip() == answer.text
