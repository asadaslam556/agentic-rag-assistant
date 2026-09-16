"""Knowledge graph: extraction, storage, traversal, routing, end to end.

All offline. The deterministic extractor and the SQLite store need no key,
no network, and no service, which is the point of both defaults.
"""

from pathlib import Path

import pytest

from agentic_rag.config import Settings
from agentic_rag.core.types import Chunk, Document
from agentic_rag.ingestion.chunking import chunk_document
from agentic_rag.kg.build import build_for_chunks, rebuild, stats
from agentic_rag.kg.extractors import (
    build_extractor,
    known_extractors,
    resolve_extractor_name,
)
from agentic_rag.kg.schema import (
    EDGE_DOMAINS,
    EDGE_TYPES,
    ENTITY_TYPES,
    Entity,
    Relation,
    entity_id,
    normalize,
    resolve,
)
from agentic_rag.kg.store import SqliteGraphStore
from agentic_rag.kg.traverse import traverse
from agentic_rag.pipeline import AgenticRAG
from agentic_rag.tools.graph_search import GraphSearchTool

MADE_BY_TEXT = "The Atlas P2 is the current flagship autonomous mobile robot from Auralis Dynamics."
LOCATED_TEXT = "Auralis Dynamics was founded in 2019 in Munich, Germany."
COMPLIES_TEXT = (
    "The Atlas platform is certified to the ISO 3691-4:2023 safety standard "
    "for driverless industrial trucks."
)
GERMAN_TEXT = (
    "Die Atlas Plattform ist nach der Sicherheitsnorm ISO 3691-4:2023 zertifiziert."
)
ARABIC_TEXT = "منصة أطلس معتمدة وفق معيار السلامة ISO 3691-4:2023."


def _settings(tmp_path, **overrides):
    base = {
        "llm_provider": "mock",
        "embeddings_provider": "local",
        "local_embedding_dim": 256,
        "storage_dir": str(tmp_path),
        "search_provider": "none",
        "max_branches": 1,
    }
    base.update(overrides)
    return Settings(**base)


def _extract(tmp_path, text):
    return build_extractor(_settings(tmp_path))(text)


# ------------------------------------------------------------------ schema


def test_normalisation_folds_case_and_whitespace():
    assert normalize("  Auralis   Dynamics ") == normalize("auralis dynamics")
    assert entity_id("COMPANY", "Auralis Dynamics") == entity_id("COMPANY", "AURALIS  dynamics")


def test_an_unknown_type_is_rejected_rather_than_stored():
    with pytest.raises(ValueError):
        Entity(name="x", type="PLANET")
    with pytest.raises(ValueError):
        Relation(Entity("a", "COMPANY"), Entity("b", "LOCATION"), "ORBITS")


def test_edge_domains_cover_every_edge_type():
    assert set(EDGE_DOMAINS) == set(EDGE_TYPES)
    for pairs in EDGE_DOMAINS.values():
        for source, target in pairs:
            assert source in ENTITY_TYPES and target in ENTITY_TYPES


def test_an_edge_between_the_wrong_types_is_not_allowed():
    bad = Relation(Entity("Munich", "LOCATION"), Entity("ISO 9001", "STANDARD"), "COMPLIES_WITH")
    assert not bad.allowed()


def test_aliases_merge_surface_forms_but_keep_the_original():
    from agentic_rag.kg.schema import load_aliases

    aliases = load_aliases(None)
    entity = resolve("the Atlas platform", "PRODUCT", aliases)
    assert entity.name == "Atlas P2"
    assert entity.surface == "the Atlas platform"
    assert entity.id == resolve("Atlas P2", "PRODUCT", aliases).id


# -------------------------------------------------------------- extraction


def test_offline_extraction_is_deterministic(tmp_path):
    first = _extract(tmp_path, MADE_BY_TEXT)
    second = _extract(tmp_path, MADE_BY_TEXT)
    assert [(e.name, e.type) for e in first.entities] == [(e.name, e.type) for e in second.entities]
    assert [(r.source.name, r.type, r.target.name) for r in first.relations] == [
        (r.source.name, r.type, r.target.name) for r in second.relations
    ]


