"""Text utilities shared by chunking, mock synthesis, and verification.

Tokenisation is Unicode-aware. The old rule matched `[a-z0-9]` only,
which quietly destroyed anything outside ASCII: German words lost their
umlauts and split into fragments ("strasse" spelled with an eszett came
out as "stra"), and Arabic, Urdu, and Chinese produced no tokens at all,
so BM25 could never match them.

The rule now keeps letters from any script and adds two steps:

- Chinese and Japanese are written without spaces, so runs of Han and
  kana are indexed as overlapping bigrams. Indexing and querying call the
  same function, so the bigrams line up on both sides.
- Stopwords are chosen by detected language instead of always English.

For pure ASCII text the output is identical to the previous tokeniser,
token for token, which is what keeps English retrieval and the
deterministic mock exactly where they were.
"""

from __future__ import annotations

import re

from agentic_rag.core.lang import (
    CHINESE_STOP_CHARS,
    CJK_CHAR_CLASS,
    ENGLISH_STOPWORDS,
    detect_language,
    is_cjk_char,
    stopwords_for,
)

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")

# Kept under the name other modules already import. It is the English list,
# which is what it has always held.
STOPWORDS = ENGLISH_STOPWORDS

# A token starts with a letter or digit from any script and may carry
# internal hyphens, so "iso-3691-4" stays one token. Underscore is excluded,
# matching the previous behaviour. On ASCII input `[^\W_]` is exactly
# `[a-z0-9]` after lowercasing, which is what preserves English output.
_WORD = re.compile(r"[^\W_](?:[^\W_]|-)*", re.UNICODE)

# Whitespace with a CJK character on either side, which PDF extraction adds.
_CJK_GAP = re.compile(f"(?<=[{CJK_CHAR_CLASS}])\\s+(?=[{CJK_CHAR_CLASS}])")

# Sentence terminators used by the scripts this project supports.
_SENTENCE_ENDERS = "\u3002\uff01\uff1f\u061f\u06d4"


def _cjk_pieces(token: str) -> list[str]:
    """Split a token into non-CJK parts and bigrams of its CJK runs.

    "atlas" glued to Han characters yields "atlas" plus the bigrams of the
    Han run. A run of a single character is kept whole so one-character
    queries still match something.
    """
    pieces: list[str] = []
    buffer: list[str] = []
    run: list[str] = []

    def flush_run() -> None:
        if not run:
            return
        if len(run) == 1:
            pieces.append(run[0])
        else:
            for i in range(len(run) - 1):
                pieces.append(run[i] + run[i + 1])
        run.clear()

    def flush_buffer() -> None:
        if buffer:
            pieces.append("".join(buffer))
            buffer.clear()

    for char in token:
        if is_cjk_char(char):
            flush_buffer()
            run.append(char)
        else:
            flush_run()
            buffer.append(char)
    flush_run()
    flush_buffer()
    return pieces


def _keep(token: str, stopwords: frozenset[str]) -> bool:
    if any(is_cjk_char(char) for char in token):
        # Bigrams are two characters long and would fail the length rule
        # below, so CJK is filtered on its own terms: drop a bigram only
        # when every character in it is a function character.
        return not all(char in CHINESE_STOP_CHARS for char in token)
    return token not in stopwords and len(token) > 1


def _close_cjk_gaps(text: str) -> str:
    """Drop whitespace sitting between two CJK characters.

    PDF text extraction often puts a space between every Han character, so
    a line reads "人 人 生 而 自 由" instead of "人人生而自由". Left alone that
    turns every character into its own token at index time while a typed
    query still produces bigrams, and the two sides never match. Closing
    the gaps first puts both through the same segmentation.

    Only whitespace with a CJK character on both sides is removed, so
    spacing in every other script is untouched.
    """
    if not _CJK_GAP.search(text):
        return text
    return _CJK_GAP.sub("", text)


def _tokens(text: str, language: str | None = None) -> list[str]:
    lowered = _close_cjk_gaps(text.lower())
    stopwords = stopwords_for(language or detect_language(text))
    out: list[str] = []
    for raw in _WORD.findall(lowered):
        pieces = _cjk_pieces(raw) if any(is_cjk_char(char) for char in raw) else (raw,)
        for piece in pieces:
            if _keep(piece, stopwords):
                out.append(piece)
    return out


def _split_non_latin_sentences(text: str) -> list[str]:
    """Split on full stops that the Latin rule above misses.

    The Latin boundary needs a space and a capital letter after the stop,
    which Chinese, Arabic, and Urdu never provide. Splitting on their own
    terminators keeps sentence-level citation and verification working for
    those languages.
    """
    if not any(char in text for char in _SENTENCE_ENDERS):
        return [text]
    parts: list[str] = []
    buffer: list[str] = []
    for char in text:
        buffer.append(char)
        if char in _SENTENCE_ENDERS:
            parts.append("".join(buffer))
            buffer = []
    if buffer:
        parts.append("".join(buffer))
    return parts


def split_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for paragraph in re.split(r"\n{2,}", text):
        flat = re.sub(r"\s+", " ", paragraph).strip()
        if not flat:
            continue
        for sentence in _SENTENCE_BOUNDARY.split(flat):
            for part in _split_non_latin_sentences(sentence):
                part = part.strip()
                if part:
                    sentences.append(part)
    return sentences


def content_tokens(text: str, language: str | None = None) -> set[str]:
    return set(_tokens(text, language))


def tokenize(text: str, language: str | None = None) -> list[str]:
    """Frequency-preserving token list (same rules as content_tokens)."""
    return _tokens(text, language)


def approx_tokens(text: str) -> int:
    """Cheap token estimate (roughly 4 characters per token)."""
    return max(1, len(text) // 4)


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
