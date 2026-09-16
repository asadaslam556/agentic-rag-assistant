from agentic_rag.config import Settings
from agentic_rag.embeddings.base import Embedder


def get_embedder(settings: Settings) -> Embedder:
    provider = settings.embeddings_provider
    if provider == "local":
        from agentic_rag.embeddings.local_hash import HashedTfEmbedder

        return HashedTfEmbedder(dim=settings.local_embedding_dim)
    if provider == "sbert":
        from agentic_rag.embeddings.sbert import SbertEmbedder

        return SbertEmbedder(settings.sbert_model)
    if provider == "multilingual":
        from agentic_rag.embeddings.multilingual import MultilingualEmbedder

        return MultilingualEmbedder(settings.multilingual_embedding_model)
    if provider == "openai":
        from agentic_rag.embeddings.openai_embed import OpenAIEmbedder

        return OpenAIEmbedder(settings)
    raise ValueError(
        f"Unknown EMBEDDINGS_PROVIDER: {provider!r} "
        "(use local, sbert, multilingual, or openai)"
    )


__all__ = ["Embedder", "get_embedder"]
