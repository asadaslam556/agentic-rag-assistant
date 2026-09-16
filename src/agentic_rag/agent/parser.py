"""Pulling the first JSON object out of whatever the model said.

Handles code fences, leading or trailing prose, and nested braces
inside strings. The agent loop retries with corrective feedback when
parsing fails, so this raises a typed error instead of guessing.
"""

from __future__ import annotations

import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


class ParserError(ValueError):
    pass


def _scan_balanced(text: str) -> dict | None:
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(text)):
            char = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    blob = text[start : i + 1]
                    try:
                        parsed = json.loads(blob)
                    except json.JSONDecodeError:
                        break  # malformed; try the next opening brace
                    if isinstance(parsed, dict):
                        return parsed
                    break
        start = text.find("{", start + 1)
    return None


def extract_first_json(text: str) -> dict:
    candidates = []
    fenced = _FENCE.search(text)
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(text)
    for candidate in candidates:
        parsed = _scan_balanced(candidate)
        if parsed is not None:
            return parsed
    raise ParserError(f"No JSON object found in model output: {text[:200]!r}")
