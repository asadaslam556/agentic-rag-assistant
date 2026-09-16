"""The orchestrator graph: decomposition, real parallelism, budget, containment."""

import threading
from pathlib import Path

from agentic_rag.config import Settings
from agentic_rag.core.types import AgentStep, Evidence
from agentic_rag.graph.decompose import decompose, heuristic_split
from agentic_rag.graph.runner import GraphRunner
from agentic_rag.graph.state import BudgetTracker
from agentic_rag.llm.mock import MockLLM
from agentic_rag.pipeline import AgenticRAG

ROOT = Path(__file__).resolve().parents[1]


class FakeLLM:
    """Returns canned text, so decomposition can be tested without a model."""

    is_mock = False
    name = "fake"

    def __init__(self, text: str):
        self.text = text

    def complete(self, *args, **kwargs):
        class Response:
            pass

        response = Response()
        response.text = self.text
        return response


def _evidence(text: str) -> Evidence:
    return Evidence(
        id="e1", text=text, source_type="vector", source_ref="d.md#0", title="D",
        tool_name="vector_search",
    )


def _step(action: str = "vector_search") -> AgentStep:
    return AgentStep(step=1, thought="t", action=action, action_input={}, observation="o")


# ------------------------------------------------------------- decomposition


def test_mock_provider_never_splits_so_offline_runs_stay_deterministic():
    assert decompose(MockLLM(), "What does A cost and when was B founded?", max_branches=3) == [
        "What does A cost and when was B founded?"
    ]


def test_heuristic_keeps_questions_whose_second_half_cannot_stand_alone():
    question = "When was Auralis Dynamics founded and where?"
    assert heuristic_split(question) == [question]


def test_heuristic_splits_two_real_questions():
    parts = heuristic_split(
        "What does the Scale plan cost per robot per month and how long does a deployment take?"
    )
    assert len(parts) == 2
    assert parts[0].endswith("?") and parts[1].endswith("?")
    assert "Scale plan" in parts[0]
    assert "deployment" in parts[1]


def test_model_decomposition_is_used_and_deduplicated():
    llm = FakeLLM(
        '{"sub_questions": ["What is the payload capacity?", "what is the payload capacity?",'
        ' "How long is the runtime?"]}'
    )
    assert decompose(llm, "payload and runtime", max_branches=3) == [
        "What is the payload capacity?",
        "How long is the runtime?",
    ]


def test_unusable_model_output_falls_back_to_the_heuristic():
    llm = FakeLLM("I think we should split this into several parts, probably two.")
    parts = decompose(
        llm,
        "What does the Scale plan cost per robot per month and how long does a deployment take?",
        max_branches=3,
    )
    assert len(parts) == 2


def test_branch_cap_is_respected():
    llm = FakeLLM('{"sub_questions": ["question one here", "question two here", "question three"]}')
    assert len(decompose(llm, "q", max_branches=2)) == 2


# ------------------------------------------------------------------ budget


def test_budget_survives_concurrent_branches():
    budget = BudgetTracker(max_steps=50)
    granted: list[bool] = []
    lock = threading.Lock()

    def worker():
        for _ in range(40):
            allowed = budget.take()
            with lock:
                granted.append(allowed)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(granted) == 50, "the shared cap must hold exactly under contention"
    assert budget.remaining == 0


# ------------------------------------------------------------------- graph


class BarrierOrchestrator:
    """Every branch waits for the others, so the test fails if they run in sequence."""

    def __init__(self, expected: int):
        self.barrier = threading.Barrier(expected, timeout=5)

    def collect(self, question, on_step=None, budget=None):
        if budget is not None:
            budget.take()
        self.barrier.wait()  # times out unless the branches are genuinely concurrent
        step = _step()
        if on_step is not None:
            on_step(step)
        return [_evidence(f"evidence for {question}")], [step]


def _runner(orchestrator, **overrides):
    settings = Settings(llm_provider="mock", max_branches=3, **overrides)
    return GraphRunner(MockLLM(), orchestrator, settings)


