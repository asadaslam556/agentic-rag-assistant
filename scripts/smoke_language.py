"""Live smoke test: ask a German question and check the answer comes back in German.

This is the check the offline suite cannot make. The deterministic mock
answers by quoting retrieved sentences, so it only ever proves that a
German question routes to German evidence. Whether a real model obeys the
ANSWER LANGUAGE rule in the synthesis prompt can only be seen by asking
one, which needs a key and a network, so it lives here rather than in
pytest.

Usage:
    python scripts/smoke_language.py
    python scripts/smoke_language.py "Welche Sicherheitsnorm erfuellt die Plattform?"

Configure the provider first, in .env or the shell:
    LLM_PROVIDER=anthropic
    ANTHROPIC_API_KEY=sk-ant-...
    ANTHROPIC_MODEL=claude-sonnet-5@default     # whatever your endpoint serves
    ANTHROPIC_BASE_URL=https://api.anthropic.com

Exit codes: 0 answered in German, 1 answered in another language,
2 the provider is not configured, 3 the index is empty.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentic_rag.config import Settings  # noqa: E402
from agentic_rag.core.lang import detect_language, language_name  # noqa: E402
from agentic_rag.llm.providers import ProviderError  # noqa: E402

DEFAULT_QUESTION = "Wie hoch ist die Traglast der Atlas P2?"


def main() -> int:
    question = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUESTION
    settings = Settings.from_env()

    try:
        from agentic_rag.pipeline import AgenticRAG

        rag = AgenticRAG(settings)
    except ProviderError as exc:
        # A missing key or an unreachable host is a setup problem, not a bug,
        # so it gets a sentence instead of a stack trace.
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    print(f"provider: {settings.llm_provider}")
    print(f"model:    {rag.llm.name}")
    if getattr(rag.llm, "is_mock", False):
        print(
            "note: this is the offline mock, which quotes its sources rather than "
            "writing new text. It cannot prove a real model follows the language "
            "rule. Set LLM_PROVIDER and a key to test that.",
            file=sys.stderr,
        )
    if rag.store.count == 0:
        print(
            f"The index at {settings.index_path} is empty. "
            "Run: rag ingest data/sample_docs_multilingual",
            file=sys.stderr,
        )
        return 3

    asked = detect_language(question)
    print(f"question ({language_name(asked)}): {question}\n")
    try:
        answer = rag.ask(question)
    except ProviderError as exc:
        print(f"Provider error: {exc}", file=sys.stderr)
        return 2

    print(f"answer:   {answer.text}\n")
    got = detect_language(answer.text)
    print(f"asked in {language_name(asked)}, answered in {language_name(got)}")
    if got == asked:
        print("PASS: the answer is in the language of the question.")
        return 0
    print(
        "FAIL: the answer language does not match the question. "
        "Check that the model is following the ANSWER LANGUAGE line in the "
        "synthesis prompt.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
