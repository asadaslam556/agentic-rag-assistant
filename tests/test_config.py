"""Env parsing: bad numeric values fail loudly, empties fall back."""

import os

from agentic_rag.config import _env_float, _env_int


def test_bad_integer_env_names_the_variable():
    os.environ["RAG_TEST_INT"] = "definitely-not-a-number"
    try:
        _env_int("RAG_TEST_INT", 5)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "RAG_TEST_INT" in str(exc)
        assert "definitely-not-a-number" in str(exc)
    finally:
        del os.environ["RAG_TEST_INT"]


def test_bad_float_env_names_the_variable():
    os.environ["RAG_TEST_FLOAT"] = "warm-ish"
    try:
        _env_float("RAG_TEST_FLOAT", 0.1)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "RAG_TEST_FLOAT" in str(exc)
    finally:
        del os.environ["RAG_TEST_FLOAT"]


def test_empty_and_valid_values_behave_normally():
    os.environ.pop("RAG_TEST_INT", None)
    assert _env_int("RAG_TEST_INT", 7) == 7
    os.environ["RAG_TEST_INT"] = "42"
    try:
        assert _env_int("RAG_TEST_INT", 7) == 42
    finally:
        del os.environ["RAG_TEST_INT"]
