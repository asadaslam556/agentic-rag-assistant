"""Live web search with pluggable providers.

Providers:
- tavily:  https://tavily.com API (TAVILY_API_KEY required)
- ddgs:    keyless DuckDuckGo search via the `ddgs` package
- fixture: canned results from a local JSON file (tests / offline demos)
- none:    tool is not registered at all
"""

from __future__ import annotations

import json
from pathlib import Path

from agentic_rag.config import Settings
from agentic_rag.core.http import post_json
from agentic_rag.core.types import Evidence, ToolResult
from agentic_rag.tools.base import Tool, ToolSpec

_MAX_RESULTS = 5
_SNIPPET_CHARS = 700


class WebSearchTool(Tool):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.spec = ToolSpec(
            name="web_search",
            description=(
                "Search the live web. Best for current events, external facts, "
                "and anything not in the ingested corpus."
            ),
            parameters={"query": "Web search query."},
            required=["query"],
        )

    # ------------------------------------------------------------- providers

    def _search_tavily(self, query: str) -> list[dict]:
        response = post_json(
            "https://api.tavily.com/search",
            {
                "api_key": self.settings.tavily_api_key,
                "query": query,
                "max_results": _MAX_RESULTS,
                "include_answer": False,
            },
            timeout=self.settings.request_timeout,
        )
        return [
            {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
            for r in response.get("results", [])
        ]

    def _search_ddgs(self, query: str) -> list[dict]:  # pragma: no cover
        try:
            from ddgs import DDGS
        except ImportError:
            try:
                from duckduckgo_search import DDGS  # older package name
            except ImportError as exc:
                raise RuntimeError(
                    "SEARCH_PROVIDER=ddgs requires the ddgs package: pip install ddgs"
                ) from exc
        with DDGS() as client:
            raw = list(client.text(query, max_results=_MAX_RESULTS))
        return [
            {"title": r.get("title", ""), "url": r.get("href", r.get("url", "")), "content": r.get("body", "")}
            for r in raw
        ]

    def _search_fixture(self, query: str) -> list[dict]:
        path = Path(self.settings.web_fixtures_path)
        if not path.exists():
            return []
        fixtures = json.loads(path.read_text(encoding="utf-8"))
        query_lower = query.lower()
        for entry in fixtures:
            if entry.get("query_contains", "").lower() in query_lower:
                return entry.get("results", [])
        return []

    # ------------------------------------------------------------------ run

    def run(self, query: str) -> ToolResult:
        provider = self.settings.search_provider
        if provider == "tavily":
            results = self._search_tavily(str(query))
        elif provider == "ddgs":
            results = self._search_ddgs(str(query))
        elif provider == "fixture":
            results = self._search_fixture(str(query))
        else:
            return ToolResult(evidence=[], observation="Web search is not configured (SEARCH_PROVIDER=none).")
        if not results:
            return ToolResult(evidence=[], observation=f"Web search returned no results for {query!r}.")
        evidence: list[Evidence] = []
        lines: list[str] = []
        for rank, result in enumerate(results[:_MAX_RESULTS]):
            content = (result.get("content") or "")[:_SNIPPET_CHARS]
            title = result.get("title") or result.get("url") or "web result"
            evidence.append(
                Evidence(
                    id="",
                    text=content,
                    source_type="web",
                    source_ref=result.get("url", ""),
                    title=title,
                    tool_name="web_search",
                    rank=rank,
                    url=result.get("url", ""),
                )
            )
            lines.append(f"  {rank + 1}. [{title}] {content[:140]}...")
        return ToolResult(
            evidence=evidence,
            observation=f"Web search found {len(evidence)} results for {query!r}:\n" + "\n".join(lines),
        )
