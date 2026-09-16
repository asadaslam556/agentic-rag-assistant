"""Minimal HTTP JSON client with retries.

Uses httpx when installed; falls back to the standard library so the
core package has no hard HTTP dependency. Retries transient failures
(429 and 5xx) with exponential backoff.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

RETRYABLE = {429, 500, 502, 503, 504}


class HttpError(RuntimeError):
    def __init__(self, status: int, body: str, url: str):
        super().__init__(f"HTTP {status} from {url}: {body[:400]}")
        self.status = status
        self.body = body


def post_json(
    url: str,
    payload: dict,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
    retries: int = 3,
) -> dict:
    headers = {"Content-Type": "application/json", **(headers or {})}
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return _post_once(url, payload, headers, timeout)
        except HttpError as exc:
            last_error = exc
            if exc.status not in RETRYABLE or attempt == retries:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            last_error = exc
            if attempt == retries:
                raise RuntimeError(f"Request to {url} failed: {exc}") from exc
        time.sleep(1.5 ** attempt)
    raise RuntimeError(f"Request to {url} failed: {last_error}")


def _post_once(url: str, payload: dict, headers: dict[str, str], timeout: int) -> dict:
    try:
        import httpx  # optional

        response = httpx.post(url, json=payload, headers=headers, timeout=timeout)
        if response.status_code >= 400:
            raise HttpError(response.status_code, response.text, url)
        return response.json()
    except ImportError:
        pass

    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as raw:
            return json.loads(raw.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise HttpError(exc.code, body, url) from exc


def _sse_data(line: str) -> dict | None:
    line = line.strip()
    if not line.startswith("data:"):
        return None
    chunk = line[5:].strip()
    if not chunk or chunk == "[DONE]":
        return None
    try:
        parsed = json.loads(chunk)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def post_sse(
    url: str,
    payload: dict,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
):
    """POST and yield the parsed JSON objects from an SSE response.

    Used for token streaming from OpenAI-compatible endpoints such as
    Ollama. httpx when installed, standard library otherwise. Connection
    failures come back as RuntimeError with the URL in the message, same
    contract as post_json.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        **(headers or {}),
    }
    try:
        import httpx  # optional
    except ImportError:
        httpx = None

    if httpx is not None:
        try:
            with httpx.stream("POST", url, json=payload, headers=headers, timeout=timeout) as response:
                if response.status_code >= 400:
                    body = response.read().decode("utf-8", errors="replace")
                    raise HttpError(response.status_code, body, url)
                for line in response.iter_lines():
                    data = _sse_data(line)
                    if data is not None:
                        yield data
            return
        except HttpError:
            raise
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Streaming request to {url} failed: {exc}") from exc

    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as raw:
            for raw_line in raw:
                data = _sse_data(raw_line.decode("utf-8", errors="replace"))
                if data is not None:
                    yield data
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise HttpError(exc.code, body, url) from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        raise RuntimeError(f"Streaming request to {url} failed: {exc}") from exc
