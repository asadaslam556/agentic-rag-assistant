"""Entity and relationship extraction, one function per backend.

Same shape as `llm/providers.py`: builders tagged with `@register("name")`
and picked at runtime from a setting, so adding an extractor is one
function and nothing else.

Two ship. The offline one is rules and patterns, needs no key and no
network, and is what the tests and a fresh clone use. The LLM one asks
the configured provider for JSON per chunk and reads far more than
patterns can, at the cost of one call per chunk.

Cost, stated plainly: with the LLM extractor, ingesting a document of N
chunks makes N model calls on top of embedding. The sample corpus is
about 30 chunks; a few hundred PDF pages is a few hundred calls. The
offline extractor makes none.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable

from agentic_rag.config import Settings
from agentic_rag.core.textutils import split_sentences
from agentic_rag.kg.schema import (
    EDGE_DOMAINS,
    ENTITY_TYPES,
    ChunkGraph,
    Entity,
    Relation,
    load_aliases,
    normalize,
    resolve,
)

Extractor = Callable[[str, Settings], ChunkGraph]

_BUILDERS: dict[str, Callable[[Settings], Extractor]] = {}


class ExtractorError(RuntimeError):
    """An extractor could not be set up, with a message a person can act on."""


def register(name: str) -> Callable[[Callable[[Settings], Extractor]], Callable[[Settings], Extractor]]:
    def decorator(builder: Callable[[Settings], Extractor]) -> Callable[[Settings], Extractor]:
        _BUILDERS[name] = builder
        return builder

    return decorator


def known_extractors() -> list[str]:
    return sorted(_BUILDERS)


# ------------------------------------------------------------ offline rules

# Standards carry their own format and survive translation untouched, which
# is why a German, Arabic, or Chinese chunk still yields this one.
# A bare "EN" or "CE" is a word, not a standard, so the numbered families
# must carry their number. The few that are standards under their own name
# are listed separately.
_STANDARD = re.compile(r"\b(?:ISO|IEC|EN|DIN|ANSI|IEEE|SOC)[\s/-]?\d[\w\-:./]*")
_STANDARD_NAMED = re.compile(r"\b(?:GDPR|CE marking|SOC 2 Type I{1,2})\b")

# "Auralis Dynamics", "Lakeshore Industrial Ventures": capitalised words
# closed by a corporate suffix.
_COMPANY = re.compile(
    r"\b((?:[A-Z][\w&.-]*\s+){0,3}?[A-Z][\w&.-]*\s+"
    r"(?:Dynamics|Ventures|Technologies|Robotics|Systems|Solutions|Industries|"
    r"Group|Labs|Holdings|GmbH|AG|SE|Inc\.?|Ltd\.?|Corp\.?|LLC|NV|BV))\b"
)

# "Atlas P2": a capitalised name followed by a model code.
_PRODUCT = re.compile(r"\b([A-Z][a-zA-Z]+)\s+([A-Z]{1,3}\d+[A-Za-z]*)\b")

_PERSON = re.compile(
    r"\b(?:CEO|CTO|CFO|COO|Dr|Mr|Ms|Mrs|Prof)\.?\s+((?:[A-Z][a-z]+\s+){1,2}[A-Z][a-z]+)\b"
)
_PERSON_TRAILING = re.compile(r"\b((?:[A-Z][a-z]+\s+){1,2}[A-Z][a-z]+),\s+(?:CEO|CTO|CFO|COO)\b")

# Only explicit place cues. Bare "in", "at", and "from" turn every
# capitalized phrase into a location: real financial documents produced
# "located in Advanced Therapies" (a segment), "in China Revenue" (a table
# header), and "at Barclays" (an analyst's employer). A single capitalized
# word, optionally followed by a country, is also enough; allowing two
# adjacent capitalized words is what captured those phrases.
_LOCATION = re.compile(
    r"\b(?:based in|headquartered in|located in|founded in|offices in|"
    r"headquarters in|plant in|site in)\s+"
    r"(?:\d{4}\s+in\s+)?"  # "founded in 2019 in Munich"
    r"([A-Z][a-z]{2,}(?:,\s+[A-Z][a-z]{2,})?)\b"
)

# Capitalised words that follow "in" but are not places.
_NOT_A_PLACE = {
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "monday", "tuesday",
    "wednesday", "thursday", "friday", "saturday", "sunday", "the", "every",
    "each", "this", "that", "these", "those", "operation", "mixed", "robot",
    "european", "eu", "north", "south", "east", "west", "q1", "q2", "q3", "q4",
    # business words that follow a place cue in financial reporting
    "revenue", "revenues", "growth", "margin", "earnings", "sales", "orders",
    "segment", "segments", "therapies", "imaging", "diagnostics", "cloud",
    "software", "services", "total", "group", "line", "lines", "business",
    "market", "markets", "region", "regions", "quarter", "half", "year",
    "guidance", "outlook", "portfolio", "demand", "pricing", "costs",
}

# Cue words between two mentions that name the relation. Checked against the
# text between them, so word order carries meaning.
_CUES: dict[str, tuple[str, ...]] = {
    "MADE_BY": ("from", "by", "made by", "built by", "manufactured by", "developed by", "von"),
    "COMPLIES_WITH": (
        "certified to", "certified", "complies with", "conforms to", "meets",
        "carries", "accredited to", "zertifiziert", "nach", "معتمدة", "通过",
    ),
    "LOCATED_IN": (
        "in", "based in", "headquartered in", "founded in", "located in", "operates in",
    ),
    "SUPPLIES": (
        "supplies", "supplier of", "provides", "sells", "delivers", "integrates with",
    ),
}

_MAX_GAP_CHARS = 90  # how far apart two mentions may sit and still be related


def _add(found: list[tuple[int, int, str, str]], start: int, end: int, name: str, kind: str) -> None:
    name = name.strip()
    if len(name) < 2:
        return
    # drop a mention that sits inside one already found, so "Atlas P2" wins
    # over a bare "Atlas" at the same position
    for other_start, other_end, _, _ in found:
        if start >= other_start and end <= other_end:
            return
    found.append((start, end, name, kind))


def _mentions(sentence: str, aliases: dict) -> list[tuple[int, int, Entity]]:
    """Every entity mention in one sentence, with its span, longest first."""
    found: list[tuple[int, int, str, str]] = []

    # Order matters: whatever claims a span first keeps it, and _add drops a
    # mention that sits inside one already found. Aliases and the named
    # standards go first so "Atlas Hive" beats a bare "Hive" read as a place
    # and "SOC 2 Type II" beats the "SOC 2" inside it.
    lowered_early = sentence.casefold()
    for surface in sorted(aliases, key=len, reverse=True):
        if not surface:
            continue
        start = lowered_early.find(surface)
        if start >= 0:
            _add(found, start, start + len(surface), sentence[start : start + len(surface)],
                 aliases[surface][1])
    for match in _STANDARD_NAMED.finditer(sentence):
        _add(found, match.start(), match.end(), match.group(0), "STANDARD")
    for match in _PRODUCT.finditer(sentence):
        _add(found, match.start(), match.end(), match.group(0), "PRODUCT")
    for match in _COMPANY.finditer(sentence):
        _add(found, match.start(1), match.end(1), match.group(1), "COMPANY")
    for match in _STANDARD.finditer(sentence):
        _add(found, match.start(), match.end(), match.group(0), "STANDARD")
    for pattern in (_PERSON, _PERSON_TRAILING):
        for match in pattern.finditer(sentence):
            _add(found, match.start(1), match.end(1), match.group(1), "PERSON")
    for match in _LOCATION.finditer(sentence):
        candidate = match.group(1)
        if normalize(candidate.split(",")[0]) in _NOT_A_PLACE:
            continue
        # "Munich, Germany" and "Munich" are one place; keeping the city
        # alone merges them without any fuzzy matching
        city = candidate.split(",")[0].strip()
        _add(found, match.start(1), match.start(1) + len(city), city, "LOCATION")

    found.sort(key=lambda item: item[0])
    return [(s, e, resolve(name, kind, aliases)) for s, e, name, kind in found]


def _relations(sentence: str, mentions: list[tuple[int, int, Entity]]) -> list[Relation]:
    relations: list[Relation] = []
    for i, (_, left_end, left) in enumerate(mentions):
        for right_start, _, right in mentions[i + 1 :]:
            if left.id == right.id:
                continue
            gap = sentence[left_end:right_start]
            if len(gap) > _MAX_GAP_CHARS:
                continue
            gap_lower = gap.casefold()
            for edge_type, cues in _CUES.items():
                if (left.type, right.type) not in EDGE_DOMAINS[edge_type]:
                    continue
                # Every edge needs its cue. Letting a product and a standard
                # in one sentence imply compliance produced edges like the
                # robot complying with GDPR, which is stated about cloud
                # telemetry two sentences away. A missing edge costs a hop; a
                # wrong one sends traversal somewhere false.
                if any(cue in gap_lower for cue in cues):
                    relation = Relation(left, right, edge_type, sentence.strip())
                    if relation.allowed():
                        relations.append(relation)
                    break
    return relations


@register("offline")
def _build_offline(settings: Settings) -> Extractor:
    aliases = load_aliases(settings.graph_alias_path)
    cap = settings.graph_max_entities_per_chunk

    def extract(text: str, _settings: Settings = settings) -> ChunkGraph:
        entities: dict[str, Entity] = {}
        relations: list[Relation] = []
        for sentence in split_sentences(text):
            mentions = _mentions(sentence, aliases)
            for _, _, entity in mentions:
                entities.setdefault(entity.id, entity)
            relations.extend(_relations(sentence, mentions))
        capped = list(entities.values())[:cap]
        keep = {entity.id for entity in capped}
        return ChunkGraph(
            entities=capped,
            relations=[r for r in relations if r.source.id in keep and r.target.id in keep],
        )

    return extract


# -------------------------------------------------------------- LLM backend

_LLM_SYSTEM = """## MODE: GRAPH_EXTRACT