def test_offline_extractor_finds_the_three_corpus_relations(tmp_path):
    made = _extract(tmp_path, MADE_BY_TEXT)
    assert ("Atlas P2", "MADE_BY", "Auralis Dynamics") in [
        (r.source.name, r.type, r.target.name) for r in made.relations
    ]
    located = _extract(tmp_path, LOCATED_TEXT)
    assert ("Auralis Dynamics", "LOCATED_IN", "Munich") in [
        (r.source.name, r.type, r.target.name) for r in located.relations
    ]
    complies = _extract(tmp_path, COMPLIES_TEXT)
    assert ("Atlas P2", "COMPLIES_WITH", "ISO 3691-4:2023") in [
        (r.source.name, r.type, r.target.name) for r in complies.relations
    ]


def test_extraction_reads_non_english_chunks(tmp_path):
    """Standards survive translation, and aliases carry the product across."""
    german = _extract(tmp_path, GERMAN_TEXT)
    names = {e.name for e in german.entities}
    assert "ISO 3691-4:2023" in names
    assert "Atlas P2" in names  # via the German alias

    arabic = _extract(tmp_path, ARABIC_TEXT)
    assert "ISO 3691-4:2023" in {e.name for e in arabic.entities}


def test_non_english_surface_forms_keep_their_own_script(tmp_path):
    arabic = _extract(tmp_path, ARABIC_TEXT)
    product = [e for e in arabic.entities if e.type == "PRODUCT"]
    assert product, "the Arabic product mention should resolve"
    assert product[0].name == "Atlas P2"
    assert product[0].surface == "أطلس"


def test_a_bare_word_is_not_mistaken_for_a_standard(tmp_path):
    """EN and CE are words as often as they are standards families."""
    result = _extract(tmp_path, "The robot moves in the aisle and then stops.")
    assert not [e for e in result.entities if e.type == "STANDARD"]


def test_compliance_needs_a_cue_not_just_co_occurrence(tmp_path):
    """Two things in one sentence do not make a relationship."""
    text = "Atlas Hive telemetry is processed in the European Union and handled under GDPR."
    relations = _extract(tmp_path, text).relations
    assert not [r for r in relations if r.type == "COMPLIES_WITH" and r.source.name == "Atlas P2"]


def test_entities_per_chunk_are_capped(tmp_path):
    settings = _settings(tmp_path, graph_max_entities_per_chunk=2)
    text = " ".join([MADE_BY_TEXT, LOCATED_TEXT, COMPLIES_TEXT])
    result = build_extractor(settings)(text)
    assert len(result.entities) <= 2


def test_auto_stays_offline_unless_a_provider_was_chosen(tmp_path):
    assert resolve_extractor_name(_settings(tmp_path)) == "offline"
    assert resolve_extractor_name(_settings(tmp_path, llm_provider="auto")) == "offline"
    assert resolve_extractor_name(_settings(tmp_path, llm_provider="anthropic")) == "llm"
    assert resolve_extractor_name(_settings(tmp_path, graph_extractor="offline",
                                            llm_provider="anthropic")) == "offline"


def test_both_extractors_are_registered():
    assert set(known_extractors()) == {"offline", "llm"}


# ------------------------------------------------------------------- store


def _seed_store(tmp_path):
    store = SqliteGraphStore(tmp_path / "graph.sqlite3")
    atlas = Entity("Atlas P2", "PRODUCT")
    auralis = Entity("Auralis Dynamics", "COMPANY")
    munich = Entity("Munich", "LOCATION")
    iso = Entity("ISO 3691-4:2023", "STANDARD")
    store.add_document(
        "doc1",
        [(atlas, "doc1:0"), (auralis, "doc1:0")],
        [(Relation(atlas, auralis, "MADE_BY", MADE_BY_TEXT), "doc1:0")],
    )
    store.add_document(
        "doc2",
        [(auralis, "doc2:0"), (munich, "doc2:0")],
        [(Relation(auralis, munich, "LOCATED_IN", LOCATED_TEXT), "doc2:0")],
    )
    store.add_document(
        "doc3",
        [(atlas, "doc3:0"), (iso, "doc3:0")],
        [(Relation(atlas, iso, "COMPLIES_WITH", COMPLIES_TEXT), "doc3:0")],
    )
    return store


