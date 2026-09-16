"""Answer relational questions by walking the knowledge graph.

Where vector_search asks "which passage looks like this question",
graph_search asks "what is this question's subject connected to". That is
the difference that matters for a question whose answer is never stated
in one passage: if the corpus says the robot is made by a company, and
separately that the company sits in Munich, no chunk contains both, so
similarity has nothing to rank. Traversal joins them.

Evidence is the chunks the walked edges came from, so the answer is still
grounded in and cited to the source text. The path itself goes into the
observation, which is what makes the route inspectable.
"""

from __future__ import annotations

from agentic_rag.core.types import Evidence, ToolResult
from agentic_rag.kg.traverse import traverse
from agentic_rag.tools.base import Tool, ToolSpec


class GraphSearchTool(Tool):
    def __init__(self, graph_store, chunk_lookup, default_hops: int = 2, max_chunks: int = 6):
        self.graph = graph_store
        self.chunk_lookup = chunk_lookup
        self.default_hops = default_hops
        self.max_chunks = max_chunks
        self.spec = ToolSpec(
            name="graph_search",
            description=(
                "Follow relationships in the knowledge graph between companies, "
                "products, people, standards, and locations. Use this when the "
                "question links things rather than asking for one fact: when it "
                "refers to something by its relationship instead of its name "
                "(\"the company that makes X\", \"whose supplier\"), or when "
                "answering needs two or more facts chained together. For a "
                "single fact stated in one passage, use vector_search instead."
            ),
            parameters={
                "query": "The question, or the entities in it. Names work better than sentences.",
                "hops": "How many relationships to follow (default 2, max 4).",
            },
            required=["query"],
        )

    def run(self, query: str, hops: int | None = None) -> ToolResult:
        if self.graph.edge_count == 0:
            return ToolResult(
                evidence=[],
                observation=(
                    "The knowledge graph is empty. Build it with `rag graph rebuild`, "
                    "or ingest documents with GRAPH_EXTRACTION on."
                ),
            )
        try:
            depth = int(hops) if hops is not None else self.default_hops
        except (TypeError, ValueError):
            depth = self.default_hops
        depth = max(1, min(depth, 4))

        walk = traverse(self.graph, str(query), hops=depth)
        if not walk.seeds:
            return ToolResult(
                evidence=[],
                observation=(
                    f"No graph entities matched {query!r}. The graph knows about named "
                    "companies, products, people, standards, and locations."
                ),
            )
        if walk.empty:
            names = ", ".join(seed["name"] for seed in walk.seeds)
            return ToolResult(
                evidence=[],
                observation=f"Found {names} in the graph, but nothing is linked to it within {depth} hops.",
            )

        evidence: list[Evidence] = []
        for rank, chunk_id in enumerate(walk.chunk_ids[: self.max_chunks]):
            chunk = self.chunk_lookup(chunk_id)
            if chunk is None:
                continue
            title = chunk.title + (f" > {chunk.heading}" if chunk.heading else "")
            evidence.append(
                Evidence(
                    id="",
                    text=chunk.text,
                    source_type="graph",
                    source_ref=chunk.source_ref,
                    title=title,
                    tool_name="graph_search",
                    rank=rank,
                )
            )

        seeds = ", ".join(f"{s['name']} ({s['type']})" for s in walk.seeds)
        reached = ", ".join(f"{n['name']} ({n['type']})" for n in walk.reached)
        observation = (
            f"Graph walk from {seeds}, {depth} hop(s), "
            f"{len(walk.steps)} relationship(s), {len(evidence)} supporting passage(s).\n"
            f"PATH:\n{walk.render_path()}\n"
            f"REACHED: {reached}"
        )
        return ToolResult(evidence=evidence, observation=observation)