Extract entities and relationships from the passage for a knowledge graph.

ENTITY TYPES: COMPANY, PRODUCT, PERSON, STANDARD, LOCATION
EDGE TYPES and the types they join:
- MADE_BY: PRODUCT -> COMPANY
- SUPPLIES: COMPANY -> COMPANY, COMPANY -> PRODUCT
- COMPLIES_WITH: PRODUCT -> STANDARD, COMPANY -> STANDARD
- LOCATED_IN: COMPANY -> LOCATION, PERSON -> LOCATION

RULES:
- Only what the passage states. Never infer from background knowledge.
- Keep names exactly as written, in the original script.
- Skip anything that does not fit a type above.
- At most __CAP__ entities.

Respond with one JSON object and nothing else:
{"entities": [{"name": "...", "type": "..."}],
 "relations": [{"source": "...", "target": "...", "type": "..."}]}
"""


@register("llm")
def _build_llm(settings: Settings) -> Extractor:
    from agentic_rag.agent.parser import ParserError, extract_first_json
    from agentic_rag.llm import get_llm

    client = get_llm(settings)
    aliases = load_aliases(settings.graph_alias_path)
    cap = settings.graph_max_entities_per_chunk
    system = _LLM_SYSTEM.replace("__CAP__", str(cap))
    fallback = _build_offline(settings)

    state = {"warned": False, "parse_failures": 0, "call_failures": 0}

    def extract(text: str, _settings: Settings = settings) -> ChunkGraph:
        try:
            # generous, because a thinking model spends most of this before it
            # writes any JSON
            reply = client.complete(
                system, [{"role": "user", "content": text}], max_tokens=settings.graph_extract_max_tokens
            )
        except Exception as exc:  # noqa: BLE001
            # The call itself failed: wrong key, wrong model, no network. That
            # degrades the whole run, not one chunk, so say so once. Silently
            # falling back made a broken provider look like a working one.
            state["call_failures"] += 1
            if not state["warned"]:
                state["warned"] = True
                print(
                    f"warning: LLM extraction is failing, falling back to the offline "
                    f"rules for every chunk. First error: {str(exc)[:300]}",
                    file=sys.stderr,
                )
            return fallback(text)
        try:
            payload = extract_first_json(reply.text)
        except ParserError:
            # One unparseable reply loses that chunk's edges, not the ingest.
            state["parse_failures"] += 1
            return fallback(text)

        by_name: dict[str, Entity] = {}
        entities: dict[str, Entity] = {}
        for item in (payload.get("entities") or [])[:cap]:
            name, kind = str(item.get("name", "")).strip(), str(item.get("type", "")).strip().upper()
            if not name or kind not in ENTITY_TYPES:
                continue
            entity = resolve(name, kind, aliases)
            entities[entity.id] = entity
            by_name[normalize(name)] = entity

        relations: list[Relation] = []
        for item in payload.get("relations") or []:
            source = by_name.get(normalize(str(item.get("source", ""))))
            target = by_name.get(normalize(str(item.get("target", ""))))
            kind = str(item.get("type", "")).strip().upper()
            if not source or not target or kind not in EDGE_DOMAINS:
                continue
            relation = Relation(source, target, kind, text.strip()[:400])
            if relation.allowed():
                relations.append(relation)
        return ChunkGraph(entities=list(entities.values()), relations=relations)

    extract.state = state  # so a caller can report how the run went
    return extract


# ---------------------------------------------------------------- selection


def resolve_extractor_name(settings: Settings) -> str:
    """Which extractor `auto` means for these settings.

    `auto` stays offline unless a provider was chosen deliberately. Falling
    into LLM extraction because Ollama happened to be running would make a
    plain `rag ingest` quietly cost one model call per chunk.
    """
    choice = (settings.graph_extractor or "auto").lower()
    if choice != "auto":
        return choice
    provider = (settings.llm_provider or "auto").lower()
    return "llm" if provider not in ("auto", "mock") else "offline"


def build_extractor(settings: Settings) -> Extractor:
    name = resolve_extractor_name(settings)
    builder = _BUILDERS.get(name)
    if builder is None:
        raise ExtractorError(
            f"Unknown GRAPH_EXTRACTOR: {name!r} (use {', '.join(known_extractors())}, or auto)"
        )
    return builder(settings)