def test_store_round_trips_entities_and_edges(tmp_path):
    store = _seed_store(tmp_path)
    assert store.entity_count == 4
    assert store.edge_count == 3
    assert store.doc_ids() == {"doc1", "doc2", "doc3"}
    assert store.entity(entity_id("PRODUCT", "Atlas P2"))["name"] == "Atlas P2"


def test_writing_the_same_document_twice_does_not_double_edges(tmp_path):
    store = _seed_store(tmp_path)
    before = store.edge_count
    atlas, auralis = Entity("Atlas P2", "PRODUCT"), Entity("Auralis Dynamics", "COMPANY")
    store.add_document(
        "doc1",
        [(atlas, "doc1:0"), (auralis, "doc1:0")],
        [(Relation(atlas, auralis, "MADE_BY", MADE_BY_TEXT), "doc1:0")],
    )
    assert store.edge_count == before


def test_reingesting_a_document_replaces_what_it_contributed(tmp_path):
    store = _seed_store(tmp_path)
    store.add_document("doc1", [], [])
    assert store.edge_count == 2
    assert "doc1" not in store.doc_ids()


def test_seed_linking_prefers_the_longer_name(tmp_path):
    store = _seed_store(tmp_path)
    names = [hit["name"] for hit in store.find_entities("what does the Atlas P2 comply with")]
    assert names[0] == "Atlas P2"


def test_store_reports_counts_by_type(tmp_path):
    report = _seed_store(tmp_path).stats()
    assert report["backend"] == "sqlite"
    assert report["entities_by_type"]["PRODUCT"] == 1
    assert report["relations_by_type"]["MADE_BY"] == 1


# --------------------------------------------------------------- traversal


def test_two_hops_reach_the_company_but_not_the_standard(tmp_path):
    walk = traverse(_seed_store(tmp_path), "the company headquartered in Munich", hops=2)
    reached = {node["name"] for node in walk.reached}
    assert {"Munich", "Auralis Dynamics", "Atlas P2"} <= reached
    assert "ISO 3691-4:2023" not in reached


def test_three_hops_complete_the_chain(tmp_path):
    walk = traverse(_seed_store(tmp_path), "the company headquartered in Munich", hops=3)
    assert "ISO 3691-4:2023" in {node["name"] for node in walk.reached}
    assert [step.render() for step in walk.steps] == [
        "Auralis Dynamics -[LOCATED_IN]-> Munich",
        "Atlas P2 -[MADE_BY]-> Auralis Dynamics",
        "Atlas P2 -[COMPLIES_WITH]-> ISO 3691-4:2023",
    ]


def test_hops_are_reported_so_the_path_can_be_read(tmp_path):
    walk = traverse(_seed_store(tmp_path), "Munich", hops=3)
    assert [step.hop for step in walk.steps] == [1, 2, 3]
    assert "hop 1" in walk.render_path()


def test_a_question_naming_nothing_in_the_graph_returns_no_seeds(tmp_path):
    walk = traverse(_seed_store(tmp_path), "what is the weather in Antarctica", hops=2)
    assert walk.seeds == []
    assert walk.empty


def test_traversal_collects_the_chunks_behind_the_edges(tmp_path):
    walk = traverse(_seed_store(tmp_path), "Munich", hops=3)
    assert {"doc1:0", "doc2:0", "doc3:0"} <= set(walk.chunk_ids)


# -------------------------------------------------------------------- tool


def _tool(tmp_path):
    store = _seed_store(tmp_path)
    chunks = {
        "doc1:0": Chunk(id="doc1:0", doc_id="doc1", text=MADE_BY_TEXT, title="Atlas",
                        heading="", position=0, source_path="atlas.md"),
        "doc2:0": Chunk(id="doc2:0", doc_id="doc2", text=LOCATED_TEXT, title="Company",
                        heading="", position=0, source_path="company.md"),
        "doc3:0": Chunk(id="doc3:0", doc_id="doc3", text=COMPLIES_TEXT, title="Safety",
                        heading="", position=0, source_path="safety.md"),
    }
    return GraphSearchTool(store, chunks.get, default_hops=3)


