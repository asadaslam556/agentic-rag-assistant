"""Deterministic mock LLM for offline demos, tests, and CI.

It implements the same three prompt contracts the real models see
(PLAN, SYNTHESIZE, REFINE) with simple deterministic heuristics:

- PLAN: routes the question to a tool (calculator for arithmetic,
  sql_query when it closely matches one of the database's worked
  examples, knowledge_base for catalog/pricing questions, vector_search
  otherwise), optionally cross-checks with a second tool, then
  finishes.
- SYNTHESIZE: writes an extractive answer by selecting the source
  sentences that best overlap the question, and cites them as [n].

Because the answer is extractive, verification passes honestly and the
whole retrieve -> assemble -> synthesize -> verify loop can be
exercised end to end with no API key and no network access.
"""

from __future__ import annotations

import json
import re

from agentic_rag.core.textutils import content_tokens, split_sentences
from agentic_rag.core.types import INSUFFICIENT_ANSWER
from agentic_rag.llm.base import LLMClient, LLMResponse

# Repetitions are bounded: an arithmetic question is short, and unbounded
# classes here backtrack quadratically on long runs of digits.
_MATH = re.compile(r"\d[\d\s.,]{0,40}[+\-*/x×][\d\s.,()+\-*/x×%]{0,80}\d")
# "12% of 4000". safe_eval reads % as modulo, so this is rewritten rather
# than passed through.
_PERCENT_OF = re.compile(r"(\d[\d.,]{0,20})\s{0,3}%\s{0,3}of\s{1,3}(\d[\d.,]{0,20})", re.IGNORECASE)
# Words that introduce an identifier rather than a sum, so the digits after
# them are a name.
_IDENTIFIER_WORDS = frozenset(
    """iso iec en din ansi ieee soc rfc sku version v model part standard
    type no rev revision chapter section clause annex""".split()
)
_YEAR_RANGE = re.compile(r"^(?:19|20)\d{2}\s*-\s*(?:19|20)\d{2}$")
_KB_HINTS = ("price", "cost", "plan", "sku", "catalog", "lease", "metric", "deployed", "how much")
_WEB_HINTS = ("latest", "news", "current", "today", "recent", "market", "industry", "2025", "2026", "2027")
# Phrases that name something by its relationship instead of its name, which
# is the case similarity search handles worst. Kept narrow on purpose: a
# question that merely mentions two things is not multi-hop, and widening
# this would pull ordinary lookups off vector_search.
_GRAPH_HINTS = (
    "the company that", "the company behind", "the company which", "made by the",
    "built by the", "manufactured by the", "whose", "which company", "who makes",
    "who manufactures", "headquartered in", "supplier", "supply chain",
    "connected to", "related to", "the maker of", "the manufacturer of",
    "from the company", "same company",
)


# The sql_query tool lists worked examples in its description. The mock
# cannot write SQL, so it runs the example whose question it matches. The
# bar is high on purpose: most of the example's words must appear, or an
# ordinary lookup that shares one word ("robots") would land on the database.
_SQL_EXAMPLE = re.compile(r"^\s*Q: (.+)\n\s*SQL: (.+)$", re.MULTILINE)


def match_sql_example(system: str, question: str) -> str:
    """The SQL of the worked example the question closely matches, or ""."""
    question_tokens = content_tokens(question)
    best_sql, best_overlap = "", 0
    for example, sql in _SQL_EXAMPLE.findall(system):
        example_tokens = content_tokens(example)
        overlap = len(question_tokens & example_tokens)
        if overlap >= 2 and overlap >= 0.6 * len(example_tokens) and overlap > best_overlap:
            best_sql, best_overlap = sql.strip(), overlap
    return best_sql


def _is_identifier(question: str, match: re.Match) -> bool:
    """True when the digits are a name rather than a sum.

    "ISO 3691-4:2023" and "P2-450" both look like subtraction to a regex.
    Three signals separate them from arithmetic: the run is glued to letters
    or to identifier punctuation, a word like ISO or version introduces it,
    or it is a span of years.
    """
    text = match.group(0)
    before, after = question[: match.start()], question[match.end() :]
    if before and (before[-1].isalpha() or before[-1] in ":-./"):
        return True
    if after and (after[0].isalpha() or after[0] in ":-./"):
        return True
    if _YEAR_RANGE.match(text.strip()):
        return True
    # A hyphen with no space around it is how identifiers are written, so it
    # only counts as subtraction when nothing else in the question suggests a
    # part number. Spaced subtraction ("100 - 25") is never affected.
    if re.search(r"\d-\d", text):
        words = {word.strip(".,:;?()").lower() for word in question.split()}
        if words & _IDENTIFIER_WORDS:
            return True
    return False


def extract_expression(question: str) -> str:
    percent = _PERCENT_OF.search(question)
    if percent:
        share, whole = (part.replace(",", "") for part in percent.groups())
        return f"{whole} * {share} / 100"
    match = _MATH.search(question)
    if not match or _is_identifier(question, match):
        return ""
    expression = match.group(0).replace("x", "*").replace("×", "*").replace(",", "")
    expression = re.sub(r"[^\d.+\-*/()% ]", "", expression).strip()
    # The pattern starts at a digit, so an opening bracket before the match is
    # left behind: "(12 + 8) / 4" would arrive as "12 + 8) / 4".
    missing = expression.count(")") - expression.count("(")
    if missing > 0:
        expression = "(" * missing + expression
    return expression


