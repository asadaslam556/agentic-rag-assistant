"""LLM-as-judge scoring for evaluation runs.

Complements the substring checks in `rag eval` with two graded scores
in the spirit of RAGAS: faithfulness (is the answer supported by the
retrieved sources) and relevance (does it address the question). With a
real model, one MODE: JUDGE call scores both. With the mock provider,
or whenever the judge response cannot be parsed, a deterministic
lexical approximation keeps the metric available offline: faithfulness
becomes the mean best token overlap of each claim against the sources,
relevance the token overlap between question and answer.
"""

from __future__ import annotations

from agentic_rag.agent.parser import ParserError, extract_first_json
from agentic_rag.agent.prompts import JUDGE_SYSTEM, build_judge_prompt
from agentic_rag.core.textutils import content_tokens
from agentic_rag.core.types import INSUFFICIENT_ANSWER, Evidence
from agentic_rag.llm.base import LLMClient
from agentic_rag.verification.verifier import split_claims


def _lexical_judge(question: str, answer: str, evidence: list[Evidence]) -> dict:
    claims = split_claims(answer)
    if not claims or not evidence:
        return {"faithfulness": 0.0, "relevance": 0.0, "note": "no claims or no sources", "method": "lexical"}
    source_tokens = [content_tokens(item.text) for item in evidence]
    overlaps: list[float] = []
    for claim, _markers in claims:
        tokens = content_tokens(claim)
        if not tokens:
            continue
        overlaps.append(max(len(tokens & source) / len(tokens) for source in source_tokens))
    faithfulness = round(sum(overlaps) / len(overlaps), 3) if overlaps else 0.0
    question_tokens = content_tokens(question)
    answer_tokens = content_tokens(answer)
    relevance = (
        round(len(question_tokens & answer_tokens) / len(question_tokens), 3)
        if question_tokens
        else 1.0
    )
    return {"faithfulness": faithfulness, "relevance": relevance, "note": "token overlap", "method": "lexical"}


def judge_answer(llm: LLMClient, question: str, answer: str, evidence: list[Evidence]) -> dict:
    """Score one answer. Returns faithfulness and relevance in [0, 1]."""
    if answer.strip() == INSUFFICIENT_ANSWER:
        return {
            "faithfulness": 1.0,
            "relevance": 1.0,
            "note": "honest abstention",
            "method": "rule",
        }
    if llm.is_mock:
        return _lexical_judge(question, answer, evidence)
    prompt = build_judge_prompt(question, answer, evidence)
    try:
        response = llm.complete(
            JUDGE_SYSTEM, [{"role": "user", "content": prompt}], temperature=0.0, max_tokens=300
        )
        payload = extract_first_json(response.text)
        faithfulness = max(0.0, min(1.0, float(payload.get("faithfulness", 0)) / 100.0))
        relevance = max(0.0, min(1.0, float(payload.get("relevance", 0)) / 100.0))
        return {
            "faithfulness": round(faithfulness, 3),
            "relevance": round(relevance, 3),
            "note": str(payload.get("note", ""))[:200],
            "method": "llm",
        }
    except (ParserError, TypeError, ValueError, RuntimeError):
        return _lexical_judge(question, answer, evidence)
