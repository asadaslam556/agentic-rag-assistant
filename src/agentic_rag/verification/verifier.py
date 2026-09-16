"""Answer verification: claim-level groundedness and citation coverage.

The draft answer is split into claims (sentences). Each claim keeps the
citation markers it carries. Two verification strategies share the same
report format:

- lexical: a claim is supported when the content-token overlap with a
  cited source reaches a threshold. Deterministic, offline, used for
  the mock provider, tests, and CI.
- llm: a single MODE: VERIFY call judges every claim against its cited
  sources; falls back to lexical when the response cannot be parsed.

The report drives the refine loop in the pipeline: answers below the
groundedness threshold are rewritten with explicit feedback about which
claims failed.
"""

from __future__ import annotations

import re

from agentic_rag.agent.parser import ParserError, extract_first_json
from agentic_rag.agent.prompts import VERIFY_SYSTEM, build_verify_prompt
from agentic_rag.config import Settings
from agentic_rag.core.textutils import content_tokens, split_sentences
from agentic_rag.core.types import (
    INSUFFICIENT_ANSWER,
    ClaimVerdict,
    Evidence,
    VerificationReport,
)
from agentic_rag.llm.base import LLMClient

_MARKER = re.compile(r"\[(\d{1,2})\]")
_LEXICAL_THRESHOLD = 0.45


def split_claims(answer: str) -> list[tuple[str, list[int]]]:
    """Split an answer into (claim, cited_markers) pairs.

    Models often place citations after the closing period ("... 450 kg. [1]"),
    which the sentence splitter sees as a separate fragment. Fragments that
    contain only citation markers are merged back into the previous claim.
    """
    claims: list[tuple[str, list[int]]] = []
    for sentence in split_sentences(answer):
        markers = [int(m) for m in _MARKER.findall(sentence)]
        clean = normalize_claim(sentence)
        if len(clean) < 3:
            if markers and claims:
                previous_claim, previous_markers = claims[-1]
                claims[-1] = (previous_claim, previous_markers + markers)
            continue
        claims.append((clean, markers))
    return claims


def normalize_claim(sentence: str) -> str:
    return _MARKER.sub("", sentence).strip()


def lexical_support(claim: str, sources: list[Evidence]) -> tuple[bool, str]:
    claim_tokens = content_tokens(claim)
    if not claim_tokens:
        return True, "no factual content"
    best = 0.0
    for source in sources:
        overlap = len(claim_tokens & content_tokens(source.text)) / len(claim_tokens)
        best = max(best, overlap)
    return best >= _LEXICAL_THRESHOLD, f"token overlap {best:.2f}"


class Verifier:
    def __init__(self, llm: LLMClient, settings: Settings):
        self.llm = llm
        self.settings = settings
        mode = settings.verifier_mode
        if mode == "auto":
            mode = "lexical" if llm.is_mock else "llm"
        self.mode = mode if mode in {"lexical", "llm"} else "lexical"

    # ------------------------------------------------------------- strategies

    def _verify_lexical(
        self, claims: list[tuple[str, list[int]]], evidence: list[Evidence]
    ) -> list[ClaimVerdict]:
        verdicts: list[ClaimVerdict] = []
        for claim, markers in claims:
            cited = [evidence[m - 1] for m in markers if 1 <= m <= len(evidence)]
            pool = cited or evidence
            supported, note = lexical_support(claim, pool)
            if not markers:
                note += "; no citation"
            verdicts.append(
                ClaimVerdict(
                    claim=claim, cited_markers=markers, supported=supported,
                    method="lexical", note=note,
                )
            )
        return verdicts

    def _verify_llm(
        self, question: str, claims: list[tuple[str, list[int]]], evidence: list[Evidence]
    ) -> list[ClaimVerdict]:
        prompt = build_verify_prompt(question, evidence, claims)
        response = self.llm.complete(
            VERIFY_SYSTEM, [{"role": "user", "content": prompt}], temperature=0.0, max_tokens=800
        )
        try:
            payload = extract_first_json(response.text)
            raw_verdicts = payload.get("verdicts", [])
            by_index = {int(v.get("claim_index", -1)): v for v in raw_verdicts if isinstance(v, dict)}
        except (ParserError, TypeError, ValueError):
            return self._verify_lexical(claims, evidence)
        verdicts: list[ClaimVerdict] = []
        for index, (claim, markers) in enumerate(claims):
            raw = by_index.get(index)
            if raw is None:
                supported, note = lexical_support(
                    claim, [evidence[m - 1] for m in markers if 1 <= m <= len(evidence)] or evidence
                )
                verdicts.append(ClaimVerdict(claim, markers, supported, "lexical", note))
                continue
            verdicts.append(
                ClaimVerdict(
                    claim=claim,
                    cited_markers=markers,
                    supported=bool(raw.get("supported", False)),
                    method="llm",
                    note=str(raw.get("note", ""))[:200],
                )
            )
        return verdicts

    # ------------------------------------------------------------------ main

    def verify(self, question: str, answer: str, evidence: list[Evidence]) -> VerificationReport:
        if answer.strip() == INSUFFICIENT_ANSWER:
            return VerificationReport(
                groundedness=1.0, citation_coverage=1.0, verdicts=[],
                passed=True, method=self.mode,
            )
        claims = split_claims(answer)
        if not claims:
            return VerificationReport(
                groundedness=0.0, citation_coverage=0.0, verdicts=[],
                passed=False, method=self.mode,
            )
        if self.mode == "llm" and evidence:
            verdicts = self._verify_llm(question, claims, evidence)
        else:
            verdicts = self._verify_lexical(claims, evidence)
        supported = sum(1 for v in verdicts if v.supported)
        cited = sum(1 for v in verdicts if v.cited_markers)
        groundedness = round(supported / len(verdicts), 3)
        coverage = round(cited / len(verdicts), 3)
        passed = groundedness >= self.settings.min_groundedness and coverage >= 0.5
        return VerificationReport(
            groundedness=groundedness,
            citation_coverage=coverage,
            verdicts=verdicts,
            passed=passed,
            method=self.mode,
        )


def feedback_from_report(report: VerificationReport) -> str:
    problems = [v for v in report.verdicts if not v.supported or not v.cited_markers]
    lines = []
    for verdict in problems[:6]:
        reason = "unsupported by the cited sources" if not verdict.supported else "missing a citation"
        lines.append(f"- {verdict.claim[:160]} ({reason})")
    return "\n".join(lines) if lines else "- Ensure every sentence is cited and supported."
