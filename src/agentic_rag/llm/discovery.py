"""Ask the configured endpoint which models it actually serves.

Hosted gateways often expose different names than the public APIs do, so
guessing at LLM_MODEL wastes time. This backs `rag models`, which lists
what the endpoint reports and says whether the current LLM_MODEL is on
the list.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from agentic_rag.config import Settings


def _get_json(url: str, headers: dict[str, str], timeout: int) -> dict:
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def list_endpoint_models(settings: Settings) -> tuple[list[str], str]:
    """Return (model names, human-readable source) for the active provider.

    Raises RuntimeError with an actionable message when the endpoint
    cannot be reached or does not offer a listing route.
    """
    provider = (settings.llm_provider or "auto").lower()

    if provider in {"auto", "ollama"}:
        from agentic_rag.llm.ollama import list_models

        tags = list_models(settings.ollama_base_url)
        if tags is None:
            raise RuntimeError(
                f"Ollama is not reachable at {settings.ollama_base_url}. Start it with 'ollama serve'."
            )
        return sorted(tags), f"Ollama at {settings.ollama_base_url}"

    if provider == "anthropic":
        url = f"{settings.anthropic_base_url}/v1/models"
        headers = {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            **settings.llm_extra_headers,
        }
    elif provider in {"openai", "openai_compatible", "deepseek"}:
        # DeepSeek speaks the OpenAI wire format, so it lists models the same way
        base_url, api_key = (
            (settings.deepseek_base_url, settings.deepseek_api_key)
            if provider == "deepseek"
            else (settings.openai_base_url, settings.openai_api_key)
        )
        url = f"{base_url}/models"
        headers = dict(settings.llm_extra_headers)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
    elif provider == "azure":
        raise RuntimeError(
            "Azure deployments are named by you in the portal, so there is nothing to list. "
            "Use the deployment name in AZURE_OPENAI_DEPLOYMENT."
        )
    else:
        raise RuntimeError(f"Listing models is not supported for LLM_PROVIDER={provider}.")

    try:
        payload = _get_json(url, headers, settings.request_timeout)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"{url} returned HTTP {exc.code}: {body}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Could not reach {url}: {exc}") from exc

    entries = payload.get("data", payload.get("models", []))
    names: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            names.append(entry)
        elif isinstance(entry, dict):
            name = entry.get("id") or entry.get("name") or entry.get("model")
            if name:
                names.append(str(name))
    if not names:
        raise RuntimeError(f"{url} answered but listed no models: {str(payload)[:200]}")
    return sorted(names), url


def active_model(settings: Settings) -> str:
    """What LLM_MODEL resolves to for the current provider, empty if auto-picked."""
    provider = (settings.llm_provider or "auto").lower()
    if settings.llm_model:
        return settings.llm_model
    if provider == "anthropic":
        return settings.anthropic_model
    if provider in {"openai", "openai_compatible"}:
        return settings.openai_model
    if provider == "deepseek":
        return settings.deepseek_model
    if provider == "azure":
        return settings.azure_openai_deployment
    return settings.ollama_model
