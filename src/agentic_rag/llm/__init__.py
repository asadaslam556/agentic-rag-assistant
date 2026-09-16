from agentic_rag.config import Settings
from agentic_rag.llm.base import LLMClient
from agentic_rag.llm.providers import ProviderError, build_client, known_providers


def get_llm(settings: Settings) -> LLMClient:
    return build_client(settings)


__all__ = ["LLMClient", "ProviderError", "get_llm", "known_providers"]
