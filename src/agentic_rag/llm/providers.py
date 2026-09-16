"""Registry of LLM backends.

Each provider is one builder function tagged with @register("name") and
picked at runtime from LLM_PROVIDER, so adding a backend means adding a
function here and nothing else. Clients are constructed lazily, which
keeps an unused provider's config problems from breaking anyone else.

Setup mistakes (missing key, unreachable host, no model pulled) raise
ProviderError with a message that says what to do about it. Callers
catch that and show it instead of a stack trace.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from agentic_rag.config import Settings
from agentic_rag.llm.base import LLMClient


class ProviderError(RuntimeError):
    """A provider could not be set up, with a message a person can act on."""


_BUILDERS: dict[str, Callable[[Settings], LLMClient]] = {}


def register(name: str) -> Callable[[Callable[[Settings], LLMClient]], Callable[[Settings], LLMClient]]:
    def decorator(builder: Callable[[Settings], LLMClient]) -> Callable[[Settings], LLMClient]:
        _BUILDERS[name] = builder
        return builder

    return decorator


def known_providers() -> list[str]:
    return sorted(_BUILDERS)


def resolve_model(settings: Settings, provider_default: str) -> str:
    """LLM_MODEL wins over the provider-specific setting, which wins over the default.

    One variable covers every provider, which is what you want when you
    switch backends. The per-provider variables still work for anyone who
    keeps several configured at once.
    """
    return settings.llm_model or provider_default


@register("mock")
def _build_mock(settings: Settings) -> LLMClient:
    from agentic_rag.llm.mock import MockLLM

    return MockLLM()


@register("ollama")
def _build_ollama(settings: Settings) -> LLMClient:
    from agentic_rag.llm.ollama import RECOMMENDED_MODEL, build_ollama

    client = build_ollama(settings)
    if client is None:
        raise ProviderError(
            f"LLM_PROVIDER=ollama but Ollama is not reachable at {settings.ollama_base_url}. "
            f"Start it (the desktop app or 'ollama serve') and pull a model: "
            f"ollama pull {RECOMMENDED_MODEL}"
        )
    return client


@register("openai")
def _build_openai(settings: Settings) -> LLMClient:
    from agentic_rag.llm.openai_compat import OpenAICompatClient

    return OpenAICompatClient(settings, azure=False)


@register("openai_compatible")
def _build_openai_compatible(settings: Settings) -> LLMClient:
    from agentic_rag.llm.openai_compat import OpenAICompatClient

    return OpenAICompatClient(settings, azure=False)


@register("azure")
def _build_azure(settings: Settings) -> LLMClient:
    from agentic_rag.llm.openai_compat import OpenAICompatClient

    return OpenAICompatClient(settings, azure=True)


@register("deepseek")
def _build_deepseek(settings: Settings) -> LLMClient:
    from agentic_rag.llm.openai_compat import OpenAICompatClient

    if not settings.deepseek_api_key:
        raise ProviderError(
            "LLM_PROVIDER=deepseek requires DEEPSEEK_API_KEY. Put it in .env "
            "(see .env.example) or export it in your shell."
        )
    # DeepSeek speaks the OpenAI chat format, so the same client covers it
    return OpenAICompatClient(
        settings,
        base_url=settings.deepseek_base_url,
        api_key=settings.deepseek_api_key,
        default_model=settings.deepseek_model,
        label="deepseek",
    )


@register("anthropic")
def _build_anthropic(settings: Settings) -> LLMClient:
    from agentic_rag.llm.anthropic_client import AnthropicClient

    return AnthropicClient(settings)


@register("auto")
def _build_auto(settings: Settings) -> LLMClient:
    """Local Ollama when it is running, the deterministic mock otherwise.

    The fallback is what lets the project run with nothing installed, and
    it is why the test suite and CI never need a model or a network.
    """
    from agentic_rag.llm.ollama import build_ollama

    client = build_ollama(settings)
    if client is not None:
        print(
            f"note: using local Ollama model '{client.model}' "
            "(set LLM_PROVIDER or LLM_MODEL to override)",
            file=sys.stderr,
        )
        return client
    from agentic_rag.llm.mock import MockLLM

    print(
        f"note: Ollama not detected at {settings.ollama_base_url}, "
        "using the deterministic offline mock. Install Ollama for real answers, "
        "or set LLM_PROVIDER explicitly.",
        file=sys.stderr,
    )
    return MockLLM()


def build_client(settings: Settings) -> LLMClient:
    provider = (settings.llm_provider or "auto").lower()
    builder = _BUILDERS.get(provider)
    if builder is None:
        raise ValueError(
            f"Unknown LLM_PROVIDER: {provider!r} (use {', '.join(known_providers())})"
        )
    return builder(settings)
