"""LLM-as-judge scoring, exercised through the lexical offline path."""

from agentic_rag.core.types import INSUFFICIENT_ANSWER, Evidence
from agentic_rag.llm.mock import MockLLM
from agentic_rag.verification.judge import judge_answer


def _evidence():
    return [
        Evidence(
            id="e1",
            text="The Atlas P2 carries up to 450 kg on its standard load deck.",
            source_type="vector",
            source_ref="doc.md#chunk0",
            title="Doc",
            tool_name="vector_search",
        )
    ]


def test_grounded_answer_scores_high_faithfulness():
    scores = judge_answer(
        MockLLM(),
        "What is the payload capacity of the Atlas P2?",
        "The Atlas P2 carries up to 450 kg on its standard load deck. [1]",
        _evidence(),
    )
    assert scores["method"] == "lexical"
    assert scores["faithfulness"] >= 0.9
    assert scores["relevance"] >= 0.5


def test_fabricated_answer_scores_low_faithfulness():
    scores = judge_answer(
        MockLLM(),
        "How fast is the Atlas P2?",
        "The Atlas P2 flies through warehouses at 900 kilometres per hour. [1]",
        _evidence(),
    )
    assert scores["faithfulness"] < 0.5


def test_honest_abstention_is_not_penalised():
    scores = judge_answer(MockLLM(), "Unknown topic?", INSUFFICIENT_ANSWER, [])
    assert scores["faithfulness"] == 1.0
    assert scores["method"] == "rule"
