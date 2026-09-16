"""Search document pages as pictures rather than as text.

Two ways to rank a page, chosen with VISUAL_RETRIEVER:

- colpali embeds the page image itself and scores with late interaction,
  so a chart is matched as a chart. Needs the colpali extra and real
  hardware to be quick.
- description scores the page description written at ingest time by a
  vision model, which needs nothing extra and rides on the normal text
  embedder.

Either way the evidence carries the page image path, so synthesis can
look at the actual page when it writes the answer.
"""

from __future__ import annotations

from agentic_rag.core.textutils import content_tokens
from agentic_rag.core.types import Evidence, ToolResult
from agentic_rag.retrieval.late_interaction import PageIndex
from agentic_rag.tools.base import Tool, ToolSpec


class VisualSearchTool(Tool):
    def __init__(self, index: PageIndex, embedder=None, encoder=None, default_k: int = 3):
        self.index = index
        self.embedder = embedder
        self.encoder = encoder
        self.default_k = default_k
        self.spec = ToolSpec(
            name="visual_search",
            description=(
                "Search pages of documents by what they show: charts, diagrams, "
                "tables, and figures. Use when a question is about a trend, a "
                "quantity read off a chart, a layout, or anything a picture in "
                "the documents would answer."
            ),
            parameters={
                "query": "What to look for on the page",
                "k": "How many pages to return (optional, default 3)",
            },
            required=["query"],
        )

    def run(self, query: str, k: int | None = None) -> ToolResult:
        top_k = int(k or self.default_k)
        if self.index.count == 0:
            return ToolResult(
                evidence=[],
                observation="No document pages have been indexed as images.",
            )

        hits = self._colpali_hits(query, top_k) if self.encoder else self._description_hits(query, top_k)
        if not hits:
            return ToolResult(evidence=[], observation=f"No pages matched {query!r}.")

        evidence: list[Evidence] = []
        lines: list[str] = []
        for rank, (record, score) in enumerate(hits):
            body = record.description or f"Page {record.page_number} of {record.title}."
            evidence.append(
                Evidence(
                    id=record.id,
                    text=body,
                    source_type="page",
                    source_ref=f"{record.source_path}#page{record.page_number}",
                    title=f"{record.title} (page {record.page_number})",
                    tool_name=self.spec.name,
                    rank=rank,
                    score=float(score),
                    image_path=record.image_path,
                )
            )
            lines.append(f"page {record.page_number} of {record.title} (score {score:.2f})")
        return ToolResult(
            evidence=evidence,
            observation=f"Found {len(evidence)} page(s): " + "; ".join(lines),
        )

    def _colpali_hits(self, query: str, k: int):
        query_vectors = self.encoder.embed_query(query)
        return self.index.search(query_vectors, k=k)

    def _description_hits(self, query: str, k: int):
        """Rank descriptions by embedding similarity, with token overlap as backup."""
        records = [record for record in self.index.records() if record.description]
        if not records:
            return []
        if self.embedder is not None:
            import numpy as np

            query_vector = self.embedder.embed_texts([query])[0]
            matrix = self.embedder.embed_texts([record.description for record in records])
            scores = np.asarray(matrix) @ np.asarray(query_vector)
        else:
            query_tokens = content_tokens(query)
            scores = [
                len(query_tokens & content_tokens(record.description)) / (len(query_tokens) or 1)
                for record in records
            ]
        ranked = sorted(zip(records, scores, strict=True), key=lambda pair: -float(pair[1]))[:k]
        best = float(ranked[0][1]) or 1.0
        return [(record, round(float(score) / best, 4)) for record, score in ranked if float(score) > 0]
