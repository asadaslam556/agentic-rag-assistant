"""HTTP helpers: SSE line parsing and the streaming failure contract."""

import os

from agentic_rag.core.http import _sse_data, post_sse


def test_sse_data_parses_only_real_data_lines():
    assert _sse_data('data: {"a": 1}') == {"a": 1}
    assert _sse_data("data: [DONE]") is None
    assert _sse_data("event: token") is None
    assert _sse_data("data: not json") is None
    assert _sse_data("data: [1, 2]") is None  # non-dict payloads are skipped


def test_streaming_connection_failure_is_wrapped():
    # keep the request off any configured proxy so the refusal is local and instant
    saved = {k: os.environ.get(k) for k in ("no_proxy", "NO_PROXY")}
    os.environ["no_proxy"] = os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    try:
        list(post_sse("http://127.0.0.1:9", {"x": 1}, timeout=3))
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "Streaming request" in str(exc)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
