"""Building the graph, at ingest time and as a rebuild.

Rebuild reads the chunk text the vector store already keeps, the same way
`retrieval/reindex.py` does, so the original files do not need to be
around and chunk ids stay stable. That matters because the graph points
at chunks: if the ids moved, every edge would lose its evidence.

Failure policy: a chunk the extractor chokes on is skipped and counted, a
document that fails entirely is reported, and neither stops ingest. A
document in the index without its edges is a worse graph; a document
lost because graph building fell over is a worse corpus.
"""

from __future__ import annotations

from agentic_rag.config import Settings
from agentic_rag.core.types import Chunk
from agentic_rag.kg.extractors import build_extractor, resolve_extractor_name
from agentic_rag.kg.store import get_graph_store


def build_for_chunks(
    store,
    extractor,
    doc_id: str,
    chunks: list[Chunk],
    max_consecutive_failures: int = 5,
) -> dict:
    """Extract from one document's chunks and write them as a unit.

    Consecutive failures give up on the rest of the document rather than
    retrying every remaining chunk against a provider that is not
    responding. One-off failures scattered through a document (a bad
    reply here and there) do not trip this: the counter resets on every
    success, so it only fires on a genuine run of failures, which is what
    a stuck connection or an exhausted rate limit looks like.
    """
    entities: list[tuple] = []
    relations: list[tuple] = []
    failed = 0
    consecutive = 0
    stopped_early = False
    for chunk in chunks:
        try:
            result = extractor(chunk.text)
        except Exception:  # noqa: BLE001 - one bad chunk must not lose the rest
            failed += 1
            consecutive += 1
            if consecutive >= max_consecutive_failures:
                stopped_early = True
                failed += len(chunks) - chunks.index(chunk) - 1
                break
            continue
        consecutive = 0
        entities.extend((entity, chunk.id) for entity in result.entities)
        relations.extend((relation, chunk.id) for relation in result.relations)
    written = store.add_document(doc_id, entities, relations)
    written["chunks_failed"] = failed
    if stopped_early:
        written["stopped_early"] = True
    return written


def rebuild(settings: Settings | None = None, chunks: list[Chunk] | None = None) -> dict:
    """Rebuild the whole graph from stored chunks.

    Reads the vector store's chunks when none are passed, so
    `rag graph rebuild` works on an index alone.
    """
    settings = settings or Settings.from_env()
    if chunks is None:
        from agentic_rag.retrieval.reindex import read_chunks

        chunks = read_chunks(settings.index_path)
    if not chunks:
        return {
            "status": "empty",
            "message": f"No chunks found in {settings.index_path}. Run `rag ingest` first.",
        }

    store = get_graph_store(settings)
    extractor = build_extractor(settings)
    store.clear()

    by_document: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        by_document.setdefault(chunk.doc_id, []).append(chunk)

    documents = 0
    failed_chunks = 0
    errors: list[dict] = []
    for doc_id, doc_chunks in by_document.items():
        try:
            written = build_for_chunks(store, extractor, doc_id, doc_chunks)
            failed_chunks += written.get("chunks_failed", 0)
            documents += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"doc_id": doc_id, "error": str(exc)[:300]})

    result = {
        "status": "ok",
        "extractor": resolve_extractor_name(settings),
        "documents": documents,
        "chunks": len(chunks),
        **store.stats(),
    }
    if failed_chunks:
        result["chunks_failed"] = failed_chunks
    if errors:
        result["errors"] = errors
    return result


def stats(settings: Settings | None = None) -> dict:
    settings = settings or Settings.from_env()
    store = get_graph_store(settings)
    return {"extractor": resolve_extractor_name(settings), **store.stats()}
