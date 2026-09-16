"""Search over the local index (hybrid keyword + semantic by default)."""

from __future__ import annotations

from agentic_rag.core.types import Evidence, ToolResult
from agentic_rag.retrieval.hybrid import HybridSearcher
from agentic_rag.tools.base import Tool, ToolSpec, preview


class VectorSearchTool(Tool):
    def __init__(self, store: HybridSearcher, default_k: int = 5):
        self.store = store
        self.default_k = default_k
        self.spec = ToolSpec(
            name="vector_search",
            description=(
                "Search over the ingested document corpus, combining keyword "
                "and semantic matching. Best for questions about the knowledge base."
            ),
            parameters={
                "query": "Search query. Use precise keywords, not a full sentence.",
                "k": "Number of results to return (default 5).",
            },
            required=["query"],
        )

    def run(self, query: str, k: int | None = None) -> ToolResult:
        if self.store.count == 0:
            return ToolResult(
                evidence=[],
                observation="The document index is empty. Ingest documents first (rag ingest <path>).",
            )
        try:
            top_k = int(k) if k is not None else self.default_k
        except (TypeError, ValueError):
            top_k = self.default_k
        top_k = max(1, min(top_k, 10))
        hits = self.store.search(str(query), k=top_k)
        if not hits:
            return ToolResult(evidence=[], observation=f"No results for query: {query!r}.")
        evidence: list[Evidence] = []
        lines: list[str] = []
        for rank, (chunk, score) in enumerate(hits):
            title = chunk.title + (f" > {chunk.heading}" if chunk.heading else "")
            evidence.append(
                Evidence(
                    id="",
                    text=chunk.text,
                    source_type="vector",
                    source_ref=chunk.source_ref,
                    title=title,
                    tool_name="vector_search",
                    rank=rank,
                    score=score,
                )
            )
            lines.append(f"  {rank + 1}. [{title}] (score {score:.2f}) {preview(chunk.text)}")
        observation = (
            f"Found {len(hits)} passages for {query!r}. The lines below are shortened "
            "previews; each full passage is already retrieved and will be available in "
            "full when the answer is written, so do not search again just to see the "
            "rest of one.\n" + "\n".join(lines)
        )
        return ToolResult(evidence=evidence, observation=observation)