def test_graph_search_returns_the_path_and_supporting_chunks(tmp_path):
    result = _tool(tmp_path).run(query="the company headquartered in Munich")
    assert "PATH:" in result.observation
    assert "MADE_BY" in result.observation
    assert result.evidence
    assert all(item.source_type == "graph" for item in result.evidence)
    assert any("ISO 3691-4:2023" in item.text for item in result.evidence)


def test_graph_search_says_so_when_nothing_matches(tmp_path):
    result = _tool(tmp_path).run(query="the weather in Antarctica")
    assert not result.evidence
    assert "No graph entities matched" in result.observation


def test_graph_search_reports_an_empty_graph_instead_of_failing(tmp_path):
    empty = GraphSearchTool(SqliteGraphStore(tmp_path / "empty.sqlite3"), lambda _: None)
    result = empty.run(query="anything")
    assert not result.evidence
    assert "empty" in result.observation


def test_hops_are_clamped_to_something_sane(tmp_path):
    tool = _tool(tmp_path)
    assert "PATH:" in tool.run(query="Munich", hops=99).observation
    assert "PATH:" in tool.run(query="Munich", hops="not a number").observation


# ----------------------------------------------------------------- routing


def test_relational_questions_route_to_graph_search():
    from agentic_rag.llm.mock import _GRAPH_HINTS

    for question in (
        "Which safety standard applies to the robot made by the company headquartered in Munich?",
        "Who makes the Atlas P2?",
        "Which company makes the Atlas P2?",
    ):
        assert any(hint in question.lower() for hint in _GRAPH_HINTS), question


def test_single_hop_lookups_stay_off_the_graph():
    """The routing hints must not divert the existing golden-set questions."""
    from agentic_rag.llm.mock import _GRAPH_HINTS

    for question in (
        "What is the payload capacity of the Atlas P2?",
        "Which safety standard does the Atlas platform comply with?",
        "What does the Scale plan cost per robot per month?",
        "When was Auralis Dynamics founded and where?",
        "How long does a typical Atlas deployment take?",
    ):
        assert not any(hint in question.lower() for hint in _GRAPH_HINTS), question


def test_the_tool_is_hidden_until_the_graph_has_edges(tmp_path):
    from agentic_rag.embeddings.local_hash import HashedTfEmbedder
    from agentic_rag.retrieval.hybrid import HybridSearcher
    from agentic_rag.retrieval.vector_store import VectorStore
    from agentic_rag.tools import build_default_tools

    settings = _settings(tmp_path)
    store = VectorStore(settings.index_path, HashedTfEmbedder(dim=256))
    searcher = HybridSearcher(store, "bm25")
    empty = SqliteGraphStore(tmp_path / "empty.sqlite3")
    assert "graph_search" not in build_default_tools(
        settings, searcher, graph_store=empty, chunk_lookup=lambda _: None
    )
    assert "graph_search" in build_default_tools(
        settings, searcher, graph_store=_seed_store(tmp_path), chunk_lookup=lambda _: None
    )


# ------------------------------------------------------------- end to end


ROOT = Path(__file__).resolve().parents[1]

MULTI_HOP = (
    "Which safety standard applies to the robot made by the company headquartered in Munich?"
)
# Two questions where no single passage holds the answer, so similarity has
# nothing useful to rank. These are the ones that separate the two paths.
# MULTI_HOP above does not: its answer sentence happens to read like the
# question, so BM25 finds it without help.
JOIN_QUESTIONS = (
    ("Where is the company that makes the Atlas P2 headquartered?", "Munich"),
    ("Who makes the robot that complies with ISO 3691-4:2023?", "Auralis Dynamics"),
)


