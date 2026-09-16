"""Ollama integration with zero-config detection.

Ollama exposes an OpenAI-compatible chat endpoint at /v1, so the client
here is a thin wrapper around that wire format. The interesting part is
resolution: `build_ollama` probes the local server, lists the installed
models, and picks a sensible one automatically, which is what lets
LLM_PROVIDER=auto use a free local model with no configuration at all.
"""

from __future__ import annotations

import json
import sys
import urllib.request

from agentic_rag.config import Settings
from agentic_rag.core.http import post_json, post_sse
from agentic_rag.llm.base import LLMClient, LLMResponse

RECOMMENDED_MODEL = "qwen2.5:7b-instruct"

# Ordered by how reliably they follow the strict-JSON planning protocol.
# Matched by prefix against `ollama list`, so version tags still resolve.
_PREFERRED_MODELS = (
    "qwen2.5:14b",
    "qwen2.5:7b-instruct",
    "qwen2.5:7b",
    "qwen2.5",
    "qwen3:8b",
    "qwen3",
    "llama3.1:8b",
    "llama3.1",
    "llama3:8b",
    "mistral:7b",
    "mistral",
    "phi4",
    "gemma2:9b",
    "gemma3",
    "llama3.2",
)


def list_models(base_url: str, timeout: float = 1.5) -> list[str] | None:
    """Installed model tags, or None when Ollama is not reachable."""
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/api/tags", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return [m.get("name", "") for m in payload.get("models", []) if m.get("name")]
    except Exception:
        return None


def pick_model(available: list[str]) -> str | None:
    for preferred in _PREFERRED_MODELS:
        for tag in available:
            if tag.startswith(preferred):
                return tag
    return available[0] if available else None


class OllamaClient(LLMClient):
    is_mock = False

    def __init__(self, settings: Settings, model: str):
        self.settings = settings
        self.model = model
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.name = f"ollama:{model}"

    def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float | None = 0.1,
        max_tokens: int = 1200,
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        response = post_json(
            f"{self.base_url}/v1/chat/completions",
            payload,
            headers={},
            timeout=self.settings.request_timeout,
        )
        try:
            content = response["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected Ollama response: {str(response)[:300]}") from exc
        return LLMResponse(text=content)

    def complete_stream(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float | None = 0.1,
        max_tokens: int = 1200,
    ):
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "max_tokens": max_tokens,
            "stream": True,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        for event in post_sse(
            f"{self.base_url}/v1/chat/completions",
            payload,
            headers={},
            timeout=self.settings.request_timeout,
        ):
            choices = event.get("choices") or []
            if not choices:
                continue
            piece = (choices[0].get("delta") or {}).get("content")
            if piece:
                yield piece


def build_ollama(settings: Settings) -> OllamaClient | None:
    """A configured client when Ollama is reachable and has a model, else None."""
    tags = list_models(settings.ollama_base_url)
    if tags is None:
        return None
    pinned = settings.llm_model or settings.ollama_model
    if pinned:
        model = pinned
        if tags and model not in tags:
            variable = "LLM_MODEL" if settings.llm_model else "OLLAMA_MODEL"
            print(
                f"note: {variable}={model} is not installed. Pull it with: ollama pull {model}",
                file=sys.stderr,
            )
    else:
        model = pick_model(tags)
        if model is None:
            print(
                "note: Ollama is running but has no models. "
                f"Pull one first: ollama pull {RECOMMENDED_MODEL}",
                file=sys.stderr,
            )
            return None
    return OllamaClient(settings, model)
