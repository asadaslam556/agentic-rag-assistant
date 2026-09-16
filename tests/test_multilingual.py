"""Multilingual tokenisation, language detection, and answer language.

Everything here runs offline with the deterministic mock and the local
hashed embedder, in line with the rest of the suite.
"""

import re

from agentic_rag.agent.prompts import SYNTHESIZE_SYSTEM, build_synthesis_prompt
from agentic_rag.config import Settings
from agentic_rag.core.lang import (
    detect_language,
    detect_language_detailed,
    language_name,
    stopwords_for,
)
from agentic_rag.core.textutils import content_tokens, split_sentences, tokenize
from agentic_rag.core.types import Document, Evidence
from agentic_rag.embeddings.local_hash import HashedTfEmbedder
from agentic_rag.ingestion.chunking import chunk_document
from agentic_rag.pipeline import AgenticRAG
from agentic_rag.retrieval.bm25 import BM25Index
from agentic_rag.retrieval.hybrid import HybridSearcher
from agentic_rag.retrieval.reindex import reindex
from agentic_rag.retrieval.vector_store import VectorStore

GERMAN = "Die Traglast der Atlas P2 betraegt bis zu 450 kg. Die Plattform ist nach der Sicherheitsnorm ISO 3691-4:2023 zertifiziert."
ARABIC = "قدرة الحمولة لمنصة أطلس بي 2 تصل إلى 450 كيلوغرام. منصة أطلس معتمدة وفق معيار السلامة."
CHINESE = "阿特拉斯平台的负载能力为450公斤。阿特拉斯平台通过了安全标准认证。"
URDU = "اٹلس پی 2 کی صلاحیت 450 کلوگرام ہے۔ اٹلس پلیٹ فارم حفاظتی معیار کے مطابق تصدیق شدہ ہے۔"


# --------------------------------------------------------------- tokenisation


def test_english_tokenisation_is_unchanged_by_the_unicode_rules():
    """The old rule, kept here so an English regression cannot slip through."""
    old_stopwords = frozenset(
        """
        a an and are as at be but by can could did do does for from had has have how
        i if in into is it its me my not of on or our per should so than that the
        their there these they this to us was we were what when where which who why
        will with would you your about
        """.split()
    )

    def old_tokenize(text):
        found = re.findall(r"[a-z0-9][a-z0-9\-]*", text.lower())
        return [t for t in found if t not in old_stopwords and len(t) > 1]

    samples = [
        "What is the payload capacity of the Atlas P2?",
        "The Atlas platform is certified to the ISO 3691-4:2023 safety standard.",
        "state-of-the-art co-operate re-index",
        "SKU IM-450 UM-12 under_score_words",
        "EUR 649 per robot per month, billed annually.",
        "",
    ]
    for sample in samples:
        assert tokenize(sample) == old_tokenize(sample), sample


def test_german_keeps_umlauts_instead_of_splitting_words():
    tokens = tokenize("Die Weiße Straße hat große Türen und Grüße für Fußgänger.")
    assert "straße" in tokens
    assert "fußgänger" in tokens
    assert "türen" in tokens
    # the old rule chopped these into fragments
    assert "stra" not in tokens
    assert "fu" not in tokens


def test_arabic_text_produces_word_tokens():
    tokens = tokenize(ARABIC)
    assert tokens, "Arabic must not tokenise to nothing"
    assert "معيار" in tokens
    assert "السلامة" in tokens


def test_urdu_text_produces_word_tokens():
    tokens = tokenize(URDU)
    assert tokens, "Urdu must not tokenise to nothing"
    assert "اٹلس" in tokens
    assert "حفاظتی" in tokens


def test_chinese_is_segmented_into_bigrams():
    tokens = tokenize("阿特拉斯平台的安全标准")
    assert tokens, "Chinese has no spaces, so it needs segmenting"
    assert all(len(t) <= 2 for t in tokens)
    assert "平台" in tokens
    assert "安全" in tokens
    # the same function runs at index time and query time, so bigrams line up
    assert set(tokenize("安全标准")) & set(tokens)


def test_mixed_script_token_splits_at_the_script_boundary():
    tokens = tokenize("atlas平台 ISO-3691")
    assert "atlas" in tokens
    assert "平台" in tokens
    assert "iso-3691" in tokens


def test_non_latin_sentences_split_on_their_own_full_stops():
    assert len(split_sentences(CHINESE)) == 2
    assert len(split_sentences(URDU)) == 2


# ------------------------------------------------------------------ stopwords