def _ingested(tmp_path, graph: bool):
    """Ingest the sample corpus, then open a fresh pipeline over it.

    The second pipeline matters. The toolset is assembled once at startup,
    so graph_search only appears for a process that starts with the graph
    already populated, which is exactly what `rag ingest` then `rag ask`
    does.
    """
    settings = _settings(tmp_path, graph_hops=3, graph_extraction=graph)
    AgenticRAG(settings).ingest(ROOT / "data" / "sample_docs")
    return AgenticRAG(_settings(tmp_path, graph_hops=3, graph_extraction=graph))


@pytest.fixture(scope="module")
def with_graph(tmp_path_factory):
    return _ingested(tmp_path_factory.mktemp("graph_on"), graph=True)


@pytest.fixture(scope="module")
def without_graph(tmp_path_factory):
    return _ingested(tmp_path_factory.mktemp("graph_off"), graph=False)


def test_a_multi_hop_question_is_answered_through_traversal(with_graph):
    assert "graph_search" in with_graph.tools
    answer = with_graph.ask(MULTI_HOP)
    assert "3691" in answer.text, "the standard three hops away should be found"
    assert any(item.source_type == "graph" for item in answer.evidence)


def test_the_multi_hop_answer_shows_the_path_it_walked(with_graph):
    result = with_graph.tools["graph_search"].run(query=MULTI_HOP, hops=3)
    assert "Auralis Dynamics -[LOCATED_IN]-> Munich" in result.observation
    assert "Atlas P2 -[MADE_BY]-> Auralis Dynamics" in result.observation
    assert "Atlas P2 -[COMPLIES_WITH]-> ISO 3691-4:2023" in result.observation


def test_traversal_retrieves_answers_similarity_search_misses(with_graph, without_graph):
    """The before and after, compared where the difference actually lives.

    Retrieval, not wording. The offline mock writes its answer by quoting
    whichever retrieved sentence overlaps the question most, so answer text
    reflects the mock as much as the retriever. What each path *fetched* is
    the honest comparison: for a question whose answer needs two facts
    joined, traversal returns the passage holding it and similarity does
    not.
    """
    assert "graph_search" not in without_graph.tools
    for question, expected in JOIN_QUESTIONS:
        graph_result = with_graph.tools["graph_search"].run(query=question, hops=3)
        vector_result = without_graph.tools["vector_search"].run(query=question, k=5)
        assert any(expected.lower() in item.text.lower() for item in graph_result.evidence), (
            f"traversal should reach {expected!r} for: {question}"
        )
        assert not any(expected.lower() in item.text.lower() for item in vector_result.evidence), (
            f"similarity search is expected to miss {expected!r} for: {question}"
        )


def test_single_hop_questions_are_unaffected_by_the_graph(with_graph):
    """The graph must not disturb what already worked."""
    answer = with_graph.ask("What is the payload capacity of the Atlas P2?")
    assert "450" in answer.text


# ------------------------------------------------------------ build and ops


def test_graph_building_never_sinks_an_ingest(tmp_path):
    """An extractor that throws costs edges, not documents."""
    rag = AgenticRAG(_settings(tmp_path))

    def exploding(_text):
        raise RuntimeError("extractor failed")

    rag._graph_extractor = exploding
    document = Document(id="d", path="d.md", title="D", text=MADE_BY_TEXT)
    chunks = chunk_document(document, target_chars=400, overlap_chars=0)
    rag.store.add_chunks(chunks)
    rag._build_graph(document.id, chunks)  # must not raise
    assert rag.store.count == len(chunks)


def test_rebuild_works_from_stored_chunks_alone(tmp_path):
    settings = _settings(tmp_path, graph_hops=3)
    rag = AgenticRAG(settings)
    for document in (
        Document(id="atlas", path="atlas.md", title="Atlas P2", text=MADE_BY_TEXT),
        Document(id="safety", path="safety.md", title="Safety", text=COMPLIES_TEXT),
    ):
        rag.store.add_chunks(chunk_document(document, target_chars=400, overlap_chars=0))
    # nothing extracted yet, the graph is built only by the rebuild below
    result = rebuild(settings)
    assert result["status"] == "ok"
    assert result["relations"] >= 2
    assert result["extractor"] == "offline"


