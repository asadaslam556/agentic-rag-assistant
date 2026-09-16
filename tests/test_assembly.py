from agentic_rag.assembly.context_assembly import assemble
from agentic_rag.config import Settings
from agentic_rag.core.types import Evidence
from agentic_rag.embeddings.local_hash import HashedTfEmbedder


def _evidence(id_, text, call_id, rank, score=0.5):
    return Evidence(
        id=id_, text=text, source_type="vector", source_ref=f"ref-{id_}",
        title=f"T{id_}", tool_name="vector_search", call_id=call_id, rank=rank, score=score,
    )


def test_duplicates_are_removed_and_relevance_wins():
    embedder = HashedTfEmbedder(dim=256)
    settings = Settings()
    evidence = [
        _evidence("e1", "The Atlas P2 payload capacity is 450 kg.", call_id=1, rank=0),
        _evidence("e2", "Support tickets are answered within one business day.", call_id=1, rank=1),
        _evidence("e3", "the atlas p2 payload   capacity is 450 kg.", call_id=2, rank=0),  # dup
    ]
    packed = assemble("What is the payload capacity?", evidence, embedder, settings)
    assert len(packed) == 2
    assert "payload" in packed[0].text.lower()
    assert packed[0].fused_score >= packed[1].fused_score > 0


def test_packing_respects_the_token_budget():
    embedder = HashedTfEmbedder(dim=128)
    settings = Settings(context_token_budget=60)
    evidence = [
        _evidence(f"e{i}", f"Passage {i}: " + ("robot warehouse throughput " * 12), call_id=1, rank=i)
        for i in range(6)
    ]
    packed = assemble("robot warehouse throughput", evidence, embedder, settings)
    assert 1 <= len(packed) < 6  # the top item always fits, the rest is budget-bound
