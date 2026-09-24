"""Indirect prompt injection: instructions hidden in retrieved text.

A web page or an uploaded document can carry text aimed at the model rather
than the reader: "ignore previous instructions and ...". Every prompt that
shows sources already says they are data, not instructions. This is the
second layer: sentences that look like such instructions are cut before any
model sees them, and a visible marker takes their place, so whoever reads
the sources panel can tell something was removed.

The patterns are narrow on purpose. A false positive silently deletes a real
sentence from the evidence, which is worse than letting a clumsy injection
through to a model that has been told to ignore it. Text with no match is
returned unchanged, character for character.
"""

from __future__ import annotations

import re

REMOVED = "[removed: text addressed to the assistant rather than the reader]"

# Fake role markup is cut as a span, since it rarely ends in punctuation and
# would otherwise take the neighbouring real sentence with it.
_ROLE_TAG = re.compile(
    r"<\s*(system|assistant|instructions?)\s*>[^<]{0,500}(?:<\s*/\s*\1\s*>)?"
    r"|<\s*/\s*(?:system|assistant|instructions?)\s*>",
    re.IGNORECASE,
)
# Looser than the shared splitter on purpose: an injected sentence may start
# in lower case or with a symbol, and must not be glued to the real sentence
# before it. Only used on text that already matched a pattern.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_GAP = r"[^.!?\n]{0,40}"
_PATTERNS = re.compile(
    "|".join(
        [
            # ignore / disregard ... previous ... instructions
            rf"\b(?:ignore|disregard|forget|override){_GAP}\b(?:previous|prior|above|earlier|all|any|your)"
            rf"\b{_GAP}\b(?:instructions?|prompts?|rules|directions|guidelines)\b",
            r"\b(?:reveal|print|repeat|show)\s+(?:your|the)\s+(?:system\s+)?(?:prompt|instructions)\b",
            r"\b(?:system|developer)\s+prompt\b",
            r"\bnew\s+instructions?\s*:",
            r"\bdo\s+not\s+(?:tell|inform)\s+the\s+user\b",
            # German: ignoriere / vergiss ... Anweisungen
            rf"\b(?:ignoriere|ignorieren|vergiss|vergessen){_GAP}\b(?:anweisungen|instruktionen|regeln)\b",
        ]
    ),
    re.IGNORECASE,
)


def strip_injections(text: str) -> tuple[str, int]:
    """Text with instruction-like sentences replaced by a marker, and how many."""
    text, removed = _ROLE_TAG.subn(REMOVED, text)
    if not _PATTERNS.search(text):
        return text, removed
    kept: list[str] = []
    for sentence in _SENTENCE_END.split(text.strip()):
        if _PATTERNS.search(sentence):
            removed += 1
            if not kept or kept[-1] != REMOVED:
                kept.append(REMOVED)
        else:
            kept.append(sentence)
    return " ".join(kept), removed
