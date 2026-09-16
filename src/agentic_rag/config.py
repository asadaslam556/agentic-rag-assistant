"""Environment-driven configuration.

Every setting has a default that works, so the project runs before you
configure anything:
LLM_PROVIDER=auto uses a local Ollama server when one is running and
falls back to the deterministic offline mock otherwise, so tests and CI
never need a model or a network. A `.env` file
in the working directory is loaded automatically when python-dotenv is
installed. See `.env.example` for the full reference.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # optional dependency; the project works without it
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


ROLES = ("plan", "decompose", "rewrite", "synthesize", "verify", "judge", "vision")


def _role_models() -> dict:
    """Per-role overrides, read as LLM_MODEL_PLAN, LLM_MODEL_VISION and so on."""
    found = {}
    for role in ROLES:
        value = _env(f"LLM_MODEL_{role.upper()}")
        if value:
            found[role] = value
    return found


def _env_bool(name: str, default: bool) -> bool:
    """A blank or unset variable keeps the default; anything else is read
    the way people write flags in a shell."""
    raw = _env(name).strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(
            f"{name} must be an integer, got {raw!r}. Fix it in .env or unset it "
            f"to use the default ({default})."
        ) from None


def _env_float_or_none(name: str, default: float | None) -> float | None:
    """Like _env_float, but an explicitly blank value means "leave it out".

    Some gateway-hosted models reject a temperature parameter outright, and
    no value satisfies them. Setting LLM_TEMPERATURE= (blank) drops the
    field from the request instead of sending a number.
    """
    if name in os.environ and not os.environ[name].strip():
        return None
    raw = _env(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(
            f"{name} must be a number or blank, got {raw!r}. Fix it in .env, "
            "leave it blank to omit temperature, or unset it for the default."
        ) from None


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(
            f"{name} must be a number, got {raw!r}. Fix it in .env or unset it "
            f"to use the default ({default})."
        ) from None


@dataclass
class Settings:
    # LLM
    llm_provider: str = "auto"  # auto | ollama | mock | openai | azure | anthropic | openai_compatible
    llm_model: str = ""  # one model name for whichever provider is active
    # optional two-tier routing: cheap models for the mechanical roles,
    # a stronger one for writing and checking the answer
    llm_model_fast: str = ""
    llm_model_deep: str = ""
    llm_role_models: dict = field(default_factory=dict)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""  # empty = pick the best installed model automatically
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-06-01"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_model: str = "claude-sonnet-4-6"
    llm_extra_headers: dict = field(default_factory=dict)
    llm_temperature: float | None = 0.1  # None omits the field from requests
    request_timeout: int = 60

    # Embeddings
    embeddings_provider: str = "local"  # local | sbert | multilingual | openai
    sbert_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    # used when EMBEDDINGS_PROVIDER=multilingual. Any sentence-transformers
    # model works; the default is small enough to run on a laptop CPU
    multilingual_embedding_model: str = "intfloat/multilingual-e5-small"
    openai_embedding_model: str = "text-embedding-3-small"
    local_embedding_dim: int = 768

    # Language handling
    # Answers follow the language of the question. Set ANSWER_LANGUAGE to a
    # code like en or de to pin every answer to one language instead.
    answer_language: str = "auto"

    # Web search
    search_provider: str = "ddgs"  # ddgs | tavily | fixture | none
    tavily_api_key: str = ""
    web_fixtures_path: str = "data/web_fixtures.json"

    # Structured data
    catalog_path: str = "data/structured/catalog.json"

    # Retrieval / chunking
    retrieval_k: int = 5
    retrieval_mode: str = "hybrid"  # hybrid | vector | bm25
    pdf_vision: str = "auto"  # off | auto | on
    visual_retriever: str = "description"  # description | colpali
    colpali_model: str = ""
    colpali_device: str = ""  # blank picks cuda when available, else cpu
    colpali_batch_size: int = 2
    vision_context_pages: int = 2  # page images attached when writing an answer
    vision_max_pages: int = 20
    vision_scale: float = 2.0  # render scale, roughly 144 dpi at 2.0
    chunk_strategy: str = "structure"  # structure | length
    chunk_target_chars: int = 900
    chunk_overlap_chars: int = 150
    context_token_budget: int = 2200

    # Agent / verification
    max_agent_steps: int = 6
    max_branches: int = 3  # 1 disables decomposition entirely
    max_total_agent_steps: int = 12  # shared across all branches of one question
    max_refine_attempts: int = 1
    min_groundedness: float = 0.7
    verifier_mode: str = "auto"  # auto | llm | lexical

    # Storage
    storage_dir: str = "storage"

    # Knowledge graph
    # Extraction runs at ingest; turning it off leaves the rest of ingest alone.
    graph_extraction: bool = True
    # offline | llm | auto. auto stays offline unless LLM_PROVIDER was set
    # deliberately, because the LLM extractor costs one call per chunk.
    graph_extractor: str = "auto"
    graph_store: str = "sqlite"  # sqlite | neo4j
    graph_max_entities_per_chunk: int = 12
    # room for the JSON plus whatever a thinking model spends before it
    graph_extract_max_tokens: int = 3000
    # give up on the rest of a document after this many extraction calls in
    # a row fail, rather than retrying every remaining chunk against a
    # provider that is not responding
    graph_max_consecutive_failures: int = 5
    graph_hops: int = 2
    graph_alias_path: str = "data/graph_aliases.json"
    neo4j_uri: str = ""
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = ""
    api_auth_token: str = ""  # empty = open local API; set to require Bearer auth
    upload_max_mb: int = 25

    @property
    def storage_path(self) -> Path:
        p = Path(self.storage_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def index_path(self) -> Path:
        p = self.storage_path / "index"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def omit_temperature(self) -> bool:
        """True when LLM_TEMPERATURE is blank, meaning no request carries the
        field at all.

        Some roles (verifying, judging, splitting, rewriting) want a fixed
        0.0 so their output cannot drift, and they pass it explicitly. A
        model that rejects the parameter rejects 0.0 too, so the clients
        check this before adding it and those roles do not have to know.
        """
        return self.llm_temperature is None

    @property
    def graph_path(self) -> Path:
        """The graph file sits beside the vector index, so one storage
        directory holds everything a corpus produced."""
        return self.index_path / "graph.sqlite3"

    @classmethod
    def from_env(cls) -> Settings:
        headers: dict = {}
        raw_headers = _env("LLM_EXTRA_HEADERS")
        if raw_headers:
            try:
                headers = json.loads(raw_headers)
            except json.JSONDecodeError:
                headers = {}
        return cls(
            llm_provider=_env("LLM_PROVIDER", "auto").lower(),
            llm_model=_env("LLM_MODEL"),
            llm_model_fast=_env("LLM_MODEL_FAST"),
            llm_model_deep=_env("LLM_MODEL_DEEP"),
            llm_role_models=_role_models(),
            ollama_base_url=_env("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
            ollama_model=_env("OLLAMA_MODEL"),
            openai_api_key=_env("OPENAI_API_KEY"),
            openai_base_url=_env("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            openai_model=_env("OPENAI_MODEL", "gpt-4o-mini"),
            azure_openai_endpoint=_env("AZURE_OPENAI_ENDPOINT").rstrip("/"),
            azure_openai_deployment=_env("AZURE_OPENAI_DEPLOYMENT"),
            azure_openai_api_key=_env("AZURE_OPENAI_API_KEY"),
            azure_openai_api_version=_env("AZURE_OPENAI_API_VERSION", "2024-06-01"),
            deepseek_api_key=_env("DEEPSEEK_API_KEY"),
            deepseek_base_url=_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            deepseek_model=_env("DEEPSEEK_MODEL", "deepseek-chat"),
            anthropic_api_key=_env("ANTHROPIC_API_KEY"),
            anthropic_base_url=_env("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/"),
            anthropic_model=_env("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            llm_extra_headers=headers,
            llm_temperature=_env_float_or_none("LLM_TEMPERATURE", 0.1),
            request_timeout=_env_int("REQUEST_TIMEOUT", 60),
            embeddings_provider=_env("EMBEDDINGS_PROVIDER", "local").lower(),
            sbert_model=_env("SBERT_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
            multilingual_embedding_model=_env(
                "MULTILINGUAL_EMBEDDING_MODEL", "intfloat/multilingual-e5-small"
            ),
            openai_embedding_model=_env("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
            answer_language=_env("ANSWER_LANGUAGE", "auto").lower(),
            search_provider=_env("SEARCH_PROVIDER", "ddgs").lower(),
            tavily_api_key=_env("TAVILY_API_KEY"),
            web_fixtures_path=_env("WEB_FIXTURES_PATH", "data/web_fixtures.json"),
            catalog_path=_env("CATALOG_PATH", "data/structured/catalog.json"),
            retrieval_k=_env_int("RETRIEVAL_K", 5),
            retrieval_mode=_env("RETRIEVAL_MODE", "hybrid").lower(),
            pdf_vision=_env("PDF_VISION", "auto").lower(),
            visual_retriever=_env("VISUAL_RETRIEVER", "description").lower(),
            colpali_model=_env("COLPALI_MODEL"),
            colpali_device=_env("COLPALI_DEVICE"),
            colpali_batch_size=_env_int("COLPALI_BATCH_SIZE", 2),
            vision_context_pages=_env_int("VISION_CONTEXT_PAGES", 2),
            vision_max_pages=_env_int("VISION_MAX_PAGES", 20),
            vision_scale=_env_float("VISION_SCALE", 2.0),
            chunk_strategy=_env("CHUNK_STRATEGY", "structure").lower(),
            chunk_target_chars=_env_int("CHUNK_TARGET_CHARS", 900),
            chunk_overlap_chars=_env_int("CHUNK_OVERLAP_CHARS", 150),
            context_token_budget=_env_int("CONTEXT_TOKEN_BUDGET", 2200),
            max_agent_steps=_env_int("MAX_AGENT_STEPS", 6),
            max_branches=_env_int("MAX_BRANCHES", 3),
            max_total_agent_steps=_env_int("MAX_TOTAL_AGENT_STEPS", 12),
            max_refine_attempts=_env_int("MAX_REFINE_ATTEMPTS", 1),
            min_groundedness=_env_float("MIN_GROUNDEDNESS", 0.7),
            verifier_mode=_env("VERIFIER_MODE", "auto").lower(),
            storage_dir=_env("STORAGE_DIR", "storage"),
            graph_extraction=_env_bool("GRAPH_EXTRACTION", True),
            graph_extractor=_env("GRAPH_EXTRACTOR", "auto").lower(),
            graph_store=_env("GRAPH_STORE", "sqlite").lower(),
            graph_max_entities_per_chunk=_env_int("GRAPH_MAX_ENTITIES_PER_CHUNK", 12),
            graph_extract_max_tokens=_env_int("GRAPH_EXTRACT_MAX_TOKENS", 3000),
            graph_max_consecutive_failures=_env_int("GRAPH_MAX_CONSECUTIVE_FAILURES", 5),
            graph_hops=_env_int("GRAPH_HOPS", 2),
            graph_alias_path=_env("GRAPH_ALIAS_PATH", "data/graph_aliases.json"),
            neo4j_uri=_env("NEO4J_URI"),
            neo4j_user=_env("NEO4J_USER", "neo4j"),
            neo4j_password=_env("NEO4J_PASSWORD"),
            neo4j_database=_env("NEO4J_DATABASE"),
            api_auth_token=_env("API_AUTH_TOKEN"),
            upload_max_mb=_env_int("UPLOAD_MAX_MB", 25),
        )