def test_stopwords_are_filtered_per_language():
    # German articles go, German nouns stay
    german = tokenize("Der Roboter und die Plattform sind in der Halle")
    assert "der" not in german
    assert "und" not in german
    assert "roboter" in german
    assert "plattform" in german

    # Arabic function words go
    arabic = tokenize("ما هو معيار السلامة لمنصة أطلس")
    assert "ما" not in arabic
    assert "هو" not in arabic
    assert "معيار" in arabic

    # Urdu function words go
    urdu = tokenize("اٹلس پلیٹ فارم کا حفاظتی معیار کیا ہے")
    assert "کا" not in urdu
    assert "کیا" not in urdu
    assert "حفاظتی" in urdu

    # Chinese: a bigram made only of function characters is dropped
    assert "是什" not in tokenize("安全标准是什么")
    assert "安全" in tokenize("安全标准是什么")


def test_english_stopwords_still_apply_to_english():
    tokens = tokenize("What is the capacity of the platform")
    assert "the" not in tokens
    assert "is" not in tokens
    assert "capacity" in tokens


def test_stopwords_for_falls_back_to_english():
    assert stopwords_for("en") is stopwords_for("does-not-exist")
    assert "the" in stopwords_for("pt")
    assert "der" in stopwords_for("de")


# ----------------------------------------------------------------- detection


def test_language_detection_across_the_supported_languages():
    assert detect_language("Wie hoch ist die Traglast des Atlas P2?") == "de"
    assert detect_language("Welche Sicherheitsnorm erfüllt die Plattform?") == "de"
    assert detect_language("What is the payload capacity of the Atlas P2?") == "en"
    assert detect_language("ما هو معيار السلامة لمنصة أطلس؟") == "ar"
    assert detect_language("阿特拉斯平台的安全标准是什么？") == "zh"
    assert detect_language("اٹلس پلیٹ فارم کا حفاظتی معیار کیا ہے؟") == "ur"


def test_urdu_is_told_apart_from_arabic_despite_the_shared_script():
    assert detect_language("روبوٹ کی صلاحیت کیا ہے؟") == "ur"
    assert detect_language("ما هي سياسة الأمان الخاصة بالمنصة؟") == "ar"


def test_short_or_empty_queries_fall_back_to_english():
    for text in ("", "   ", "Atlas P2", "450", "SKU IM-450 UM-12"):
        assert detect_language(text) == "en", text
    assert detect_language_detailed("Atlas P2").confidence == 0.0


def test_low_confidence_can_be_rejected_with_a_threshold():
    # a bare noun phrase carries no signal, so a caller asking for
    # confidence gets English rather than a guess
    assert detect_language("Atlas P2", min_confidence=0.5) == "en"
    assert detect_language("Die Roboter bewegen Paletten zwischen den Lagerzonen", 0.5) == "de"


def test_mixed_language_queries_use_the_dominant_language():
    assert detect_language("Was ist die Traglast und der Preis für den Atlas P2?") == "de"
    assert detect_language("What is the Traglast of the Atlas P2 robot?") == "en"
    assert detect_language("阿特拉斯平台的安全标准 Atlas platform") == "zh"


def test_language_names_are_available_for_the_prompt():
    assert language_name("de") == "German"
    assert language_name("zh") == "Chinese"
    assert language_name("unknown") == "English"


# -------------------------------------------------------- retrieval end to end


def _multilingual_store(tmp_path):
    documents = [
        Document(id="de", path="de.md", title="Atlas DE", text=GERMAN),
        Document(id="ar", path="ar.md", title="Atlas AR", text=ARABIC),
        Document(id="zh", path="zh.md", title="Atlas ZH", text=CHINESE),
        Document(id="ur", path="ur.md", title="Atlas UR", text=URDU),
        Document(
            id="en",
            path="en.md",
            title="Atlas EN",
            text="Payload capacity: the Atlas P2 carries up to 450 kg on its load deck.",
        ),
    ]
    store = VectorStore(tmp_path, HashedTfEmbedder(dim=256))
    for document in documents:
        store.add_chunks(chunk_document(document, target_chars=400, overlap_chars=0))
    return store


def test_bm25_returns_hits_for_every_supported_language(tmp_path):
    index = BM25Index(_multilingual_store(tmp_path).chunks())
    for query in (
        "Wie hoch ist die Traglast der Atlas P2?",
        "ما هي قدرة الحمولة لمنصة أطلس؟",
        "阿特拉斯平台的负载能力",
        "اٹلس کی صلاحیت کیا ہے؟",
        "What is the payload capacity?",
    ):
        assert index.search(query, k=3), f"no BM25 hits for: {query}"


