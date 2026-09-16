"""Language detection and per-language stopwords, stdlib only.

Script first, from Unicode ranges. Where that is not enough, stopword
hits break the tie: Arabic script covers both Arabic and Urdu, so Urdu
is spotted by the letters it added to the alphabet (ٹ ڈ ڑ ں ھ ے گ چ پ),
and Latin covers English and German, separated by function words with a
nudge from umlauts.

Thin evidence falls back to English, which is what short queries like
"Atlas P2" get.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_LANGUAGE = "en"

# Languages this project ships stopwords and detection rules for.
SUPPORTED_LANGUAGES = ("en", "de", "ar", "zh", "ur")

LANGUAGE_NAMES = {
    "en": "English",
    "de": "German",
    "ar": "Arabic",
    "zh": "Chinese",
    "ur": "Urdu",
}

# --------------------------------------------------------------- script ranges

# Han ideographs plus kana. These scripts are written without spaces, so the
# tokenizer has to segment them instead of splitting on whitespace.
_CJK_RANGES = (
    (0x3040, 0x30FF),  # hiragana and katakana
    (0x3400, 0x4DBF),  # CJK unified ideographs extension A
    (0x4E00, 0x9FFF),  # CJK unified ideographs
    (0xF900, 0xFAFF),  # CJK compatibility ideographs
)

_ARABIC_RANGES = (
    (0x0600, 0x06FF),  # Arabic
    (0x0750, 0x077F),  # Arabic supplement
    (0x08A0, 0x08FF),  # Arabic extended-A
    (0xFB50, 0xFDFF),  # Arabic presentation forms-A
    (0xFE70, 0xFEFF),  # Arabic presentation forms-B
)

# Letters Urdu added to the Arabic alphabet. Arabic text does not use them,
# so a single one of these is a strong Urdu signal.
_URDU_ONLY_CHARS = frozenset("ٹڈڑںھےہگچپژکی")

# German letters outside the plain ASCII range.
_GERMAN_CHARS = frozenset("äöüßÄÖÜ")


def _in_ranges(code_point: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(low <= code_point <= high for low, high in ranges)


def is_cjk_char(char: str) -> bool:
    """True for Han and kana, the characters that need segmenting."""
    return _in_ranges(ord(char), _CJK_RANGES)


# The same ranges as a regex character class body, for callers that need to
# match CJK inside a pattern rather than one character at a time.
CJK_CHAR_CLASS = "".join(f"{chr(low)}-{chr(high)}" for low, high in _CJK_RANGES)


def is_arabic_char(char: str) -> bool:
    return _in_ranges(ord(char), _ARABIC_RANGES)


# ------------------------------------------------------------------ stopwords

# The English list is the one this project has always used. It stays exactly
# as it was so English tokenisation does not shift by a single token.
ENGLISH_STOPWORDS = frozenset(
    """
    a an and are as at be but by can could did do does for from had has have how
    i if in into is it its me my not of on or our per should so than that the
    their there these they this to us was we were what when where which who why
    will with would you your about
    """.split()
)

GERMAN_STOPWORDS = frozenset(
    """
    aber alle als also am an auch auf aus bei beim bin bis bist da damit dann
    das dass dem den denn der des dessen die dies diese diesem diesen dieser
    dieses doch dort du durch ein eine einem einen einer eines er es etwas
    euer eure fuer für gegen gewesen hab habe haben hat hatte hatten hier hin
    ihr ihre ihrem ihren ihrer ihres im in ist ja jede jedem jeden jeder jedes
    jene kann kannst koennen können machen man mehr mein meine mit muss müssen
    nach nicht noch nun nur ob oder ohne schon sehr sein seine seinem seinen
    seiner sich sie sind so soll sollen ueber über um und uns unser unsere vom
    von vor waehrend war waren warum was weil weiter welche wenn wer werden
    wie wieder wir wird wirst wo wurde wurden zu zum zur zwar zwischen
    """.split()
)

ARABIC_STOPWORDS = frozenset(
    """
    في من على إلى عن مع هذا هذه هذان ذلك تلك التي الذي الذين ما ماذا لا لم لن
    ان أن إن أو او ثم حتى إذا اذا كما بين هناك هنا هو هي هم هن نحن أنا انا أنت
    انت كان كانت يكون تكون قد كل بعض عند عندما لكن لكي كي به بها له لها لهم
    وهو وهي التى الي الى و يا اي أي كيف اين أين متى مته لدى سوف قبل بعد
    """.split()
)

URDU_STOPWORDS = frozenset(
    """
    کا کی کے کو میں سے پر نے ہے ہیں تھا تھی تھے اور یا لیکن جو کہ یہ وہ ان اس
    ہم آپ نہیں بھی تو ہی کیا کیوں کب کہاں کون کس ایک ساتھ لیے لئے بارے پھر
    اگر جب تک ہر کچھ بہت زیادہ کم اپنے اپنی اپنا وغیرہ گیا گئی گئے کرنے کرنا
    ہوتا ہوتی ہوتے رہا رہی رہے دیا دی دیے والا والی والے
    """.split()
)

# Chinese function characters. Because Chinese is indexed as bigrams, these
# are used to drop a bigram only when every character in it is a function
# character. That removes noise like 的是 without eating content bigrams that
# happen to touch a particle.
CHINESE_STOP_CHARS = frozenset(
    "的了是在和有我你他她它们这那就不也与及为之以于或但而都很吗呢吧个一"
    "被把让从对向所并且还又只再没什么怎哪些当因所以如果虽然然后可以"
)

STOPWORDS_BY_LANGUAGE = {
    "en": ENGLISH_STOPWORDS,
    "de": GERMAN_STOPWORDS,
    "ar": ARABIC_STOPWORDS,
    "ur": URDU_STOPWORDS,
    "zh": frozenset(),  # handled per character, see CHINESE_STOP_CHARS
}


def stopwords_for(language: str) -> frozenset[str]:
    """Stopwords for a language code, English for anything unknown."""
    return STOPWORDS_BY_LANGUAGE.get(language, ENGLISH_STOPWORDS)


# ------------------------------------------------------------------ detection

# Latin runs used to score English against German. Digits are included so a
# run breaks on the same boundaries the tokeniser uses; anything that is not
# pure letters is then skipped, so an identifier like "zu5bbradmb" cannot
# score a German hit for the "zu" buried inside it.
_LATIN_WORD = re.compile(r"[a-z0-9äöüß]+")


@dataclass(frozen=True)
class LanguageGuess:
    language: str
    confidence: float  # 0.0 means no evidence at all


# One Han character carries about as much meaning as a whole Latin word, so
# comparing raw character counts would let a couple of English words outvote
# a full Chinese phrase. Weighting Han and kana puts the two on a fairer
# footing when deciding which language a mixed query is mostly in.
_CJK_WEIGHT = 2.5


def _script_counts(text: str) -> dict[str, float]:
    counts: dict[str, float] = {"latin": 0.0, "arabic": 0.0, "cjk": 0.0}
    for char in text:
        if not char.isalpha():
            continue
        code_point = ord(char)
        if _in_ranges(code_point, _CJK_RANGES):
            counts["cjk"] += _CJK_WEIGHT
        elif _in_ranges(code_point, _ARABIC_RANGES):
            counts["arabic"] += 1.0
        elif code_point < 0x0370:  # Latin, including the accented supplements
            counts["latin"] += 1.0
    return counts


def _arabic_or_urdu(text: str) -> LanguageGuess:
    if any(char in _URDU_ONLY_CHARS for char in text):
        return LanguageGuess("ur", 0.95)
    words = text.split()
    if not words:
        return LanguageGuess("ar", 0.6)
    urdu_hits = sum(1 for word in words if word.strip("،۔؟!.,") in URDU_STOPWORDS)
    arabic_hits = sum(1 for word in words if word.strip("،۔؟!.,") in ARABIC_STOPWORDS)
    if urdu_hits > arabic_hits:
        return LanguageGuess("ur", 0.7)
    # Arabic script with no Urdu-only letters is Arabic by default.
    return LanguageGuess("ar", 0.8 if arabic_hits else 0.6)


# Words on both lists ("an", "in", "so", "was") say nothing about which of
# the two languages this is, so they are left out of the scoring entirely.
_GERMAN_ONLY = GERMAN_STOPWORDS - ENGLISH_STOPWORDS
_ENGLISH_ONLY = ENGLISH_STOPWORDS - GERMAN_STOPWORDS

# How much German evidence is needed before English is given up. The two
# mistakes are not equally bad. Reading English as German drops real English
# tokens as if they were stopwords, which loses content. Reading German as
# English only leaves a few German function words in the token list, which
# costs a little index noise and nothing else, because the words themselves
# still tokenise correctly. So the bar leans towards English.
#
# An umlaut or eszett settles it on its own, since English never has one.
# Without them, German has to show at least three of its own function words,
# which stops a stray "es" or "im" in an identifier from flipping the whole
# document.
_GERMAN_MIN_EVIDENCE_WITH_UMLAUT = 2.0
_GERMAN_MIN_EVIDENCE_ASCII = 3.0
# Share of words that must be German function words for the two-word case,
# and the shortest run of words it is allowed to apply to. Without the
# length floor, a part number like "SKU IM-450 UM-12" reads as German
# because "im" and "um" are two thirds of its words.
_GERMAN_MIN_SHARE = 0.2
_GERMAN_MIN_WORDS = 6


def _english_or_german(text: str) -> LanguageGuess:
    lowered = text.lower()
    words = [word for word in _LATIN_WORD.findall(lowered) if word.isalpha()]
    if not words:
        return LanguageGuess(DEFAULT_LANGUAGE, 0.0)
    german_hits = sum(1 for word in words if word in _GERMAN_ONLY)
    english_hits = sum(1 for word in words if word in _ENGLISH_ONLY)
    # Two-letter matches like "es" or "im" turn up by chance in part numbers
    # and identifiers. Real German always brings longer function words too
    # ("der", "und", "nicht"), so at least one of those is required before
    # English is given up on the strength of function words alone.
    german_long_hits = sum(1 for word in words if len(word) > 2 and word in _GERMAN_ONLY)
    # Umlauts and eszett never appear in English, so they count for a lot.
    german_chars = sum(1 for char in lowered if char in _GERMAN_CHARS)
    german_score = german_hits + 2.0 * german_chars
    english_score = float(english_hits)
    total = german_score + english_score
    if total == 0:
        # No function words either way: a bare noun phrase like "Atlas P2".
        return LanguageGuess(DEFAULT_LANGUAGE, 0.0)
    needed = (
        _GERMAN_MIN_EVIDENCE_WITH_UMLAUT if german_chars else _GERMAN_MIN_EVIDENCE_ASCII
    )
    # A short German question without umlauts, "Was kostet der Plan pro
    # Roboter und Monat?", only gets two function words and would otherwise
    # miss the bar. Allow it when nothing points at English at all and the
    # German words are a real share of the sentence rather than one stray
    # match in a wall of identifiers.
    if (
        english_hits == 0
        and german_hits >= 2
        and len(words) >= _GERMAN_MIN_WORDS
        and german_hits / len(words) >= _GERMAN_MIN_SHARE
    ):
        needed = min(needed, float(german_hits))
    has_german_signal = german_chars > 0 or german_long_hits > 0
    if has_german_signal and german_score >= needed and german_score > english_score:
        return LanguageGuess("de", (german_score - english_score) / total)
    return LanguageGuess(DEFAULT_LANGUAGE, max(english_score - german_score, 0.0) / total)


def detect_language_detailed(text: str) -> LanguageGuess:
    """Best guess plus a rough confidence between 0.0 and 1.0.

    Mixed-language input resolves to whichever language contributes most:
    scripts are compared by character count, and inside the Latin script
    English and German are compared by stopword hits.
    """
    if not text or not text.strip():
        return LanguageGuess(DEFAULT_LANGUAGE, 0.0)
    counts = _script_counts(text)
    total = sum(counts.values())
    if total == 0:
        return LanguageGuess(DEFAULT_LANGUAGE, 0.0)
    script, script_count = max(counts.items(), key=lambda pair: pair[1])
    share = script_count / total
    if script == "cjk":
        return LanguageGuess("zh", share)
    if script == "arabic":
        guess = _arabic_or_urdu(text)
        return LanguageGuess(guess.language, min(guess.confidence, share))
    return _english_or_german(text)


def detect_language(text: str, min_confidence: float = 0.0) -> str:
    """Language code for a piece of text, English when the evidence is thin.

    A non-Latin script is evidence on its own, so short Arabic or Chinese
    queries still detect correctly. Short Latin queries with no function
    words carry no signal and fall back to English, which is the default
    the rest of the project assumes.
    """
    guess = detect_language_detailed(text)
    if guess.confidence < min_confidence:
        return DEFAULT_LANGUAGE
    return guess.language


def language_name(language: str) -> str:
    """Human-readable name, used in the answer-language prompt rule."""
    return LANGUAGE_NAMES.get(language, LANGUAGE_NAMES[DEFAULT_LANGUAGE])