class MockLLM(LLMClient):
    supports_vision = True

    name = "mock"
    is_mock = True

    # ------------------------------------------------------------------ plan

    def _plan(self, system: str, messages: list[dict[str, str]]) -> str:
        first_user = next((m["content"] for m in messages if m["role"] == "user"), "")
        question_match = re.search(r"QUESTION:\s*(.+)", first_user)
        question = question_match.group(1).strip() if question_match else first_user.strip()
        question_lower = question.lower()

        used_tools = re.findall(r"OBSERVATION \d+ \((\w+)\)", " ".join(m["content"] for m in messages))

        def available(tool: str) -> bool:
            return f"- {tool}:" in system

        def action(thought: str, name: str, payload: dict) -> str:
            return json.dumps({"thought": thought, "action": name, "action_input": payload})

        if not used_tools:
            expression = extract_expression(question)
            if expression and available("calculator"):
                return action("This is arithmetic; compute it exactly.", "calculator", {"expression": expression})
            if any(hint in question_lower for hint in _GRAPH_HINTS) and available("graph_search"):
                return action(
                    "The question refers to something by its relationships, so walk the graph.",
                    "graph_search",
                    {"query": question},
                )
            sql = match_sql_example(system, question) if available("sql_query") else ""
            if sql:
                return action(
                    "Counts and totals over records are a database query.", "sql_query", {"sql": sql}
                )
            if any(hint in question_lower for hint in _KB_HINTS) and available("knowledge_base"):
                return action(
                    "Pricing or catalog data lives in the structured knowledge base.",
                    "knowledge_base",
                    {"query": question},
                )
            return action("Search the ingested corpus first.", "vector_search", {"query": question})

        # a database result is the exact answer; searching the web after it only
        # adds text that can outrank the row, and makes the eval depend on the
        # network whenever the question happens to mention a year
        if "sql_query" in used_tools:
            return json.dumps(
                {"thought": "The database answered it exactly.", "action": "finish", "action_input": {}}
            )

        if used_tools == ["knowledge_base"] and available("vector_search"):
            return action(
                "Cross-check the structured record against the document corpus.",
                "vector_search",
                {"query": question},
            )

        if (
            "web_search" not in used_tools
            and available("web_search")
            and any(hint in question_lower for hint in _WEB_HINTS)
        ):
            return action(
                "The question asks about current outside information, so search the web.",
                "web_search",
                {"query": question},
            )

        return json.dumps(
            {"thought": "Enough evidence has been collected.", "action": "finish", "action_input": {}}
        )

    # ------------------------------------------------------------ synthesize

    @staticmethod
    def _parse_sources(prompt: str) -> list[tuple[int, str]]:
        sources: list[tuple[int, str]] = []
        section = prompt.split("SOURCES:", 1)[-1]
        section = section.split("\nEND OF SOURCES")[0]
        for block in section.split("\n---\n"):
            # each block is "[n] title :: ref" on the first line, then the text
            header, _, body = block.strip().partition("\n")
            match = re.match(r"\[(\d+)\]\s", header)
            if match and body:
                sources.append((int(match.group(1)), body.strip()))
        return sources

    def _synthesize(self, prompt: str) -> str:
        question_match = re.search(r"QUESTION:\s*(.+)", prompt)
        question = question_match.group(1).strip() if question_match else ""
        question_tokens = content_tokens(question)
        sources = self._parse_sources(prompt)
        if not sources:
            return INSUFFICIENT_ANSWER

        scored: list[tuple[int, int, int, str]] = []  # (score, marker, order, sentence)
        for order, (marker, text) in enumerate(sources):
            for sentence in split_sentences(text):
                overlap = len(question_tokens & content_tokens(sentence))
                if overlap:
                    scored.append((overlap, marker, order, sentence))
        if not scored:
            return INSUFFICIENT_ANSWER

        scored.sort(key=lambda item: (-item[0], item[2]))
        best_score, best_marker, _, best_sentence = scored[0]
        answer_parts = [f"{best_sentence} [{best_marker}]"]
        seen = {best_sentence}
        for overlap, marker, _, sentence in scored[1:]:
            if sentence in seen or overlap < max(2, best_score - 1):
                continue
            if marker == best_marker and len(answer_parts) >= 1 and overlap < best_score:
                continue
            answer_parts.append(f"{sentence} [{marker}]")
            seen.add(sentence)
            if len(answer_parts) >= 2:
                break
        return " ".join(answer_parts)

    # -------------------------------------------------------------- dispatch

    def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float | None = 0.1,
        max_tokens: int = 1200,
    ) -> LLMResponse:
        if "MODE: PLAN" in system:
            return LLMResponse(text=self._plan(system, messages))
        if "MODE: SYNTHESIZE" in system:
            prompt = messages[-1]["content"] if messages else ""
            return LLMResponse(text=self._synthesize(prompt))
        return LLMResponse(text=INSUFFICIENT_ANSWER)

    def complete_stream(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float | None = 0.1,
        max_tokens: int = 1200,
    ):
        """Stream synthesis output in small word groups so the console's
        live view can be exercised offline and deterministically."""
        text = self.complete(system, messages, temperature=temperature, max_tokens=max_tokens).text
        if "MODE: SYNTHESIZE" not in system or not text:
            yield text
            return
        words = text.split(" ")
        for start in range(0, len(words), 4):
            piece = " ".join(words[start : start + 4])
            yield piece if start == 0 else " " + piece

    def complete_vision(
        self,
        system: str,
        prompt: str,
        images: list[bytes],
        temperature: float | None = 0.0,
        max_tokens: int = 900,
    ):
        """A fixed, obviously synthetic description, so vision ingestion can be
        exercised end to end without a real model or a network."""
        return LLMResponse(
            text=(
                f"Page overview generated without a vision model. The page holds "
                f"{len(images)} rendered image(s). Figures, charts, and tables on this "
                "page are not described because the mock provider cannot see them."
            )
        )