def test_german_and_arabic_queries_reach_the_right_document(tmp_path):
    store = _multilingual_store(tmp_path)
    searcher = HybridSearcher(store, "bm25")
    assert searcher.search("Traglast Sicherheitsnorm", k=1)[0][0].doc_id == "de"
    assert searcher.search("قدرة الحمولة معيار السلامة", k=1)[0][0].doc_id == "ar"


def test_local_embedder_sees_non_latin_text():
    """The hashed embedder had its own ASCII-only tokeniser and produced
    all-zero vectors for non-Latin input."""
    embedder = HashedTfEmbedder(dim=256)
    vectors = embedder.embed_texts([ARABIC, CHINESE, URDU, GERMAN])
    for row, label in zip(vectors, ("arabic", "chinese", "urdu", "german"), strict=True):
        assert abs(row).sum() > 0.0, f"{label} embedded to an empty vector"


# -------------------------------------------------------------- answer language


def test_synthesis_prompt_names_a_non_english_answer_language():
    evidence = [Evidence("e1", "Doc", "vector", "ref.md", "Some text", "vector_search")]
    prompt = build_synthesis_prompt("Wie hoch ist die Traglast?", evidence, language="de")
    assert "ANSWER LANGUAGE: German" in prompt


def test_english_synthesis_prompt_is_left_exactly_as_it_was():
    evidence = [Evidence("e1", "Doc", "vector", "ref.md", "Some text", "vector_search")]
    question = "What is the payload capacity?"
    assert build_synthesis_prompt(question, evidence, language="en") == build_synthesis_prompt(
        question, evidence
    )
    assert "ANSWER LANGUAGE" not in build_synthesis_prompt(question, evidence, language="en")


def test_the_system_prompt_carries_the_same_language_rule():
    assert "same language as the question" in SYNTHESIZE_SYSTEM
    assert "mostly written in" in SYNTHESIZE_SYSTEM  # the mixed-language case


def _pipeline(tmp_path):
    settings = Settings(
        llm_provider="mock",
        embeddings_provider="local",
        local_embedding_dim=256,
        storage_dir=str(tmp_path),
        search_provider="none",
        max_branches=1,
    )
    rag = AgenticRAG(settings)
    for document in (
        Document(id="de", path="de.md", title="Atlas DE", text=GERMAN),
        Document(
            id="en",
            path="en.md",
            title="Atlas EN",
            text="Every Atlas P2 ships with a 24-month hardware warranty covering spare parts.",
        ),
    ):
        rag.store.add_chunks(chunk_document(document, target_chars=400, overlap_chars=0))
    return rag


def test_pipeline_resolves_the_answer_language_from_the_question(tmp_path):
    rag = _pipeline(tmp_path)
    assert rag._answer_language("Wie hoch ist die Traglast der Atlas P2?") == "de"
    assert rag._answer_language("What is the payload capacity?") == "en"


def test_answer_language_setting_pins_every_answer(tmp_path):
    rag = _pipeline(tmp_path)
    rag.settings.answer_language = "de"
    assert rag._answer_language("What is the payload capacity?") == "de"


def test_a_german_question_gets_a_german_answer(tmp_path):
    """End to end with the offline mock.

    The mock answers by quoting the sentences it retrieved rather than
    writing new ones, so what this shows is that a German question routes to
    German evidence and comes back in German. Instructing a real model to
    write in the question language is the job of the prompt rule, which is
    checked separately above.
    """
    rag = _pipeline(tmp_path)
    answer = rag.ask("Wie hoch ist die Traglast der Atlas P2?")
    assert detect_language(answer.text) == "de"
    assert "450" in answer.text


def test_an_english_question_still_gets_an_english_answer(tmp_path):
    rag = _pipeline(tmp_path)
    answer = rag.ask("What hardware warranty does the Atlas P2 ship with?")
    assert detect_language(answer.text) == "en"
    assert "24-month" in answer.text


# ------------------------------------------------------------------- settings


def test_multilingual_settings_have_backwards_compatible_defaults():
    settings = Settings()
    assert settings.embeddings_provider == "local"
    assert settings.sbert_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert settings.multilingual_embedding_model == "intfloat/multilingual-e5-small"
    assert settings.answer_language == "auto"


