"""Provider-agnostic LLM client interface.

Providers are implemented directly over HTTP (no SDK lock-in): any
OpenAI-compatible endpoint, Azure OpenAI, and Anthropic. The mock
client makes the entire pipeline runnable offline and deterministic,
which is what the tests, CI, and the zero-config demo run on.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    text: str


class LLMClient(ABC):
    name: str = "base"
    is_mock: bool = False
    supports_vision: bool = False

    @abstractmethod
    def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float | None = 0.1,
        max_tokens: int = 1200,
    ) -> LLMResponse:
        """messages: [{"role": "user"|"assistant", "content": str}, ...]"""

    def complete_stream(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float | None = 0.1,
        max_tokens: int = 1200,
    ):
        """Yield the response text incrementally. Providers without native
        streaming fall back to a single chunk, so callers can always
        iterate."""
        yield self.complete(
            system, messages, temperature=temperature, max_tokens=max_tokens
        ).text

    def complete_vision(
        self,
        system: str,
        prompt: str,
        images: list[bytes],
        temperature: float | None = 0.0,
        max_tokens: int = 900,
    ) -> LLMResponse:
        """Describe one or more PNG images. Only providers that set
        supports_vision implement this."""
        raise NotImplementedError(f"{self.name} cannot read images")
