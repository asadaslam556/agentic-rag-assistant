"""Provider registry, model resolution, and the request payloads we send."""

import pytest

from agentic_rag.config import Settings
from agentic_rag.llm import get_llm, known_providers
from agentic_rag.llm.anthropic_client import AnthropicClient
from agentic_rag.llm.openai_compat import OpenAICompatClient
from agentic_rag.llm.providers import ProviderError, resolve_model


def test_every_supported_provider_is_registered():
    names = known_providers()
    for expected in ("auto", "mock", "ollama", "openai", "azure", "anthropic", "openai_compatible"):
        assert expected in names


def test_llm_model_beats_the_provider_specific_setting():
    assert resolve_model(Settings(llm_model="claude-sonnet-4-6@default"), "claude-sonnet-4-6") == (
        "claude-sonnet-4-6@default"
    )
    assert resolve_model(Settings(), "gpt-4o-mini") == "gpt-4o-mini"


def test_unknown_provider_lists_the_valid_names():
    with pytest.raises(ValueError) as caught:
        get_llm(Settings(llm_provider="banana"))
    assert "anthropic" in str(caught.value)


def test_anthropic_without_a_key_says_what_to_do():
    with pytest.raises(ProviderError) as caught:
        get_llm(Settings(llm_provider="anthropic"))
    assert "ANTHROPIC_API_KEY" in str(caught.value)


def test_anthropic_sends_the_model_name_untouched():
    # gateways serve names the public API does not, so nothing may rewrite them
    settings = Settings(
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6@default",
        anthropic_api_key="key",
        anthropic_base_url="https://example.invalid/gateway",
    )
    client = AnthropicClient(settings)
    assert client.name == "anthropic:claude-sonnet-4-6@default"
    payload = client._payload("sys", [{"role": "user", "content": "hi"}], 0.1, 500)
    assert payload["model"] == "claude-sonnet-4-6@default"
    assert payload["temperature"] == 0.1
    assert payload["system"] == "sys"


def test_blank_temperature_is_left_out_of_every_request():
    anthropic = AnthropicClient(Settings(anthropic_api_key="key"))
    assert "temperature" not in anthropic._payload("s", [], None, 100)
    openai = OpenAICompatClient(Settings(openai_api_key="key"))
    assert "temperature" not in openai._payload("s", [], None, 100)


def test_openai_payload_carries_model_and_system_message():
    client = OpenAICompatClient(Settings(openai_api_key="key", llm_model="gpt-4o"))
    payload = client._payload("sys", [{"role": "user", "content": "hi"}], 0.1, 100)
    assert payload["model"] == "gpt-4o"
    assert payload["messages"][0] == {"role": "system", "content": "sys"}


def test_azure_needs_endpoint_and_deployment():
    with pytest.raises(ProviderError) as caught:
        get_llm(Settings(llm_provider="azure"))
    assert "AZURE_OPENAI_ENDPOINT" in str(caught.value)


def test_anthropic_streaming_reads_content_block_deltas(monkeypatch=None):
    import agentic_rag.llm.anthropic_client as module

    events = [
        {"type": "message_start", "message": {}},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "The payload "}},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "is 450 kg."}},
        {"type": "message_stop"},
    ]
    original = module.post_sse
    module.post_sse = lambda *args, **kwargs: iter(events)
    try:
        client = AnthropicClient(Settings(anthropic_api_key="key"))
        assert "".join(client.complete_stream("s", [{"role": "user", "content": "q"}])) == (
            "The payload is 450 kg."
        )
    finally:
        module.post_sse = original


def test_openai_streaming_reads_choice_deltas():
    import agentic_rag.llm.openai_compat as module

    events = [
        {"choices": [{"delta": {"role": "assistant"}}]},
        {"choices": [{"delta": {"content": "450"}}]},
        {"choices": [{"delta": {"content": " kg"}}]},
        {"choices": []},
    ]
    original = module.post_sse
    module.post_sse = lambda *args, **kwargs: iter(events)
    try:
        client = OpenAICompatClient(Settings(openai_api_key="key"))
        assert "".join(client.complete_stream("s", [{"role": "user", "content": "q"}])) == "450 kg"
    finally:
        module.post_sse = original


