"""Command line interface.

Commands: ingest, ask, chat, eval, models, stats, graph, reindex, reset, serve.
Zero-dependency output (ANSI colors degrade to plain text on
non-interactive terminals and legacy Windows consoles).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from agentic_rag.config import Settings
from agentic_rag.core.console import paint, rule
from agentic_rag.core.types import Answer
from agentic_rag.pipeline import AgenticRAG


def _build_pipeline() -> AgenticRAG:
    try:
        return AgenticRAG(Settings.from_env())
    except RuntimeError as exc:
        print(paint(f"Configuration error: {exc}", "red"), file=sys.stderr)
        raise SystemExit(2) from exc


def _print_answer(answer: Answer, show_trace: bool = False) -> None:
    print()
    print(rule("ANSWER"))
    print(answer.text)
    if answer.citations:
        print()
        print(rule("SOURCES"))
        for citation in answer.citations:
            label = f"[{citation.marker}]"
            location = citation.url or citation.source_ref
            print(f"  {paint(label, 'bold')} {citation.title}  {paint(f'({citation.source_type})', 'dim')}")
            print(f"      {paint(location, 'dim')}")
    report = answer.verification
    print()
    print(rule("VERIFICATION"))
    status = paint("PASSED", "green", "bold") if report.passed else paint("NEEDS REVIEW", "yellow", "bold")
    print(
        f"  {status}  groundedness {report.groundedness:.0%}  "
        f"citation coverage {report.citation_coverage:.0%}  method {report.method}"
        + (f"  refine attempts {answer.attempts}" if answer.attempts else "")
    )
    for verdict in report.verdicts:
        mark = paint("[ok]", "green") if verdict.supported else paint("[!!]", "red")
        print(f"  {mark} {verdict.claim[:96]}{'...' if len(verdict.claim) > 96 else ''}")
    if show_trace and answer.steps:
        print()
        print(rule("AGENT TRACE"))
        for step in answer.steps:
            arguments = json.dumps(step.action_input, ensure_ascii=False)
            print(f"  {step.step}. {paint(step.action, 'cyan')} {arguments}")
            if step.thought:
                print(f"     thought: {paint(step.thought, 'dim')}")
            preview = step.observation.splitlines()[0][:110] if step.observation else ""
            print(f"     -> {paint(preview, 'dim')}")
    timings = answer.timings_ms
    print()
    print(
        paint(
            f"total {timings.get('total_ms', 0)} ms  "
            f"(retrieve {timings.get('retrieve_ms', 0)}, assemble {timings.get('assemble_ms', 0)}, "
            f"synthesize {timings.get('synthesize_ms', 0)}, verify {timings.get('verify_ms', 0)})",
            "dim",
        )
    )


# ------------------------------------------------------------------ commands


def cmd_ingest(args: argparse.Namespace) -> int:
    rag = _build_pipeline()
    path = Path(args.path)
    if not path.exists():
        print(paint(f"Path not found: {path}", "red"), file=sys.stderr)
        return 2
    stats = rag.ingest(path)
    print(paint("Ingestion complete.", "green", "bold"))
    for key, value in stats.items():
        print(f"  {key}: {value}")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    rag = _build_pipeline()
    answer = rag.ask(args.question)
    if args.json:
        print(json.dumps(answer.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_answer(answer, show_trace=args.trace)
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    rag = _build_pipeline()
    print(paint("Agentic RAG chat. Type 'exit' to quit.", "bold"))
    print(paint(f"llm={rag.llm.name}  embedder={rag.embedder.name}  chunks={rag.store.count}", "dim"))
    history: list[dict] = []
    while True:
        try:
            question = input(paint("\nyou> ", "cyan", "bold")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not question:
            continue
        if question.lower() in {"exit", "quit", "q"}:
            return 0
        answer = rag.chat(question, history=history)
        if answer.rewritten_question:
            print(paint(f"  (interpreted as: {answer.rewritten_question})", "dim"))
        _print_answer(answer, show_trace=args.trace)
        history.append({"question": question, "answer": answer.text})
        history = history[-6:]


def cmd_models(args: argparse.Namespace) -> int:
    """Ask the configured endpoint what it serves and flag the active model."""
    from agentic_rag.llm.discovery import active_model, list_endpoint_models

    settings = Settings.from_env()
    print(rule(f"MODELS: provider {settings.llm_provider}"))
    try:
        names, source = list_endpoint_models(settings)
    except RuntimeError as exc:
        print(paint(str(exc), "red"), file=sys.stderr)
        return 2
    current = active_model(settings)
    for name in names:
        marker = paint("  <- in use", "green") if name == current else ""
        print(f"  {name}{marker}")
    print(paint(f"\n  source: {source}", "dim"))
    if current and current not in names:
        print(
            paint(
                f"  note: the configured model {current} is not in that list. Copy one of the names above.",
                "yellow",
            )
        )
    elif not current:
        print(paint("  note: no model is configured, so one is picked automatically.", "dim"))
    return 0


def cmd_stats(args: argparse.Namespace) -> int:  # noqa: ARG001
    rag = _build_pipeline()
    print(paint("Pipeline configuration", "bold"))
    print(f"  llm: {rag.llm.name}")
    if rag.router.is_split():
        print(paint("  model routing", "dim"))
        for role, model in rag.router.describe().items():
            print(f"    {role:<11} {model}")
    print(f"  embedder: {rag.embedder.name}")
    print(f"  search provider: {rag.settings.search_provider}")
    print(f"  verifier mode: {rag.verifier.mode}")
    print(f"  reranker: {rag.reranker.name if rag.reranker is not None else 'none'}")
    print(f"  tools: {', '.join(rag.tools)}")
    print(paint("Index", "bold"))
    for key, value in rag.store.stats().items():
        print(f"  {key}: {value}")
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    if not args.yes:
        confirm = input("Delete the vector index and any page images? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return 1
    rag = _build_pipeline()
    rag.store.clear()
    # page records and rendered images live beside the text index and would
    # otherwise survive a reset and be duplicated on the next ingest
    pages = rag.pages.count
    rag.pages.clear()
    # the graph points at chunk ids, so leaving it behind would strand every
    # entity on a chunk that no longer exists
    entities = 0
    if rag.knowledge_graph is not None:
        entities = rag.knowledge_graph.entity_count
        rag.knowledge_graph.clear()
    parts = ["Index cleared"]
    if pages:
        parts.append(f"{pages} indexed page(s)")
    if entities:
        parts.append(f"{entities} graph entities")
    message = parts[0] + "." if len(parts) == 1 else parts[0] + ", along with " + " and ".join(parts[1:]) + "."
    print(paint(message, "green"))
    return 0


def cmd_graph(args: argparse.Namespace) -> int:
    """rebuild, stats, or explain for the knowledge graph."""
    from agentic_rag.config import Settings
    from agentic_rag.kg import build as kg_build

    settings = Settings.from_env()

    if args.graph_command == "stats":
        info = kg_build.stats(settings)
        print(paint("Knowledge graph", "bold"))
        for key, value in info.items():
            print(f"  {key}: {value}")
        return 0

    if args.graph_command == "rebuild":
        result = kg_build.rebuild(settings)
        if result["status"] == "empty":
            print(paint(result["message"], "red"), file=sys.stderr)
            return 1
        print(paint("Graph rebuild complete.", "green"))
        for key, value in result.items():
            if key != "status":
                print(f"  {key}: {value}")
        return 0

    # explain: show the walk behind an answer without running the agent
    from agentic_rag.kg.store import get_graph_store
    from agentic_rag.kg.traverse import traverse

    store = get_graph_store(settings)
    if store.edge_count == 0:
        print(paint("The graph is empty. Run `rag graph rebuild`.", "red"), file=sys.stderr)
        return 1
    hops = args.hops if args.hops is not None else settings.graph_hops
    walk = traverse(store, args.question, hops=hops)
    print(paint(f"QUESTION: {args.question}", "bold"))
    if not walk.seeds:
        print(paint("No graph entities matched the question.", "red"))
        return 1
    print("\nSEEDS")
    for seed in walk.seeds:
        print(f"  {seed['name']} ({seed['type']})")
    print(f"\nPATH ({hops} hop max)")
    print(walk.render_path())
    print("\nREACHED")
    for node in walk.reached:
        print(f"  {node['name']} ({node['type']})")
    print("\nSUPPORTING SENTENCES")
    for step in walk.steps:
        if step.sentence:
            print(f"  [{step.type}] {step.sentence[:150]}")
    print(f"\nsupporting chunks: {len(walk.chunk_ids)}")
    return 0


def cmd_reindex(args: argparse.Namespace) -> int:
    """Re-embed stored chunks with the current embedder, keeping the documents."""
    from agentic_rag.retrieval.reindex import reindex

    result = reindex(keep_backup=not args.no_backup)
    if result["status"] == "empty":
        print(paint(result["message"], "red"), file=sys.stderr)
        return 1
    print(paint("Re-index complete.", "green"))
    for key in ("chunks", "documents", "previous_embedder", "embedder", "dim", "bm25_terms", "backup"):
        value = result.get(key)
        if value not in ("", None):
            print(f"  {key}: {value}")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    rag = _build_pipeline()
    golden_path = Path(args.golden)
    if not golden_path.exists():
        print(paint(f"Golden set not found: {golden_path}", "red"), file=sys.stderr)
        return 2
    cases = [
        json.loads(line)
        for line in golden_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.judge:
        from agentic_rag.verification.judge import judge_answer
    results = []
    print(rule(f"EVAL: {len(cases)} questions"))
    for case in cases:
        answer = rag.ask(case["question"])
        text_lower = answer.text.lower()
        correct = all(sub.lower() in text_lower for sub in case.get("expected_substrings", []))
        cited = bool(answer.citations)
        # tool correctness: did the agent reach for the tools this case needs
        used_tools = {step.action for step in answer.steps if step.action != "finish"}
        expected_tools = set(case.get("expected_tools", []))
        tools_ok = expected_tools.issubset(used_tools) if expected_tools else True
        row = {
            "id": case.get("id", ""),
            "question": case["question"],
            "category": case.get("category", "uncategorised"),
            "difficulty": case.get("difficulty", "unknown"),
            "correct": correct,
            "cited": cited,
            "tools_ok": tools_ok,
            "expected_tools": sorted(expected_tools),
            "used_tools": sorted(used_tools),
            "groundedness": answer.verification.groundedness,
            "passed_verification": answer.verification.passed,
            "latency_ms": answer.timings_ms.get("total_ms", 0),
        }
        judge_note = ""
        if args.judge:
            scores = judge_answer(
                rag.router.client_for("judge"), case["question"], answer.text, answer.evidence
            )
            row["judge"] = scores
            judge_note = f"faith {scores['faithfulness']:.0%}  "
        results.append(row)
        # three separate checks: name the ones that missed, so a row that only
        # picked a different tool doesn't read like a wrong answer
        missed = [
            label
            for label, ok in (("answer", correct), ("citations", cited), ("tools", tools_ok))
            if not ok
        ]
        mark = paint("PASS", "green") if not missed else paint("FAIL", "red")
        reason = paint(f"  missed: {', '.join(missed)}", "yellow") if missed else ""
        print(
            f"  {mark}  {case.get('id', '?'):<16} grounded {answer.verification.groundedness:.0%}  "
            f"tools {'ok ' if tools_ok else 'miss'}  {judge_note}"
            f"{answer.timings_ms.get('total_ms', 0)} ms  {case['question'][:44]}{reason}"
        )
    total = len(results)
    correct_count = sum(1 for r in results if r["correct"])
    cited_count = sum(1 for r in results if r["cited"])
    avg_grounded = sum(r["groundedness"] for r in results) / total if total else 0.0
    avg_latency = sum(r["latency_ms"] for r in results) / total if total else 0
    print(rule("SUMMARY"))
    print(f"  answer correctness: {correct_count}/{total}")
    print(f"  answers with citations: {cited_count}/{total}")
    print(f"  average groundedness: {avg_grounded:.0%}")
    print(f"  average latency: {avg_latency:.0f} ms")
    tool_hits = sum(1 for r in results if r["tools_ok"])
    print(f"  expected tools called: {tool_hits}/{len(results)}")

    categories: dict[str, list] = {}
    for row_result in results:
        categories.setdefault(row_result["category"], []).append(row_result)
    if len(categories) > 1:
        print(paint("\n  by category", "dim"))
        for name in sorted(categories):
            rows_in = categories[name]
            passed = sum(1 for r in rows_in if r["correct"] and r["cited"] and r["tools_ok"])
            print(f"    {name:<20} {passed}/{len(rows_in)}")
    if args.judge:
        judged = [r["judge"] for r in results if "judge" in r]
        if judged:
            avg_faith = sum(j["faithfulness"] for j in judged) / len(judged)
            avg_rel = sum(j["relevance"] for j in judged) / len(judged)
            print(f"  average faithfulness (judge): {avg_faith:.0%}")
            print(f"  average relevance (judge): {avg_rel:.0%}")
    report_path = rag.settings.storage_path / "eval_report.json"
    report_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(paint(f"  report written to {report_path}", "dim"))
    return 0 if correct_count == total else 1


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        print(
            paint("The API server needs fastapi and uvicorn: pip install fastapi uvicorn", "red"),
            file=sys.stderr,
        )
        return 2
    from agentic_rag.api import FRONTEND_DIST, create_app

    app = create_app()
    base = f"http://{args.host}:{args.port}"
    if FRONTEND_DIST.exists():
        print(paint(f"Console: {base}   API: {base}/api   Docs: {base}/docs", "bold"))
    else:
        print(paint(f"API: {base}/api   Docs: {base}/docs", "bold"))
        print(
            paint(
                "Web console not built yet. Build it once with: cd frontend && npm install && npm run build",
                "dim",
            )
        )
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


# --------------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rag",
        description="Agentic RAG knowledge assistant: retrieve, verify, and answer with citations.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Ingest documents into the vector index")
    p_ingest.add_argument("path", nargs="?", default="data/sample_docs", help="File or directory")
    p_ingest.set_defaults(func=cmd_ingest)

    p_ask = sub.add_parser("ask", help="Ask one question")
    p_ask.add_argument("question")
    p_ask.add_argument("--trace", action="store_true", help="Show the agent's tool decisions")
    p_ask.add_argument("--json", action="store_true", help="Print the full Answer as JSON")
    p_ask.set_defaults(func=cmd_ask)

    p_chat = sub.add_parser("chat", help="Interactive question loop")
    p_chat.add_argument("--trace", action="store_true")
    p_chat.set_defaults(func=cmd_chat)

    p_eval = sub.add_parser("eval", help="Run the golden-set evaluation")
    p_eval.add_argument("--golden", default="eval/golden_set.jsonl")
    p_eval.add_argument(
        "--judge",
        action="store_true",
        help="Also score faithfulness and relevance (LLM judge with real models, lexical with the mock)",
    )
    p_eval.set_defaults(func=cmd_eval)

    p_models = sub.add_parser("models", help="List the models the configured endpoint serves")
    p_models.set_defaults(func=cmd_models)

    p_stats = sub.add_parser("stats", help="Show configuration and index statistics")
    p_stats.set_defaults(func=cmd_stats)

    p_graph = sub.add_parser("graph", help="Knowledge graph: rebuild, stats, explain")
    graph_sub = p_graph.add_subparsers(dest="graph_command", required=True)
    graph_sub.add_parser("stats", help="Entity and relationship counts")
    graph_sub.add_parser("rebuild", help="Rebuild the graph from stored chunks")
    p_explain = graph_sub.add_parser(
        "explain", help="Show the entities and relationships a question traverses"
    )
    p_explain.add_argument("question")
    p_explain.add_argument("--hops", type=int, default=None, help="How many relationships to follow")
    p_graph.set_defaults(func=cmd_graph)

    p_reindex = sub.add_parser(
        "reindex",
        help="Rebuild the index with the current embedder, keeping ingested documents",
    )
    p_reindex.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip the chunks.jsonl.bak copy taken before rebuilding",
    )
    p_reindex.set_defaults(func=cmd_reindex)

    p_reset = sub.add_parser("reset", help="Delete the vector index")
    p_reset.add_argument("--yes", action="store_true", help="Skip confirmation")
    p_reset.set_defaults(func=cmd_reset)

    p_serve = sub.add_parser("serve", help="Run the REST API (needs fastapi + uvicorn)")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print()
        return 130
    except BrokenPipeError:
        # piping into head closes stdout early, exit quietly like any unix tool
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