def test_branches_run_at_the_same_time(monkeypatch=None):
    import agentic_rag.graph.runner as runner_module

    questions = ["What does the plan cost?", "How long is deployment?"]
    original = runner_module.decompose
    runner_module.decompose = lambda llm, question, max_branches=3: questions
    try:
        events = []
        result = _runner(BarrierOrchestrator(expected=2)).run(
            "cost and deployment", emit=lambda name, payload: events.append((name, payload))
        )
    finally:
        runner_module.decompose = original

    assert result.sub_questions == questions
    assert len(result.evidence) == 2
    assert len(result.branches) == 2
    assert [name for name, _ in events][0] == "decompose"
    branch_ids = {payload["branch"] for name, payload in events if name == "step"}
    assert branch_ids == {0, 1}, "each step must say which branch produced it"
    # the saved answer keeps the same tags, not only the live events
    assert {step.branch for step in result.steps} == {0, 1}


def test_single_question_keeps_the_original_event_order():
    events = []
    result = _runner(BarrierOrchestrator(expected=1)).run(
        "one question", emit=lambda name, payload: events.append((name, payload))
    )
    names = [name for name, _ in events]
    assert "decompose" not in names, "no fan-out machinery for a single question"
    assert names[0] == "stage" and events[0][1]["name"] == "planning"
    assert result.sub_questions == ["one question"]


class ExplodingOrchestrator:
    def collect(self, question, on_step=None, budget=None):
        if "boom" in question:
            raise RuntimeError("branch blew up")
        return [_evidence("fine")], [_step()]


def test_one_failing_branch_does_not_sink_the_answer():
    import agentic_rag.graph.runner as runner_module

    original = runner_module.decompose
    runner_module.decompose = lambda llm, question, max_branches=3: ["good question here", "boom question"]
    try:
        events = []
        result = _runner(ExplodingOrchestrator()).run(
            "q", emit=lambda name, payload: events.append((name, payload))
        )
    finally:
        runner_module.decompose = original

    assert len(result.evidence) == 1, "the healthy branch still contributes"
    errors = [b for b in result.branches if b["error"]]
    assert len(errors) == 1 and "blew up" in errors[0]["error"]
    assert any(name == "branch_error" for name, _ in events)


def test_shared_budget_caps_total_work_across_branches():
    import agentic_rag.graph.runner as runner_module

    class GreedyOrchestrator:
        def collect(self, question, on_step=None, budget=None):
            taken = 0
            while budget is not None and budget.take():
                taken += 1
            return [_evidence(f"{question}:{taken}")], [_step()]

    original = runner_module.decompose
    runner_module.decompose = lambda llm, question, max_branches=3: ["question one aa", "question two bb"]
    try:
        result = _runner(GreedyOrchestrator(), max_total_agent_steps=7).run("q")
    finally:
        runner_module.decompose = original

    assert result.budget == {"used": 7, "max_steps": 7}


def test_end_to_end_two_branches_gather_both_facts(tmp_path):
    import agentic_rag.graph.runner as runner_module

    settings = Settings(
        llm_provider="mock",
        embeddings_provider="local",
        search_provider="none",
        storage_dir=str(tmp_path / "storage"),
        catalog_path=str(ROOT / "data" / "structured" / "catalog.json"),
    )
    rag = AgenticRAG(settings)
    rag.ingest(ROOT / "data" / "sample_docs")

    original = runner_module.decompose
    runner_module.decompose = lambda llm, question, max_branches=3: [
        "What does the Scale plan cost per robot per month?",
        "What is the payload capacity of the Atlas P2?",
    ]
    try:
        events = []
        answer = rag.ask("cost and payload", on_event=lambda n, p: events.append((n, p)))
    finally:
        runner_module.decompose = original

    assert len(answer.sub_questions) == 2
    assert len(answer.branches) == 2
    assert all(branch["evidence_count"] > 0 for branch in answer.branches)
    corpus = " ".join(item.text for item in answer.evidence)
    assert "649" in corpus and "450" in corpus, "both branches contributed evidence"
    assert answer.verification.passed
