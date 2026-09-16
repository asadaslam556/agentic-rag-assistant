"""Shared dataclasses used across the pipeline.

Keeping every stage's input/output as plain dataclasses makes the whole
system easy to test, serialize, and reason about: no framework objects
leak between layers.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Document:
    """A source document as loaded from disk."""

    id: str
    path: str
    title: str
    text: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    """A retrievable slice of a document."""

    id: str
    doc_id: str
    text: str
    title: str
    heading: str = ""
    position: int = 0
    source_path: str = ""

    @property
    def source_ref(self) -> str:
        ref = f"{self.source_path}#chunk{self.position}"
        return ref


@dataclass
class Evidence:
    """One unit of evidence produced by a tool call.

    ``call_id`` groups evidence by the tool call that produced it and
    ``rank`` is the position inside that call's result list. Both are
    used by reciprocal rank fusion during context assembly.
    """

    id: str
    text: str
    source_type: str          # vector | web | structured | calculation | page
    source_ref: str
    title: str
    tool_name: str
    call_id: int = 0
    image_path: str = ""      # set for page evidence, read at synthesis time
    rank: int = 0
    score: float = 0.0
    url: str = ""
    fused_score: float = 0.0


@dataclass
class ToolResult:
    """What a tool returns: evidence for the pipeline, a short
    observation string for the agent's transcript."""

    evidence: list[Evidence]
    observation: str


@dataclass
class AgentStep:
    """One planning step taken by the orchestrator."""

    step: int
    thought: str
    action: str
    action_input: dict[str, Any]
    observation: str


@dataclass
class Citation:
    marker: int
    evidence_id: str
    title: str
    source_type: str
    source_ref: str
    url: str = ""


@dataclass
class ClaimVerdict:
    claim: str
    cited_markers: list[int]
    supported: bool
    method: str
    note: str = ""


@dataclass
class VerificationReport:
    groundedness: float
    citation_coverage: float
    verdicts: list[ClaimVerdict]
    passed: bool
    method: str


@dataclass
class Answer:
    question: str
    text: str
    citations: list[Citation]
    evidence: list[Evidence]
    verification: VerificationReport
    steps: list[AgentStep]
    attempts: int
    timings_ms: dict[str, int]
    rewritten_question: str = ""
    sub_questions: list[str] = dataclasses.field(default_factory=list)
    branches: list[dict] = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


INSUFFICIENT_ANSWER = (
    "The available sources do not contain enough information to answer this question."
)