def test_rebuild_on_an_empty_index_reports_instead_of_failing(tmp_path):
    result = rebuild(_settings(tmp_path))
    assert result["status"] == "empty"
    assert "ingest" in result["message"]


def test_extraction_can_be_switched_off(tmp_path):
    rag = AgenticRAG(_settings(tmp_path, graph_extraction=False))
    document = Document(id="d", path="d.md", title="D", text=MADE_BY_TEXT)
    chunks = chunk_document(document, target_chars=400, overlap_chars=0)
    rag.store.add_chunks(chunks)
    rag._build_graph(document.id, chunks)
    assert rag.knowledge_graph.edge_count == 0


def test_stats_report_the_backend_and_extractor(tmp_path):
    settings = _settings(tmp_path)
    report = stats(settings)
    assert report["backend"] == "sqlite"
    assert report["extractor"] == "offline"


def test_build_for_chunks_counts_what_it_could_not_read(tmp_path):
    store = SqliteGraphStore(tmp_path / "g.sqlite3")

    def half_broken(text):
        if "Munich" in text:
            raise ValueError("nope")
        return build_extractor(_settings(tmp_path))(text)

    chunks = [
        Chunk(id="c0", doc_id="d", text=MADE_BY_TEXT, title="t", heading="", position=0,
              source_path="a.md"),
        Chunk(id="c1", doc_id="d", text=LOCATED_TEXT, title="t", heading="", position=1,
              source_path="a.md"),
    ]
    written = build_for_chunks(store, half_broken, "d", chunks)
    assert written["chunks_failed"] == 1
    assert store.edge_count >= 1


# ---------------------------------------------------------------- settings


def test_graph_settings_have_working_defaults():
    settings = Settings()
    assert settings.graph_extraction is True
    assert settings.graph_extractor == "auto"
    assert settings.graph_store == "sqlite"
    assert settings.graph_hops == 2


def test_graph_settings_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("GRAPH_EXTRACTION", "off")
    monkeypatch.setenv("GRAPH_EXTRACTOR", "offline")
    monkeypatch.setenv("GRAPH_HOPS", "4")
    monkeypatch.setenv("GRAPH_STORE", "sqlite")
    settings = Settings.from_env()
    assert settings.graph_extraction is False
    assert settings.graph_extractor == "offline"
    assert settings.graph_hops == 4


def test_an_unknown_graph_store_is_rejected_by_name():
    from agentic_rag.kg.store import get_graph_store

    with pytest.raises(ValueError) as caught:
        get_graph_store(Settings(graph_store="mongodb"))
    assert "sqlite" in str(caught.value)


def test_the_graph_lives_beside_the_vector_index(tmp_path):
    settings = _settings(tmp_path)
    assert settings.graph_path.parent == settings.index_path


# ------------------------------------------------- calculator misrouting


def test_identifiers_are_not_read_as_arithmetic():
    """Standard numbers, versions, and part numbers all look like subtraction.

    "ISO 3691-4:2023" used to reach the calculator and come back as 3,687,
    which sent a relational question to entirely the wrong tool.
    """
    from agentic_rag.llm.mock import extract_expression

    for question in (
        "Who makes the robot that complies with ISO 3691-4:2023?",
        "What is ISO 3691-4?",
        "Which safety standard does EN 1175 cover?",
        "Tell me about the P2-450 load deck",
        "Is SOC 2 Type II renewed annually?",
        "What does version 1.2.3-rc1 change?",
        "the 2024-2025 fiscal year",
        "Does it support IPv4-only networks?",
    ):
        assert extract_expression(question) == "", question


def test_real_arithmetic_still_reaches_the_calculator():
    from agentic_rag.llm.mock import extract_expression
    from agentic_rag.tools.structured import safe_eval

    expected = {
        "What is 23 * 649?": 14927.0,
        "what is 1847 * 23": 42481.0,
        "12% of 4000": 480.0,
        "25% of 1,200": 300.0,
        "compute 2+2": 4.0,
        "what is 100 - 25": 75.0,
        "1,200 * 3": 3600.0,
    }
    for question, value in expected.items():
        expression = extract_expression(question)
        assert expression, question
        assert safe_eval(expression) == value, question


