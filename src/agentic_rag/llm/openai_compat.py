"""Chat client for OpenAI, Azure OpenAI, and OpenAI-compatible gateways.

One wire format covers the OpenAI API, Azure deployments, local runtimes
like LM Studio and vLLM, and most hosted gateways: set the base URL, the
key, the model, and any extra headers the endpoint needs.
"""

from __future__ import annotations

import base64

from agentic_rag.config import Settings
from agentic_rag.core.http import HttpError, post_json, post_sse
from agentic_rag.llm.base import LLMClient, LLMResponse
from agentic_rag.llm.providers import ProviderError, resolve_model

DEFAULT_MODEL = "gpt-4o-mini"


class OpenAICompatClient(LLMClient):
    supports_vision = True

    def __init__(
        self,
        settings: Settings,
        azure: bool = False,
        base_url: str = "",
        api_key: str = "",
        default_model: str = "",
        label: str = "openai",
    ):
        self.settings = settings
        self.azure = azure
        self.label = label
        # an explicit endpoint wins, which is how sibling providers that speak
        # the same wire format (DeepSeek and friends) reuse this client
        self.override_base_url = base_url
        self.override_api_key = api_key
        if base_url:
            self.model = resolve_model(settings, default_model)
            self.name = f"{label}:{self.model}"
            return
        if azure:
            if not settings.azure_openai_endpoint or not settings.azure_openai_deployment:
                raise ProviderError(
                    "LLM_PROVIDER=azure requires AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT."
                )
            self.model = settings.azure_openai_deployment
            self.name = f"azure:{self.model}"
        else:
            if not settings.openai_api_key and "api.openai.com" in settings.openai_base_url:
                raise ProviderError(
                    "LLM_PROVIDER=openai requires OPENAI_API_KEY. Put it in .env, or point "
                    "OPENAI_BASE_URL at a local endpoint that does not need a key."
                )
            self.model = resolve_model(settings, settings.openai_model or DEFAULT_MODEL)
            self.name = f"openai:{self.model}"

    def _url_and_headers(self) -> tuple[str, dict[str, str]]:
        s = self.settings
        if self.override_base_url:
            headers = dict(s.llm_extra_headers)
            if self.override_api_key:
                headers["Authorization"] = f"Bearer {self.override_api_key}"
            return f"{self.override_base_url}/chat/completions", headers
        if self.azure:
            url = (
                f"{s.azure_openai_endpoint}/openai/deployments/"
                f"{s.azure_openai_deployment}/chat/completions"
                f"?api-version={s.azure_openai_api_version}"
            )
            headers = {"api-key": s.azure_openai_api_key}
        else:
            url = f"{s.openai_base_url}/chat/completions"
            headers = {"Authorization": f"Bearer {s.openai_api_key}"} if s.openai_api_key else {}
        headers.update(s.llm_extra_headers)
        return url, headers

    def _payload(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float | None,
        max_tokens: int,
    ) -> dict:
        payload: dict = {
            "messages": [{"role": "system", "content": system}, *messages],
            "max_tokens": max_tokens,
        }
        # Blank LLM_TEMPERATURE leaves the field out for models that reject
        # it. Checked here rather than at the call sites because the fixed
        # 0.0 roles would otherwise put it back.
        if temperature is not None and not self.settings.omit_temperature:
            payload["temperature"] = temperature
        if not self.azure:
            payload["model"] = self.model
        return payload

    def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float | None = 0.1,
        max_tokens: int = 1200,
    ) -> LLMResponse:
        url, headers = self._url_and_headers()
        try:
            response = post_json(
                url,
                self._payload(system, messages, temperature, max_tokens),
                headers=headers,
                timeout=self.settings.request_timeout,
            )
        except HttpError as exc:
            raise _friendly(exc, self.model) from exc
        try:
            content = response["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected chat completion response: {str(response)[:300]}") from exc
        return LLMResponse(text=content)

    def complete_stream(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float | None = 0.1,
        max_tokens: int = 1200,
    ):
        url, headers = self._url_and_headers()
        payload = self._payload(system, messages, temperature, max_tokens)
        payload["stream"] = True
        try:
            for event in post_sse(url, payload, headers=headers, timeout=self.settings.request_timeout):
                choices = event.get("choices") or []
                if not choices:
                    continue
                piece = (choices[0].get("delta") or {}).get("content")
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
        content: list[dict] = [{"type": "text", "text": prompt}]
        for image in images:
            encoded = base64.b64encode(image).decode("ascii")
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}}
            )
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
            f"The endpoint rejected the credentials (HTTP {status}). Check OPENAI_API_KEY "
            "(or the Azure key) and the base URL."
        )
    if status == 404:
        return ProviderError(
            f"The endpoint returned 404 for model {model!r}. Run `rag models` to see what it "
            "serves, then set LLM_MODEL to one of those names."
        )
    if status == 400 and "temperature" in str(exc).lower():
        return ProviderError(
            f"This model rejects the temperature parameter ({model!r}). Set LLM_TEMPERATURE= "
            "(blank) in .env to leave it out of the request."
        )
    if status == 429:
        return ProviderError("Rate limit reached (HTTP 429). Wait a moment and retry.")
    return exc
