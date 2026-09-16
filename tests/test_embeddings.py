import numpy as np

from agentic_rag.embeddings.local_hash import HashedTfEmbedder


def test_embeddings_are_deterministic_and_normalized():
    embedder = HashedTfEmbedder(dim=256)
    first = embedder.embed_texts(["the atlas robot carries pallets"])
    second = embedder.embed_texts(["the atlas robot carries pallets"])
    assert np.allclose(first, second)
    assert abs(float(np.linalg.norm(first[0])) - 1.0) < 1e-5


def test_similarity_prefers_topically_related_text():
    embedder = HashedTfEmbedder(dim=512)
    query = embedder.embed_query("payload capacity of the robot")
    payload_text, pricing_text = embedder.embed_texts(
        [
            "The robot has a payload capacity of 450 kg on its load deck.",
            "The subscription plan costs 649 EUR per month billed annually.",
        ]
    )
    assert float(payload_text @ query) > float(pricing_text @ query)
