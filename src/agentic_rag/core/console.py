"""Tiny dependency-free console helpers (colors degrade gracefully)."""

from __future__ import annotations

import os
import sys


def _colors_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if os.name == "nt" and "WT_SESSION" not in os.environ and "TERM" not in os.environ:
        return False
    return True


_ENABLED = _colors_enabled()

_CODES = {
    "bold": "1",
    "dim": "2",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
}


def paint(text: str, *styles: str) -> str:
    if not _ENABLED or not styles:
        return text
    codes = ";".join(_CODES[s] for s in styles if s in _CODES)
    return f"\033[{codes}m{text}\033[0m"


def rule(label: str = "") -> str:
    width = 72
    if not label:
        return "-" * width
    pad = max(width - len(label) - 4, 0)
    return f"-- {label} " + "-" * pad


def print_kv(key: str, value: str, indent: int = 2) -> None:
    print(" " * indent + paint(f"{key}:", "bold"), value)
