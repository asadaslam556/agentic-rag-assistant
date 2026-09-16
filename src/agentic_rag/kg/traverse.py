"""Walk the graph from the entities a question names.

Two steps. Link the question to seed nodes by matching entity names and
recorded surface forms against its text, then breadth-first out to k
hops, keeping the edges walked so the route can be shown.

The path is the point. A vector hit says a passage looked similar; a
traversal says the answer is two edges from something the question named,
and can name both edges. That is what makes a relational answer checkable
rather than plausible.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from agentic_rag.kg.store import StoredEdge


@dataclass
class TraversalStep:
    source: str  # display name
    target: str
    type: str
    hop: int
    chunk_id: str
    sentence: str = ""

    def render(self) -> str:
        return f"{self.source} -[{self.type}]-> {self.target}"


@dataclass
class Traversal:
    seeds: list[dict] = field(default_factory=list)
    steps: list[TraversalStep] = field(default_factory=list)
    reached: list[dict] = field(default_factory=list)
    chunk_ids: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.steps

    def render_path(self) -> str:
        if not self.steps:
            return "(no path)"
        return "\n".join(f"  hop {step.hop}: {step.render()}" for step in self.steps)


def _edge_view(store, edge: StoredEdge, entity_id: str) -> tuple[str, dict, dict]:
    """Orient an edge so it reads outward from the node we arrived at."""
    source = store.entity(edge.source_id) or {"id": edge.source_id, "name": edge.source_id}
    target = store.entity(edge.target_id) or {"id": edge.target_id, "name": edge.target_id}
    other = target if edge.source_id == entity_id else source
    return other["id"], source, target


def traverse(store, question: str, hops: int = 2, max_nodes: int = 40) -> Traversal:
    """Breadth-first from the question's entities, out to `hops` edges."""
    seeds = store.find_entities(question)
    result = Traversal(seeds=seeds)
    if not seeds:
        return result

    seen: set[str] = {seed["id"] for seed in seeds}
    reached: dict[str, dict] = {seed["id"]: seed for seed in seeds}
    queue: deque[tuple[str, int]] = deque((seed["id"], 0) for seed in seeds)

    while queue and len(seen) < max_nodes:
        entity_id, depth = queue.popleft()
        if depth >= hops:
            continue
        for edge in store.neighbours(entity_id):
            other_id, source, target = _edge_view(store, edge, entity_id)
            result.steps.append(
                TraversalStep(
                    source=source["name"],
                    target=target["name"],
                    type=edge.type,
                    hop=depth + 1,
                    chunk_id=edge.chunk_id,
                    sentence=edge.sentence,
                )
            )
            if other_id not in seen:
                seen.add(other_id)
                node = store.entity(other_id)
                if node:
                    reached[other_id] = node
                queue.append((other_id, depth + 1))

    # de-duplicate edges walked from both ends, keeping the shallowest hop
    unique: dict[tuple[str, str, str], TraversalStep] = {}
    for step in result.steps:
        key = (step.source, step.target, step.type)
        if key not in unique or step.hop < unique[key].hop:
            unique[key] = step
    result.steps = sorted(unique.values(), key=lambda step: (step.hop, step.source))

    result.reached = list(reached.values())
    ordered: list[str] = []
    for chunk_id in [step.chunk_id for step in result.steps] + store.chunks_for(seen):
        if chunk_id and chunk_id not in ordered:
            ordered.append(chunk_id)
    result.chunk_ids = ordered
    return result
