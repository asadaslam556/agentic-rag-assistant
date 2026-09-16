"""Split a question into independent sub-questions.

Most questions are one sub-question and stay that way. The split only
happens when a request genuinely contains parts that can be researched
without each other, because every extra branch costs a full agent loop.

Three layers, in order: the model's structured answer, a conservative
"and" split when that is unusable, and the original question if neither
produces something sane. The mock provider always returns the question
unchanged so offline runs and the eval stay deterministic.
"""

from __future__ import annotations

from agentic_rag.agent.parser import ParserError, extract_first_json
from agentic_rag.agent.prompts import DECOMPOSE_SYSTEM, build_decompose_prompt
from agentic_rag.core.textutils import content_tokens
from agentic_rag.llm.base import LLMClient

_MIN_LEN = 8
_MAX_LEN = 300
_MIN_PART_LEN = 20
_MIN_PART_TOKENS = 3


def _normalise(question: str) -> str:
    return " ".join(question.lower().split()).strip(" ?.")


def _dedupe(questions: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for question in questions:
        key = _normalise(question)
        if key and key not in seen:
            seen.add(key)
            unique.append(question.strip())
    return unique


def heuristic_split(question: str) -> list[str]:
    """Split on a conjunction, but only when both halves stand on their own.

    "When was the company founded and where?" must not become
    ["When was the company founded", "where?"], so each half has to be
    long enough and carry enough content words to be researched alone.
    """
    lowered = question.lower()
    marker = " and "
    if marker not in lowered:
        return [question]
    index = lowered.index(marker)
    left = question[:index].strip(" ,")
    right = question[index + len(marker) :].strip(" ,")
    for part in (left, right):
        if len(part) < _MIN_PART_LEN or len(content_tokens(part)) < _MIN_PART_TOKENS:
            return [question]
    if not right.endswith("?"):
        right += "?"
    if not left.endswith("?"):
        left += "?"
    return [left, right]


def decompose(llm: LLMClient, question: str, max_branches: int = 3) -> list[str]:
    """Return one or more self-contained sub-questions, original first choice."""
    if llm.is_mock or max_branches <= 1:
        return [question]

    try:
        response = llm.complete(
            DECOMPOSE_SYSTEM,
            [{"role": "user", "content": build_decompose_prompt(question, max_branches)}],
            temperature=0.0,
            max_tokens=400,
        )
        payload = extract_first_json(response.text)
        raw = payload.get("sub_questions")
        if not isinstance(raw, list):
            raise ParserError("sub_questions missing")
        candidates = [str(item).strip() for item in raw if str(item).strip()]
    except (ParserError, TypeError, ValueError, RuntimeError):
        candidates = heuristic_split(question)

    usable = [q for q in _dedupe(candidates) if _MIN_LEN <= len(q) <= _MAX_LEN]
    if not usable:
        return [question]
    if len(usable) == 1:
        return usable
    return usable[:max_branches]
