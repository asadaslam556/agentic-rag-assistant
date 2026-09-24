"""Agentic RAG Knowledge Assistant.

An agent orchestrator plans tool calls (vector search, web search,
structured data APIs), assembles the retrieved evidence into a ranked
context, drafts an answer with numbered citations, and then verifies
every claim against the evidence before returning it.
"""

__version__ = "3.14.0"

from agentic_rag.pipeline import AgenticRAG  # noqa: E402

__all__ = ["AgenticRAG", "__version__"]
