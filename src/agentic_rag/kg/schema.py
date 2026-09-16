"""Schema for the knowledge graph: what a node is and what an edge means.

Deliberately small. Five entity types and four edge types cover the
relational questions this corpus can actually answer, and a small schema
is one an offline extractor can fill reliably and a reader can hold in
their head. Anything the extractor is unsure of is dropped rather than
guessed, because a wrong edge sends traversal somewhere false and is
worse than a missing one.

Note on naming: `agentic_rag.graph` is the orchestration graph
(decompose, branch, merge). This package is the knowledge graph, which
is a different thing entirely, so it lives under `kg` to keep the two
from being confused at import sites.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# Entity types. COMPANY and PRODUCT carry most of the corpus; STANDARD is
# what makes compliance questions traversable; LOCATION and PERSON connect
# organisations to places and people.
ENTITY_TYPES = ("COMPANY", "PRODUCT", "PERSON", "STANDARD", "LOCATION")

# Edge types, each written source -> target.
#   PRODUCT  MADE_BY       COMPANY
#   COMPANY  SUPPLIES      COMPANY | PRODUCT
#   PRODUCT | COMPANY  COMPLIES_WITH  STANDARD
#   COMPANY | PERSON   LOCATED_IN     LOCATION
EDGE_TYPES = ("MADE_BY", "SUPPLIES", "COMPLIES_WITH", "LOCATED_IN")

# Which (source type, target type) pairs an edge type is allowed to join.
# The extractor checks this, so a cue word cannot produce a nonsense edge
# like a LOCATION complying with a STANDARD.
EDGE_DOMAINS: dict[str, set[tuple[str, str]]] = {
    "MADE_BY": {("PRODUCT", "COMPANY")},
    "SUPPLIES": {("COMPANY", "COMPANY"), ("COMPANY", "PRODUCT")},
    "COMPLIES_WITH": {("PRODUCT", "STANDARD"), ("COMPANY", "STANDARD")},
    "LOCATED_IN": {("COMPANY", "LOCATION"), ("PERSON", "LOCATION")},
}

_WS = re.compile(r"\s+")
_EDGE_PUNCT = re.compile(r"^[\s\"'(\[,.;:]+|[\s\"')\],.;:]+$")


def normalize(name: str) -> str:
    """Fold a surface form into the key entities are merged on.

    Case and whitespace only, plus Unicode NFKC so widths and composed
    forms agree. Nothing clever: no stemming, no fuzzy matching, no
    embedding similarity. See the limits noted in the README.
    """
    text = unicodedata.normalize("NFKC", name)
    text = _EDGE_PUNCT.sub("", text)
    text = _WS.sub(" ", text).strip()
    return text.casefold()


def entity_id(entity_type: str, name: str) -> str:
    return f"{entity_type}:{normalize(name)}"


@dataclass(frozen=True)
class Entity:
    """A node. `name` is the display form, `surface` is how it appeared.

    The two differ when an alias matched: a German or Arabic chunk keeps
    its own surface form while resolving to the same canonical node, so
    traversal can cross languages without losing what the text said.
    """

    name: str
    type: str
    surface: str = ""

    @property
    def id(self) -> str:
        return entity_id(self.type, self.name)

    def __post_init__(self) -> None:
        if self.type not in ENTITY_TYPES:
            raise ValueError(f"Unknown entity type: {self.type!r}")


@dataclass(frozen=True)
class Relation:
    """An edge, with the sentence it came from so it can be shown as evidence."""

    source: Entity
    target: Entity
    type: str
    sentence: str = ""

    def __post_init__(self) -> None:
        if self.type not in EDGE_TYPES:
            raise ValueError(f"Unknown edge type: {self.type!r}")

    def allowed(self) -> bool:
        return (self.source.type, self.target.type) in EDGE_DOMAINS[self.type]


@dataclass
class ChunkGraph:
    """What one chunk contributed."""

    entities: list[Entity] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)


# --------------------------------------------------------------- aliases

# Surface forms that mean the same node. This is the whole of entity
# resolution: an exact lookup after normalisation. It exists so the same
# company written "Auralis" and "Auralis Dynamics", or a product named in
# another script, land on one node instead of three.
#
# Keys are normalised surface forms, values are (canonical name, type).
BUILTIN_ALIASES: dict[str, tuple[str, str]] = {
    "auralis": ("Auralis Dynamics", "COMPANY"),
    "auralis dynamics gmbh": ("Auralis Dynamics", "COMPANY"),
    "atlas": ("Atlas P2", "PRODUCT"),
    "atlas platform": ("Atlas P2", "PRODUCT"),
    "the atlas platform": ("Atlas P2", "PRODUCT"),
    "atlas p2 platform": ("Atlas P2", "PRODUCT"),
    "atlas hive": ("Atlas Hive", "PRODUCT"),
    "hive": ("Atlas Hive", "PRODUCT"),
    "iso 3691-4": ("ISO 3691-4:2023", "STANDARD"),
    "iso 3691-4:2023": ("ISO 3691-4:2023", "STANDARD"),
    # other scripts, so a German or Arabic chunk resolves to the same node
    "atlas plattform": ("Atlas P2", "PRODUCT"),
    "atlas-plattform": ("Atlas P2", "PRODUCT"),
    "أطلس": ("Atlas P2", "PRODUCT"),
    "أطلس بي 2": ("Atlas P2", "PRODUCT"),
    "阿特拉斯": ("Atlas P2", "PRODUCT"),
    "阿特拉斯 p2": ("Atlas P2", "PRODUCT"),
    "اٹلس": ("Atlas P2", "PRODUCT"),
    "münchen": ("Munich", "LOCATION"),
}


def load_aliases(path: Path | None = None) -> dict[str, tuple[str, str]]:
    """Built-in aliases plus an optional JSON file of the same shape.

    The file is `{"surface form": ["Canonical Name", "TYPE"]}`. A missing
    or unreadable file is not an error: aliases are an improvement, never
    a requirement.
    """
    aliases = dict(BUILTIN_ALIASES)
    if path is None or not Path(path).exists():
        return aliases
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return aliases
    for surface, value in raw.items():
        if isinstance(value, list) and len(value) == 2 and value[1] in ENTITY_TYPES:
            aliases[normalize(surface)] = (value[0], value[1])
    return aliases


def resolve(name: str, entity_type: str, aliases: dict[str, tuple[str, str]]) -> Entity:
    """Map a surface form to its canonical entity, keeping the original form."""
    key = normalize(name)
    canonical, canonical_type = aliases.get(key, (name.strip(), entity_type))
    return Entity(name=canonical, type=canonical_type, surface=name.strip())