def test_the_multilingual_model_is_configurable_from_the_environment(monkeypatch):
    monkeypatch.setenv("MULTILINGUAL_EMBEDDING_MODEL", "intfloat/multilingual-e5-base")
    monkeypatch.setenv("ANSWER_LANGUAGE", "de")
    settings = Settings.from_env()
    assert settings.multilingual_embedding_model == "intfloat/multilingual-e5-base"
    assert settings.answer_language == "de"


def test_unknown_embeddings_provider_mentions_the_multilingual_option():
    from agentic_rag.embeddings import get_embedder

    try:
        get_embedder(Settings(embeddings_provider="nope"))
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "multilingual" in str(exc)


# -------------------------------------------------------------------- reindex


def test_reindex_rebuilds_the_index_and_keeps_every_document(tmp_path):
    settings = Settings(
        llm_provider="mock",
        embeddings_provider="local",
        local_embedding_dim=256,
        storage_dir=str(tmp_path),
    )
    store = VectorStore(settings.index_path, HashedTfEmbedder(dim=256))
    store.add_chunks(chunk_document(Document(id="de", path="de.md", title="DE", text=GERMAN)))
    before = store.count

    result = reindex(settings)
    assert result["status"] == "ok"
    assert result["chunks"] == before
    assert result["documents"] == 1
    assert result["bm25_terms"] > 0
    assert (settings.index_path / "chunks.jsonl.bak").exists()

    rebuilt = VectorStore(settings.index_path, HashedTfEmbedder(dim=256))
    assert rebuilt.count == before
    assert BM25Index(rebuilt.chunks()).search("Traglast Sicherheitsnorm", k=1)


def test_reindex_recovers_an_index_built_by_a_different_embedder(tmp_path):
    """The store refuses a manifest from another embedder, which is exactly
    what happens when EMBEDDINGS_PROVIDER changes. Re-indexing is the way out."""
    import json

    settings = Settings(
        llm_provider="mock",
        embeddings_provider="local",
        local_embedding_dim=256,
        storage_dir=str(tmp_path),
    )
    store = VectorStore(settings.index_path, HashedTfEmbedder(dim=256))
    store.add_chunks(chunk_document(Document(id="de", path="de.md", title="DE", text=GERMAN)))

    manifest_path = settings.index_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["embedder"] = "multilingual:intfloat/multilingual-e5-small"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    try:
        VectorStore(settings.index_path, HashedTfEmbedder(dim=256))
        raise AssertionError("expected the embedder guard to fire")
    except RuntimeError as exc:
        assert "re-ingest" in str(exc)

    result = reindex(settings)
    assert result["status"] == "ok"
    assert result["previous_embedder"] == "multilingual:intfloat/multilingual-e5-small"
    assert VectorStore(settings.index_path, HashedTfEmbedder(dim=256)).count == result["chunks"]


def test_reindex_on_an_empty_index_reports_instead_of_failing(tmp_path):
    settings = Settings(storage_dir=str(tmp_path), embeddings_provider="local")
    result = reindex(settings)
    assert result["status"] == "empty"
    assert "ingest" in result["message"]


# --------------------------------------------------------------- content_tokens


def test_content_tokens_accepts_an_explicit_language():
    # forcing English keeps German articles, which proves the language
    # argument is what selects the stopword list
    assert "der" in content_tokens("Der Roboter und die Plattform", language="en")
    assert "der" not in content_tokens("Der Roboter und die Plattform", language="de")


# ------------------------------------------------------------- CJK spacing


def test_pdf_spaced_chinese_matches_typed_chinese():
    """PDF text extraction puts a space between every Han character.

    Left alone, the index sees single characters while a typed query still
    produces bigrams, so the two sides never match and a Chinese PDF is
    effectively unsearchable.
    """
    from_pdf = "人 人 生 而 自 由, 在 尊 严 和 权 利 上 一 律 平 等。"
    typed = "人人生而自由，在尊严和权利上一律平等。"
    assert tokenize(from_pdf) == tokenize(typed)
    assert "自由" in tokenize(from_pdf)


def test_closing_cjk_gaps_leaves_other_scripts_alone():
    assert tokenize("the atlas p2 platform") == ["atlas", "p2", "platform"]
    # spacing between Arabic words is real word spacing, not an extraction artifact
    assert len(tokenize("معيار السلامة لمنصة أطلس")) == 4


def test_mixed_latin_and_spaced_cjk_still_splits_at_the_boundary():
    tokens = tokenize("Atlas 平 台 ISO-3691")
    assert "atlas" in tokens
    assert "平台" in tokens
    assert "iso-3691" in tokens
