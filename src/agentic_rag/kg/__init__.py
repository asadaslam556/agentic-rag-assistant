"""Knowledge graph: extraction, storage, and traversal.

Separate from `agentic_rag.graph`, which is the orchestration graph that
decomposes a question and merges branches. This package is about entities
and the relationships between them.
"""

from agentic_rag.kg.schema import EDGE_TYPES, ENTITY_TYPES, ChunkGraph, Entity, Relation
from agentic_rag.kg.store import get_graph_store
from agentic_rag.kg.traverse import Traversal, traverse

__all__ = [
    "EDGE_TYPES",
    "ENTITY_TYPES",
    "ChunkGraph",
    "Entity",
    "Relation",
    "Traversal",
    "get_graph_store",
    "traverse",
]
