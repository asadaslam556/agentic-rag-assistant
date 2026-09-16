"""End-to-end sanity check with zero third-party test dependencies.

Runs the full offline pipeline (mock LLM, local embeddings) against a
temporary index and verifies a grounded, cited, verified answer comes
back. Useful on machines where installing pytest is not an option.

Usage:  python scripts/quickcheck.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentic_rag.config import Settings  # noqa: E402
from agentic_rag.pipeline import AgenticRAG  # noqa: E402


def main() -> int:
    # ignore_cleanup_errors keeps Windows file locks from failing the run
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        settings = Settings(
            llm_provider="mock",
            embeddings_provider="local",
            search_provider="none",
            storage_dir=str(Path(tmp) / "storage"),
            catalog_path=str(ROOT / "data" / "structured" / "catalog.json"),
        )
        rag = AgenticRAG(settings)

        stats = rag.ingest(ROOT / "data" / "sample_docs")
        print(f"ingest: {stats['files_added']} files, {stats['chunks_added']} chunks")
        if stats["chunks_added"] < 10:
            print("FAIL: expected at least 10 chunks")
            rag.close()
            return 1

        answer = rag.ask("What is the payload capacity of the Atlas P2?")
        print(f"answer: {answer.text}")
        report = answer.verification
        print(
            f"verification: passed={report.passed} "
            f"groundedness={report.groundedness:.0%} coverage={report.citation_coverage:.0%}"
        )
        checks = [
            ("payload fact present", "450" in answer.text),
            ("citation attached", bool(answer.citations)),
            ("verification passed", report.passed),
            ("agent used vector_search", any(s.action == "vector_search" for s in answer.steps)),
        ]
        ok = True
        for label, result in checks:
            print(f"  [{'ok' if result else '!!'}] {label}")
            ok = ok and result
        print("PASS" if ok else "FAIL")
        rag.close()  # release the graph file before the temp dir is removed
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