def test_http_errors_become_advice():
    from agentic_rag.core.http import HttpError
    from agentic_rag.llm.anthropic_client import _friendly

    assert "ANTHROPIC_API_KEY" in str(_friendly(HttpError(401, "no", "u"), "m"))
    assert "rag models" in str(_friendly(HttpError(404, "nope", "u"), "m"))
    assert "LLM_TEMPERATURE=" in str(_friendly(HttpError(400, "temperature is deprecated", "u"), "m"))
    assert isinstance(_friendly(HttpError(500, "boom", "u"), "m"), HttpError)


def test_deepseek_without_a_key_says_what_to_do():
    with pytest.raises(ProviderError) as caught:
        get_llm(Settings(llm_provider="deepseek"))
    assert "DEEPSEEK_API_KEY" in str(caught.value)


def test_deepseek_defaults_to_its_own_endpoint_and_model():
    settings = Settings()
    assert settings.deepseek_base_url == "https://api.deepseek.com"
    assert settings.deepseek_model == "deepseek-flash"


def test_rag_models_lists_deepseek_from_its_own_endpoint(monkeypatch):
    from agentic_rag.llm import discovery

    seen = {}

    def fake_get_json(url, headers, timeout):
        seen["url"], seen["auth"] = url, headers.get("Authorization")
        return {"data": [{"id": "deepseek-v4-pro"}, {"id": "deepseek-flash"}]}

    monkeypatch.setattr(discovery, "_get_json", fake_get_json)
    settings = Settings(llm_provider="deepseek", deepseek_api_key="sk-test")
    names, source = discovery.list_endpoint_models(settings)
    assert names == ["deepseek-flash", "deepseek-v4-pro"]
    assert seen == {"url": "https://api.deepseek.com/models", "auth": "Bearer sk-test"}
    assert discovery.active_model(settings) == "deepseek-flash"


def test_provider_settings_round_trip_through_the_environment(monkeypatch):
    """Keys and endpoints come from the environment, never from code."""
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    # a trailing slash would double up once request paths are appended
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://gateway.example/v1/")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-5@default")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-key")
    settings = Settings.from_env()
    assert settings.llm_provider == "anthropic"
    assert settings.anthropic_api_key == "test-key"
    assert settings.anthropic_base_url == "https://gateway.example/v1"
    assert settings.anthropic_model == "claude-sonnet-5@default"
    assert settings.deepseek_api_key == "ds-key"


def test_the_default_provider_still_needs_no_key_or_network():
    assert Settings().llm_provider == "auto"
    assert Settings().anthropic_api_key == ""
    assert Settings().deepseek_api_key == ""


def test_blank_temperature_is_omitted_even_by_the_fixed_zero_roles():
    """Verifying, judging, splitting, and rewriting ask for a fixed 0.0.

    A model that rejects the temperature parameter rejects 0.0 as well, so
    a blank LLM_TEMPERATURE has to win over those call sites. It used to
    lose, and the request died in the verifier with HTTP 400 after planning
    had already succeeded.
    """
    settings = Settings(llm_provider="anthropic", anthropic_api_key="k", llm_temperature=None)
    client = get_llm(settings)
    messages = [{"role": "user", "content": "hi"}]
    for requested in (None, 0.0, 0.1, 1.0):
        payload = client._payload("system", messages, requested, 100)
        assert "temperature" not in payload, requested


def test_a_configured_temperature_is_still_sent():
    settings = Settings(llm_provider="anthropic", anthropic_api_key="k", llm_temperature=0.2)
    client = get_llm(settings)
    messages = [{"role": "user", "content": "hi"}]
    assert client._payload("s", messages, 0.2, 100)["temperature"] == 0.2
    # the deterministic roles keep their own 0.0 when temperature is allowed
    assert client._payload("s", messages, 0.0, 100)["temperature"] == 0.0


def test_blank_temperature_is_omitted_on_openai_compatible_endpoints():
    settings = Settings(llm_provider="deepseek", deepseek_api_key="k", llm_temperature=None)
    payload = get_llm(settings)._payload("s", [{"role": "user", "content": "hi"}], 0.0, 100)
    assert "temperature" not in payload


def test_omit_temperature_reflects_the_setting():
    assert Settings(llm_temperature=None).omit_temperature is True
    assert Settings(llm_temperature=0.0).omit_temperature is False
    assert Settings(llm_temperature=0.7).omit_temperature is False
