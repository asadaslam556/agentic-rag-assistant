"""The orchestrator graph: decompose, fan out, merge, check coverage.

Two levels. The worker is the plan-and-act loop the project started
with, scoped to one sub-question. This layer wraps several of those:

    decompose -> branch -> merge -> coverage -> answer
                 branch  /            |
                 branch /             +-- bounded retry of empty branches

Splitting the levels buys two things a single loop cannot give you.
Independent parts of a question get researched at the same time instead
of one after another, which is what you feel with a slow local model.
And coverage is checked against the sub-questions that were asked, not
against whatever the one loop happened to fetch.

The machinery only appears when a question genuinely has independent
parts. A single sub-question runs inline on the calling thread and
behaves exactly like the original loop, same events, same order.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

from agentic_rag.agent.orchestrator import Orchestrator
from agentic_rag.config import Settings
from agentic_rag.core.types import AgentStep, Evidence
from agentic_rag.graph.decompose import decompose
from agentic_rag.graph.state import BranchState, BudgetTracker
from agentic_rag.llm.base import LLMClient


@dataclass
class GraphResult:
    evidence: list[Evidence]
    steps: list[AgentStep]
    sub_questions: list[str] = field(default_factory=list)
    branches: list[dict] = field(default_factory=list)
    budget: dict = field(default_factory=dict)


class GraphRunner:
    def __init__(self, llm: LLMClient, orchestrator: Orchestrator, settings: Settings):
        self.llm = llm
        self.orchestrator = orchestrator
        self.settings = settings

    # --------------------------------------------------------------- nodes

    def _run_branch(self, state: BranchState, budget: BudgetTracker, emit) -> BranchState:
        def on_step(step: AgentStep) -> None:
            step.branch = state.index
            payload = asdict(step)
            emit("step", payload)

        try:
            evidence, steps = self.orchestrator.collect(
                state.question, on_step=on_step, budget=budget
            )
            state.evidence = evidence
            state.steps = steps
        except Exception as exc:
            # one branch failing should not take the whole answer down
            state.error = str(exc)[:300]
            emit("branch_error", {"branch": state.index, "message": state.error})
        return state

    def _fan_out(
        self, questions: list[str], budget: BudgetTracker, emit, indices: list[int] | None = None
    ) -> list[BranchState]:
        # a retry keeps the index of the branch it stands in for, so its steps
        # are reported under the same part of the question
        indices = indices if indices is not None else list(range(len(questions)))
        states = [BranchState(index=i, question=q) for i, q in zip(indices, questions, strict=True)]
        if len(states) == 1:
            return [self._run_branch(states[0], budget, emit)]
        workers = min(len(states), max(1, self.settings.max_branches))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="branch") as pool:
            return list(pool.map(lambda state: self._run_branch(state, budget, emit), states))

    def _merge(self, states: list[BranchState]) -> tuple[list[Evidence], list[AgentStep]]:
        """Join point. Assembly deduplicates and re-ranks, so branch order is enough here."""
        evidence: list[Evidence] = []
        steps: list[AgentStep] = []
        for state in states:
            evidence.extend(state.evidence)
            for step in state.steps:
                step.branch = state.index
            steps.extend(state.steps)
        return evidence, steps

    # ----------------------------------------------------------------- run

    def run(self, question: str, emit=None) -> GraphResult:
        emit = emit if emit is not None else (lambda name, payload: None)
        budget = BudgetTracker(self.settings.max_total_agent_steps)

        questions = decompose(self.llm, question, max_branches=self.settings.max_branches)
        if len(questions) > 1:
            emit("decompose", {"sub_questions": questions})

        emit("stage", {"name": "planning"})
        states = self._fan_out(questions, budget, emit)

        # coverage: a branch that found nothing gets one more try while budget lasts
        gaps = [s for s in states if not s.evidence and not s.error]
        if len(states) > 1 and gaps and budget.remaining > 0:
            emit("stage", {"name": "retrying"})
            retried = self._fan_out(
                [s.question for s in gaps], budget, emit, indices=[s.index for s in gaps]
            )
            for original, retry in zip(gaps, retried, strict=False):
                original.evidence = retry.evidence
                original.steps.extend(retry.steps)

        evidence, steps = self._merge(states)
        return GraphResult(
            evidence=evidence,
            steps=steps,
            sub_questions=questions,
            branches=[state.summary() for state in states],
            budget=budget.snapshot(),
        )
