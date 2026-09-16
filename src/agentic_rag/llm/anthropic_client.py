"""Claude client, talking to the Messages API over plain HTTP.

Works against the public API and against any compatible endpoint you
point ANTHROPIC_BASE_URL at. Model names sometimes differ between the
two (an endpoint may serve claude-sonnet-4-6@default where the public
API calls it claude-sonnet-4-6), so whatever is in LLM_MODEL is sent
through untouched. `rag models` asks the endpoint what it serves.
"""

from __future__ import annotations

import base64

from agentic_rag.config import Settings
from agentic_rag.core.http import HttpError, post_json, post_sse
from agentic_rag.llm.base import LLMClient, LLMResponse
from agentic_rag.llm.providers import ProviderError, resolve_model

DEFAULT_MODEL = "claude-sonnet-4-6"


class AnthropicClient(LLMClient):
    supports_vision = True

    def __init__(self, settings: Settings):
        if not settings.anthropic_api_key:
            raise ProviderError(
                "LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY. Put it in .env "
                "(see .env.example) or export it in your shell."
            )
        self.settings = settings
        self.model = resolve_model(settings, settings.anthropic_model or DEFAULT_MODEL)
        self.name = f"anthropic:{self.model}"

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            **self.settings.llm_extra_headers,
        }

    def _payload(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float | None,
        max_tokens: int,
    ) -> dict:
        payload: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        # Blank LLM_TEMPERATURE leaves the field out for models that reject
        # it. Checked here rather than at the call sites because the fixed
        # 0.0 roles would otherwise put it back.
        if temperature is not None and not self.settings.omit_temperature:
            payload["temperature"] = temperature
        return payload

    def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float | None = 0.1,
        max_tokens: int = 1200,
    ) -> LLMResponse:
        url = f"{self.settings.anthropic_base_url}/v1/messages"
        try:
            response = post_json(
                url,
                self._payload(system, messages, temperature, max_tokens),
                headers=self._headers(),
                timeout=self.settings.request_timeout,
            )
        except HttpError as exc:
            raise _friendly(exc, self.model) from exc
        blocks = response.get("content", [])
        text = "".join(block.get("text", "") for block in blocks if block.get("type") == "text")
        if not text:
            # Models with extended thinking on spend the token budget thinking
            # first. If the budget runs out before any text block, the reply is
            # all reasoning and no answer, which is a limit problem rather than
            # a malformed response.
            thinking = any(
                block.get("type") in ("thinking", "redacted_thinking") for block in blocks
            )
            if thinking or response.get("stop_reason") == "max_tokens":
                raise ProviderError(
                    f"{self.model!r} used its whole {max_tokens} token budget on extended "
                    "thinking and returned no text. Raise max_tokens for this call, or turn "
                    "thinking off on the endpoint."
                )
            raise RuntimeError(f"Unexpected Anthropic response: {str(response)[:300]}")
        return LLMResponse(text=text)

    def complete_stream(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float | None = 0.1,
        max_tokens: int = 1200,
    ):
        payload = self._payload(system, messages, temperature, max_tokens)
        payload["stream"] = True
        url = f"{self.settings.anthropic_base_url}/v1/messages"
        try:
            for event in post_sse(
                url, payload, headers=self._headers(), timeout=self.settings.request_timeout
            ):
                # text arrives as content_block_delta events; everything else is bookkeeping
                if event.get("type") != "content_block_delta":
                    continue
                piece = (event.get("delta") or {}).get("text")
                if piece:
                    yield piece
        except HttpError as exc:
            raise _friendly(exc, self.model) from exc


    def complete_vision(
        self,
        system: str,
        prompt: str,
        images: list[bytes],
        temperature: float | None = 0.0,
        max_tokens: int = 900,
    ) -> LLMResponse:
        content: list[dict] = []
        for image in images:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.b64encode(image).decode("ascii"),
                    },
                }
            )
        content.append({"type": "text", "text": prompt})
        return self.complete(
            system,
            [{"role": "user", "content": content}],
            temperature=temperature,
            max_tokens=max_tokens,
        )


def _friendly(exc: HttpError, model: str) -> Exception:
    status = getattr(exc, "status", None)
    if status in (401, 403):
        return ProviderError(
            "Claude rejected the credentials (HTTP "
            f"{status}). Check ANTHROPIC_API_KEY, and ANTHROPIC_BASE_URL if you "
            "are using a private endpoint."
        )
    if status == 404:
        return ProviderError(
            f"Claude endpoint returned 404 for model {model!r}. Run `rag models` to see "
            "what this endpoint actually serves, then set LLM_MODEL to one of those names."
        )
    if status == 400 and "temperature" in str(exc).lower():
        return ProviderError(
            f"This model rejects the temperature parameter ({model!r}). Set "
            "LLM_TEMPERATURE= (blank) in .env to leave it out of the request."
        )
    if status == 429:
        return ProviderError("Claude rate limit reached (HTTP 429). Wait a moment and retry.")
    return exc
