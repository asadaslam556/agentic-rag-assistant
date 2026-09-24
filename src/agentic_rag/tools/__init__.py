"""Tool registry: builds the toolset exposed to the orchestrator."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from agentic_rag.config import Settings
from agentic_rag.retrieval.hybrid import HybridSearcher
from agentic_rag.tools.base import Tool
from agentic_rag.tools.structured import CalculatorTool, KnowledgeBaseTool
from agentic_rag.tools.vector_search import VectorSearchTool
from agentic_rag.tools.web_search import WebSearchTool


def build_default_tools(
    settings: Settings,
    searcher: HybridSearcher,
    page_index=None,
    embedder=None,
    encoder=None,
    graph_store=None,
    chunk_lookup=None,
) -> dict[str, Tool]:
    tools: dict[str, Tool] = {}
    vector = VectorSearchTool(searcher, default_k=settings.retrieval_k)
    tools[vector.spec.name] = vector
    if settings.search_provider != "none":
        web = WebSearchTool(settings)
        tools[web.spec.name] = web
    knowledge = KnowledgeBaseTool(settings.catalog_path)
    tools[knowledge.spec.name] = knowledge
    calculator = CalculatorTool()
    tools[calculator.spec.name] = calculator
    if settings.sql_database_path and Path(settings.sql_database_path).is_file():
        from agentic_rag.tools.sql import SQLTool

        try:
            sql = SQLTool(settings.sql_database_path)
            tools[sql.spec.name] = sql
        except (sqlite3.Error, OSError, UnicodeDecodeError) as exc:
            # a broken database costs this one tool, not the assistant
            print(f"note: sql_query disabled, {settings.sql_database_path}: {exc}", file=sys.stderr)
    # offered only once the graph actually holds edges, so the planner never
    # sees a tool whose only possible answer is 'nothing here'
    if graph_store is not None and chunk_lookup is not None and graph_store.edge_count:
        from agentic_rag.tools.graph_search import GraphSearchTool

        graph = GraphSearchTool(graph_store, chunk_lookup, default_hops=settings.graph_hops)
        tools[graph.spec.name] = graph
    # only offered when pages have actually been indexed as images, so the
    # planner never sees a tool that can only answer 'nothing here'
    if page_index is not None and page_index.count:
        from agentic_rag.tools.visual_search import VisualSearchTool

        visual = VisualSearchTool(page_index, embedder=embedder, encoder=encoder,
                                  default_k=max(2, settings.retrieval_k // 2))
        tools[visual.spec.name] = visual
    return tools


def render_tool_catalog(tools: dict[str, Tool]) -> str:
    return "\n".join(tool.spec.render() for tool in tools.values())


__all__ = ["Tool", "build_default_tools", "render_tool_catalog"]
