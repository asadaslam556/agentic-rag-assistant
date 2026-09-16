"""Where the graph lives.

SQLite is the default because it is in the standard library: a fresh
clone gets a working graph with no service to install and no container to
run, the same bargain the hashed local embedder makes for vectors.

Writes are idempotent per document. Re-ingesting a document deletes
everything it contributed and rewrites it, so running ingest twice cannot
double an edge, matching how the vector store skips documents it already
holds.

An optional Neo4j backend is selected with GRAPH_STORE=neo4j. It is an
extra, never a requirement: no test and no default run touches it.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from agentic_rag.kg.schema import Entity, Relation

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    id      TEXT PRIMARY KEY,
    name    TEXT NOT NULL,
    type    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mentions (
    entity_id TEXT NOT NULL,
    doc_id    TEXT NOT NULL,
    chunk_id  TEXT NOT NULL,
    surface   TEXT NOT NULL,
    PRIMARY KEY (entity_id, chunk_id, surface)
);
CREATE TABLE IF NOT EXISTS edges (
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    type      TEXT NOT NULL,
    doc_id    TEXT NOT NULL,
    chunk_id  TEXT NOT NULL,
    sentence  TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (source_id, target_id, type, chunk_id)
);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_mentions_entity ON mentions(entity_id);
CREATE INDEX IF NOT EXISTS idx_mentions_doc ON mentions(doc_id);
"""


@dataclass(frozen=True)
class StoredEdge:
    source_id: str
    target_id: str
    type: str
    doc_id: str
    chunk_id: str
    sentence: str = ""


class SqliteGraphStore:
    """Entities, mentions, and edges in one file next to the vector index."""

    name = "sqlite"

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Branches run in parallel and share this connection. sqlite3 may or
        # may not serialise for us depending on how the library was built
        # (threadsafety is 3 on Linux, lower elsewhere), and the Python
        # wrapper's implicit cursors interleave badly either way, which shows
        # up as "bad parameter or other API misuse". The lock is the fix; the
        # queries are small enough that contention does not matter.
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------- writing

    def add_document(
        self,
        doc_id: str,
        entities: Iterable[tuple[Entity, str]],
        relations: Iterable[tuple[Relation, str]],
    ) -> dict:
        """Replace everything `doc_id` contributed. Safe to call repeatedly."""
        entities = list(entities)
        relations = list(relations)
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM mentions WHERE doc_id = ?", (doc_id,))
            self._conn.execute("DELETE FROM edges WHERE doc_id = ?", (doc_id,))
            for entity, chunk_id in entities:
                self._conn.execute(
                    "INSERT OR IGNORE INTO entities (id, name, type) VALUES (?, ?, ?)",
                    (entity.id, entity.name, entity.type),
                )
                self._conn.execute(
                    "INSERT OR REPLACE INTO mentions (entity_id, doc_id, chunk_id, surface) "
                    "VALUES (?, ?, ?, ?)",
                    (entity.id, doc_id, chunk_id, entity.surface or entity.name),
                )
            for relation, chunk_id in relations:
                for node in (relation.source, relation.target):
                    self._conn.execute(
                        "INSERT OR IGNORE INTO entities (id, name, type) VALUES (?, ?, ?)",
                        (node.id, node.name, node.type),
                    )
                self._conn.execute(
                    "INSERT OR REPLACE INTO edges "
                    "(source_id, target_id, type, doc_id, chunk_id, sentence) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        relation.source.id,
                        relation.target.id,
                        relation.type,
                        doc_id,
                        chunk_id,
                        relation.sentence[:500],
                    ),
                )
            # an entity nothing mentions any more is dead weight
            self._conn.execute(
                "DELETE FROM entities WHERE id NOT IN (SELECT entity_id FROM mentions) "
                "AND id NOT IN (SELECT source_id FROM edges) "
                "AND id NOT IN (SELECT target_id FROM edges)"
            )
        return {"entities": len(entities), "relations": len(relations)}

    def clear(self) -> None:
        with self._lock, self._conn:
            for table in ("mentions", "edges", "entities"):
                self._conn.execute(f"DELETE FROM {table}")

    # ------------------------------------------------------------- reading

    @property
    def entity_count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]

    @property
    def edge_count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    def doc_ids(self) -> set[str]:
        with self._lock:
            rows = self._conn.execute("SELECT DISTINCT doc_id FROM mentions").fetchall()
        return {row[0] for row in rows}

    def entity(self, entity_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, name, type FROM entities WHERE id = ?", (entity_id,)
            ).fetchone()
        return dict(row) if row else None

    def entities(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT id, name, type FROM entities ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def find_entities(self, text: str, limit: int = 8) -> list[dict]:
        """Entities whose name or a recorded surface form occurs in `text`.

        Longest name first, so "Atlas P2" is preferred over "Atlas" when
        both are present.
        """
        lowered = text.casefold()
        hits: list[dict] = []
        seen: set[str] = set()
        with self._lock:
            rows = self._conn.execute(
                "SELECT e.id, e.name, e.type, m.surface FROM entities e "
                "LEFT JOIN mentions m ON m.entity_id = e.id"
            ).fetchall()
        for row in rows:
            if row["id"] in seen:
                continue
            for candidate in (row["name"], row["surface"]):
                if candidate and candidate.casefold() in lowered:
                    hits.append({"id": row["id"], "name": row["name"], "type": row["type"]})
                    seen.add(row["id"])
                    break
        hits.sort(key=lambda item: len(item["name"]), reverse=True)
        return hits[:limit]

    def neighbours(self, entity_id: str) -> list[StoredEdge]:
        """Edges touching this node, in either direction."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT source_id, target_id, type, doc_id, chunk_id, sentence FROM edges "
                "WHERE source_id = ? OR target_id = ?",
                (entity_id, entity_id),
            ).fetchall()
        return [StoredEdge(**dict(row)) for row in rows]

    def chunks_for(self, entity_ids: Iterable[str]) -> list[str]:
        ids = list(entity_ids)
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT DISTINCT chunk_id FROM mentions WHERE entity_id IN ({placeholders})", ids
            ).fetchall()
        return [row[0] for row in rows]

    def stats(self) -> dict:
        with self._lock:
            by_type = {
                row[0]: row[1]
                for row in self._conn.execute(
                    "SELECT type, COUNT(*) FROM entities GROUP BY type ORDER BY type"
                ).fetchall()
            }
            by_edge = {
                row[0]: row[1]
                for row in self._conn.execute(
                    "SELECT type, COUNT(*) FROM edges GROUP BY type ORDER BY type"
                ).fetchall()
            }
        return {
            "backend": self.name,
            "path": str(self.path),
            "entities": self.entity_count,
            "relations": self.edge_count,
            "documents": len(self.doc_ids()),
            "entities_by_type": by_type,
            "relations_by_type": by_edge,
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def get_graph_store(settings) -> SqliteGraphStore:
    """The configured backend. SQLite unless GRAPH_STORE says otherwise."""
    backend = (settings.graph_store or "sqlite").lower()
    if backend == "sqlite":
        return SqliteGraphStore(settings.graph_path)
    if backend == "neo4j":
        from agentic_rag.kg.neo4j_store import Neo4jGraphStore

        return Neo4jGraphStore(settings)
    raise ValueError(f"Unknown GRAPH_STORE: {backend!r} (use sqlite or neo4j)")