def test_a_bracketed_expression_keeps_its_opening_bracket():
    """The pattern starts at a digit, so "(12 + 8) / 4" arrived unbalanced."""
    from agentic_rag.llm.mock import extract_expression
    from agentic_rag.tools.structured import safe_eval

    assert safe_eval(extract_expression("(12 + 8) / 4")) == 5.0


def test_a_standard_number_question_routes_to_the_graph(with_graph):
    """The end of the misrouting bug, checked through the whole pipeline."""
    answer = with_graph.ask("Who makes the robot that complies with ISO 3691-4:2023?")
    actions = [step.action for step in answer.steps if step.action and step.action != "finish"]
    assert actions == ["graph_search"]


def test_an_arithmetic_question_still_routes_to_the_calculator(with_graph):
    answer = with_graph.ask("What is 23 * 649?")
    actions = [step.action for step in answer.steps if step.action and step.action != "finish"]
    assert actions == ["calculator"]
    assert "14,927" in answer.text


def test_an_unknown_extractor_is_named_in_the_error(tmp_path):
    from agentic_rag.kg.extractors import ExtractorError

    with pytest.raises(ExtractorError) as caught:
        build_extractor(_settings(tmp_path, graph_extractor="magic"))
    assert "offline" in str(caught.value)


def test_the_store_can_be_closed(tmp_path):
    store = SqliteGraphStore(tmp_path / "g.sqlite3")
    store.add_document("d", [(Entity("Atlas P2", "PRODUCT"), "c0")], [])
    store.close()


def test_parallel_reads_do_not_trip_over_each_other(tmp_path):
    """Branches run concurrently and share one connection."""
    from concurrent.futures import ThreadPoolExecutor

    store = _seed_store(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: len(traverse(store, "Munich", hops=3).steps), range(8)))
    assert results == [3] * 8


def test_concurrent_reads_and_writes_share_one_connection_safely(tmp_path):
    """Reported from Windows as "bad parameter or other API misuse".

    sqlite3.threadsafety is 3 on Linux but not everywhere, and the implicit
    cursors the Python wrapper creates interleave across threads regardless,
    so the store serialises access itself.
    """
    from concurrent.futures import ThreadPoolExecutor

    store = _seed_store(tmp_path)
    extra = Entity("Lakeshore Industrial Ventures", "COMPANY")

    def read(_):
        for _ in range(15):
            traverse(store, "Munich", hops=3)
            store.find_entities("Atlas P2 Munich")
            store.stats()
        return True

    def write(i):
        for n in range(5):
            store.add_document(f"w{i}-{n}", [(extra, f"c{i}-{n}")], [])
        return True

    with ThreadPoolExecutor(max_workers=6) as pool:
        assert all(list(pool.map(read, range(4))) + list(pool.map(write, range(2))))
    assert traverse(store, "Munich", hops=3).steps


def test_the_pipeline_releases_the_graph_file(tmp_path):
    """Windows cannot delete an open SQLite file, so temp dirs need this."""
    rag = AgenticRAG(_settings(tmp_path))
    rag.close()
    rag.close()  # closing twice must not raise


def test_reset_clears_the_graph_too(tmp_path):
    """A graph left behind by reset points at chunks that no longer exist."""
    from agentic_rag.cli import cmd_reset

    settings = _settings(tmp_path)
    rag = AgenticRAG(settings)
    document = Document(id="d", path="d.md", title="D", text=MADE_BY_TEXT)
    chunks = chunk_document(document, target_chars=400, overlap_chars=0)
    rag.store.add_chunks(chunks)
    rag._build_graph(document.id, chunks)
    assert rag.knowledge_graph.entity_count > 0
    rag.close()

    import argparse
    import os

    os.environ["STORAGE_DIR"] = str(tmp_path)
    os.environ["LLM_PROVIDER"] = "mock"
    os.environ["EMBEDDINGS_PROVIDER"] = "local"
    try:
        assert cmd_reset(argparse.Namespace(yes=True)) == 0
    finally:
        os.environ.pop("STORAGE_DIR", None)
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("EMBEDDINGS_PROVIDER", None)
    assert AgenticRAG(_settings(tmp_path)).knowledge_graph.entity_count == 0


