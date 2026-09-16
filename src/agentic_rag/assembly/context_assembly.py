"""Context assembly: merge, deduplicate, rank, and pack evidence.

Evidence arrives from several tool calls with incomparable scores
(cosine similarities, web ranks, structured match counts). Assembly
makes them comparable:

1. Deduplicate by normalized text hash (keeping the best raw score).
2. Reciprocal rank fusion across the ranked list of each tool call:
   rrf(e) = sum over calls of 1 / (60 + rank_in_call).
3. Semantic similarity between the question and each evidence text,
   using the same embedder as retrieval, mapped to [0, 1].
4. Fused score = 0.6 * semantic + 0.4 * normalized RRF.
5. Greedy packing into the context token budget (top item always fits).

The packed order defines the citation numbering [1..n] used by
synthesis and verification.
"""

from __future__ import annotations

import hashlib

from agentic_rag.config import Settings
from agentic_rag.core.textutils import approx_tokens, normalize_ws
from agentic_rag.core.types import Evidence
from agentic_rag.embeddings.base import Embedder

_MAX_SOURCES = 12
_RRF_K = 60


def assemble(
    question: str,
    evidence: list[Evidence],
    embedder: Embedder,
    settings: Settings,
) -> list[Evidence]:
    if not evidence:
        return []

    # 1. deduplicate
    unique: list[Evidence] = []
    by_hash: dict[str, Evidence] = {}
    for item in evidence:
        key = hashlib.md5(normalize_ws(item.text).lower().encode("utf-8")).hexdigest()
        existing = by_hash.get(key)
        if existing is not None:
            existing.score = max(existing.score, item.score)
            continue
        by_hash[key] = item
        unique.append(item)

    # 2. reciprocal rank fusion across tool calls
    rrf: dict[str, float] = {item.id: 0.0 for item in unique}
    calls: dict[int, list[Evidence]] = {}
    for item in unique:
        calls.setdefault(item.call_id, []).append(item)
    for members in calls.values():
        members.sort(key=lambda entry: entry.rank)
        for position, item in enumerate(members):
            rrf[item.id] += 1.0 / (_RRF_K + position)
    max_rrf = max(rrf.values())

    # 3. semantic similarity to the question
    matrix = embedder.embed_texts([item.text for item in unique])
    query_vector = embedder.embed_query(question)
    similarities = matrix @ query_vector

    # 4. fuse
    for item, similarity in zip(unique, similarities, strict=True):
        semantic = (float(similarity) + 1.0) / 2.0
        item.fused_score = round(0.6 * semantic + 0.4 * (rrf[item.id] / max_rrf), 4)
    unique.sort(key=lambda entry: -entry.fused_score)

    # 5. pack into the token budget
    packed: list[Evidence] = []
    used_tokens = 0
    for item in unique:
        cost = approx_tokens(item.text)
        if packed and used_tokens + cost > settings.context_token_budget:
            continue  # greedy: skip oversized items, smaller relevant ones may still fit
        packed.append(item)
        used_tokens += cost
        if len(packed) >= _MAX_SOURCES:
            break
    return packed
