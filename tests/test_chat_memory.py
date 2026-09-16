"""Conversation memory: history plumbing, rewrite behaviour, prompt shape."""

from pathlib import Path

from agentic_rag.agent.prompts import (
    build_rewrite_prompt,
    build_synthesis_prompt,
    render_history,
)
from agentic_rag.config import Settings
from agentic_rag.core.types import Evidence
from agentic_rag.pipeline import AgenticRAG

ROOT = Path(__file__).resolve().parents[1]

HISTORY = [
    {"question": "What is the payload capacity of the Atlas P2?", "answer": "It carries up to 450 kg. [1]"},
]


def _pipeline(tmp_path):
    settings = Settings(
        llm_provider="mock",
        embeddings_provider="local",
        search_provider="none",
        storage_dir=str(tmp_path / "storage"),
        catalog_path=str(ROOT / "data" / "structured" / "catalog.json"),
    )
    rag = AgenticRAG(settings)
    rag.ingest(ROOT / "data" / "sample_docs")
    return rag


def test_history_renders_into_rewrite_and_synthesis_prompts():
    rendered = render_history(HISTORY)
    assert "User: What is the payload capacity" in rendered
    assert "Assistant: It carries up to 450 kg" in rendered
    assert "What is the payload" in build_rewrite_prompt("what about the P1?", HISTORY)
    prompt = build_synthesis_prompt("q", [], history=HISTORY)
    assert prompt.index("CONVERSATION SO FAR") < prompt.index("QUESTION:")
    assert "never cite" in prompt


def test_long_answers_are_truncated_in_history():
    rendered = render_history([{"question": "q", "answer": "x" * 500}])
    assert len(rendered) < 400 and rendered.endswith("...")


def test_chat_with_history_stays_grounded_and_records_passthrough(tmp_path):
    rag = _pipeline(tmp_path)
    answer = rag.chat("How long does the Atlas P2 run on a single charge?", history=HISTORY)
    assert "14" in answer.text
    assert answer.verification.passed
    # the mock never rewrites, so the field stays empty and behaviour is deterministic
    assert answer.rewritten_question == ""


def test_multi_turn_conversation_flows(tmp_path):
    rag = _pipeline(tmp_path)
    history: list[dict] = []
    for question, expected in [
        ("What is the payload capacity of the Atlas P2?", "450"),
        ("What does the Scale plan cost per robot per month?", "649"),
    ]:
        answer = rag.chat(question, history=history)
        assert expected in answer.text
        history.append({"question": question, "answer": answer.text})


def test_rewrite_guard_rejects_degenerate_output(tmp_path):
    rag = _pipeline(tmp_path)

    class WeirdLLM:
        is_mock = False
        name = "weird"

        def complete(self, *args, **kwargs):
            class R:
                text = "ok"  # too short to be a standalone question
            return R()

    rag.llm = WeirdLLM()
    assert rag._rewrite("what about it?", HISTORY) == "what about it?"


def _evidence_free_prompt_has_no_history_section():
    assert "CONVERSATION" not in build_synthesis_prompt("q", [Evidence("e1", "t", "vector", "r", "T", "vector_search")])
