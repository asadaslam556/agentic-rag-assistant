"""Ollama detection and the auto provider fallback, fully offline.

An unreachable base URL (a closed local port) exercises the same code
path as a machine without Ollama, so these tests never touch the
network in any meaningful way and fail fast.
"""

import pytest

from agentic_rag.config import Settings
from agentic_rag.llm import get_llm
from agentic_rag.llm.ollama import build_ollama, list_models, pick_model

UNREACHABLE = "http://127.0.0.1:9"  # discard port, connection refused instantly


def test_list_models_returns_none_when_unreachable():
    assert list_models(UNREACHABLE, timeout=0.5) is None


def test_pick_model_prefers_json_reliable_models():
    assert pick_model(["llama3.1:8b", "qwen2.5:7b-instruct"]) == "qwen2.5:7b-instruct"
    assert pick_model(["mystery-model:latest"]) == "mystery-model:latest"
    assert pick_model([]) is None


def test_build_ollama_is_none_without_server():
    settings = Settings(llm_provider="ollama", ollama_base_url=UNREACHABLE)
    assert build_ollama(settings) is None


def test_auto_provider_falls_back_to_mock():
    settings = Settings(llm_provider="auto", ollama_base_url=UNREACHABLE)
    client = get_llm(settings)
    assert client.is_mock


def test_explicit_ollama_without_server_raises_actionable_error():
    settings = Settings(llm_provider="ollama", ollama_base_url=UNREACHABLE)
    with pytest.raises(RuntimeError):
        get_llm(settings)


def test_openai_provider_without_a_key_fails_at_construction():
    from agentic_rag.llm import get_llm

    settings = Settings(llm_provider="openai", openai_api_key="")
    try:
        get_llm(settings)
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "OPENAI_API_KEY" in str(exc)