def test_a_document_stops_after_too_many_extraction_failures_in_a_row(tmp_path):
    """Reported live: a document whose chunks kept failing stalled ingest
    for hours, invisibly, because chunks.jsonl only moves once per
    document and this loop had no bound on how long it could keep retrying.
    """
    store = SqliteGraphStore(tmp_path / "g.sqlite3")
    calls = []

    def always_fails(text):
        calls.append(text)
        raise TimeoutError("simulated stuck provider")

    chunks = [
        Chunk(id=f"c{i}", doc_id="d", text=f"chunk {i}", title="t", heading="",
              position=i, source_path="a.md")
        for i in range(50)
    ]
    written = build_for_chunks(store, always_fails, "d", chunks, max_consecutive_failures=5)
    assert len(calls) == 5, "should stop after the cap, not try all 50 chunks"
    assert written["chunks_failed"] == 50
    assert written["stopped_early"] is True


def test_a_success_in_between_resets_the_failure_count(tmp_path):
    """Occasional failures scattered through a document are normal and must
    not trip the same-document circuit breaker meant for a stuck provider."""
    store = SqliteGraphStore(tmp_path / "g.sqlite3")
    calls = {"n": 0}

    def mostly_fails(text):
        calls["n"] += 1
        # fails 4 times, succeeds once, repeat -- never 5 in a row
        if calls["n"] % 5 == 0:
            return build_extractor(_settings(tmp_path))(MADE_BY_TEXT)
        raise RuntimeError("flaky")

    chunks = [
        Chunk(id=f"c{i}", doc_id="d", text=f"chunk {i}", title="t", heading="",
              position=i, source_path="a.md")
        for i in range(20)
    ]
    written = build_for_chunks(store, mostly_fails, "d", chunks, max_consecutive_failures=5)
    assert calls["n"] == 20, "a document that never fails 5 times running must not stop early"
    assert "stopped_early" not in written


def test_the_failure_cap_is_a_setting(tmp_path):
    settings = _settings(tmp_path)
    assert settings.graph_max_consecutive_failures == 5


def test_the_failure_cap_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("GRAPH_MAX_CONSECUTIVE_FAILURES", "2")
    assert Settings.from_env().graph_max_consecutive_failures == 2


def test_business_phrases_are_not_mistaken_for_places(tmp_path):
    """Reported from a real corpus of financial reports.

    Bare "in", "at", and "from" turned any capitalized phrase into a
    location, producing edges like Siemens Healthineers LOCATED_IN
    "Advanced Therapies" (a segment), "China Revenue" (a table header),
    and "Barclays" (an analyst's employer).
    """
    extract = build_extractor(_settings(tmp_path, graph_extractor="offline"))
    for sentence in (
        "Accelerated growth in Advanced Therapies driven by all new products.",
        "Structural market rebasing in China Revenue dilution due to volumes.",
        "Marc Koebernick Siemens Healthineers I think these are meaningful at Barclays.",
        "Revenue in the Imaging segment rose by 2.3% in the third quarter.",
    ):
        places = [e.name for e in extract(sentence).entities if e.type == "LOCATION"]
        assert not places, f"{sentence!r} produced {places}"


def test_real_places_are_still_found(tmp_path):
    extract = build_extractor(_settings(tmp_path, graph_extractor="offline"))
    for sentence, expected in (
        ("Auralis Dynamics was founded in 2019 in Munich, Germany.", "Munich"),
        ("Siemens Healthineers AG is headquartered in Forchheim, Germany.", "Forchheim"),
        ("SAP SE is based in Walldorf.", "Walldorf"),
    ):
        places = [e.name for e in extract(sentence).entities if e.type == "LOCATION"]
        assert expected in places, f"{sentence!r} produced {places}"
