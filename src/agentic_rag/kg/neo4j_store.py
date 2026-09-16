"""Optional Neo4j backend, selected with GRAPH_STORE=neo4j.

An extra, never a requirement. Nothing in the default path or the test
suite imports this module, and the driver is not a project dependency:
install it with `pip install "agentic-rag-assistant[neo4j]"` when you
want it. The reason to reach for it is a graph too large for one SQLite
file, or one that other systems need to query directly.

The interface matches SqliteGraphStore, so everything above the store
works the same either way.
"""

from __future__ import annotations

from agentic_rag.kg.schema import Entity, Relation
from agentic_rag.kg.store import StoredEdge


class Neo4jGraphStore:
    name = "neo4j"

    def __init__(self, settings):
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:  # pragma: no cover - optional extra
            raise RuntimeError(
                "GRAPH_STORE=neo4j needs the driver: pip install neo4j "
                '(or pip install "agentic-rag-assistant[neo4j]")'
            ) from exc
        if not settings.neo4j_uri:
            raise RuntimeError("GRAPH_STORE=neo4j requires NEO4J_URI. Put it in .env.")
        self._driver = GraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
        )
        self.database = settings.neo4j_database or None

    def _run(self, query: str, **params):  # pragma: no cover - optional extra
        with self._driver.session(database=self.database) as session:
            return list(session.run(query, **params))

    def add_document(self, doc_id, entities, relations) -> dict:  # pragma: no cover
        entities, relations = list(entities), list(relations)
        self._run("MATCH ()-[r:REL {doc_id: $doc}]-() DELETE r", doc=doc_id)
        self._run("MATCH (m:Mention {doc_id: $doc}) DETACH DELETE m", doc=doc_id)
        for entity, chunk_id in entities:
            self._run(
                "MERGE (e:Entity {id: $id}) SET e.name = $name, e.type = $type "
                "MERGE (m:Mention {entity_id: $id, chunk_id: $chunk, doc_id: $doc}) "
                "SET m.surface = $surface MERGE (e)-[:MENTIONED_IN]->(m)",
                id=entity.id, name=entity.name, type=entity.type,
                chunk=chunk_id, doc=doc_id, surface=entity.surface or entity.name,
            )
        for relation, chunk_id in relations:
            self._run(
                "MERGE (a:Entity {id: $src}) SET a.name = $src_name, a.type = $src_type "
                "MERGE (b:Entity {id: $dst}) SET b.name = $dst_name, b.type = $dst_type "
                "MERGE (a)-[r:REL {type: $type, chunk_id: $chunk}]->(b) "
                "SET r.doc_id = $doc, r.sentence = $sentence",
                src=relation.source.id, src_name=relation.source.name,
                src_type=relation.source.type, dst=relation.target.id,
                dst_name=relation.target.name, dst_type=relation.target.type,
                type=relation.type, chunk=chunk_id, doc=doc_id,
                sentence=relation.sentence[:500],
            )
        return {"entities": len(entities), "relations": len(relations)}

    def clear(self) -> None:  # pragma: no cover
        self._run("MATCH (n) WHERE n:Entity OR n:Mention DETACH DELETE n")

    @property
    def entity_count(self) -> int:  # pragma: no cover
        rows = self._run("MATCH (e:Entity) RETURN count(e) AS n")
        return rows[0]["n"] if rows else 0

    @property
    def edge_count(self) -> int:  # pragma: no cover
        rows = self._run("MATCH ()-[r:REL]->() RETURN count(r) AS n")
        return rows[0]["n"] if rows else 0

    def doc_ids(self) -> set[str]:  # pragma: no cover
        return {row["d"] for row in self._run("MATCH (m:Mention) RETURN DISTINCT m.doc_id AS d")}

    def entity(self, entity_id: str) -> dict | None:  # pragma: no cover
        rows = self._run(
            "MATCH (e:Entity {id: $id}) RETURN e.id AS id, e.name AS name, e.type AS type",
            id=entity_id,
        )
        return dict(rows[0]) if rows else None

    def entities(self) -> list[dict]:  # pragma: no cover
        return [dict(r) for r in self._run(
            "MATCH (e:Entity) RETURN e.id AS id, e.name AS name, e.type AS type ORDER BY e.id"
        )]

    def find_entities(self, text: str, limit: int = 8) -> list[dict]:  # pragma: no cover
        lowered = text.casefold()
        hits = [e for e in self.entities() if e["name"].casefold() in lowered]
        hits.sort(key=lambda item: len(item["name"]), reverse=True)
        return hits[:limit]

    def neighbours(self, entity_id: str) -> list[StoredEdge]:  # pragma: no cover
        rows = self._run(
            "MATCH (a:Entity)-[r:REL]-(b:Entity) WHERE a.id = $id "
            "RETURN startNode(r).id AS source_id, endNode(r).id AS target_id, "
            "r.type AS type, r.doc_id AS doc_id, r.chunk_id AS chunk_id, "
            "coalesce(r.sentence, '') AS sentence",
            id=entity_id,
        )
        return [StoredEdge(**dict(row)) for row in rows]

    def chunks_for(self, entity_ids) -> list[str]:  # pragma: no cover
        ids = list(entity_ids)
        if not ids:
            return []
        rows = self._run(
            "MATCH (m:Mention) WHERE m.entity_id IN $ids RETURN DISTINCT m.chunk_id AS c", ids=ids
        )
        return [row["c"] for row in rows]

    def stats(self) -> dict:  # pragma: no cover
        return {
            "backend": self.name,
            "entities": self.entity_count,
            "relations": self.edge_count,
            "documents": len(self.doc_ids()),
        }

    def close(self) -> None:  # pragma: no cover
        self._driver.close()


__all__ = ["Neo4jGraphStore", "Entity", "Relation"]
