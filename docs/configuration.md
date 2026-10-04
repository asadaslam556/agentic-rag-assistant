# Configuration

[![Ollama](https://img.shields.io/badge/Ollama-default-000000?logo=ollama&logoColor=white)](https://ollama.com)
[![Claude](https://img.shields.io/badge/Claude-D97757?logo=anthropic&logoColor=white)](https://www.anthropic.com)
[![OpenAI](https://img.shields.io/badge/OpenAI-412991?logo=openai&logoColor=white)](https://platform.openai.com)
[![DeepSeek](https://img.shields.io/badge/DeepSeek-4D6BFE?logo=deepseek&logoColor=white)](https://www.deepseek.com)
[![sentence-transformers](https://img.shields.io/badge/sentence--transformers-optional-FFD21E?logo=huggingface&logoColor=black)](https://www.sbert.net)
[![Neo4j](https://img.shields.io/badge/Neo4j-optional-4581C3?logo=neo4j&logoColor=white)](#knowledge-graph)

Every setting is an environment variable, read once by `Settings.from_env()` in
`src/agentic_rag/config.py`. Copy `.env.example` to `.env` (it is gitignored) or export the variables
in your shell. A blank or unset variable keeps the default shown here.

Nothing needs configuring for a first run: with no settings at all, `LLM_PROVIDER=auto` uses a local
Ollama if one answers and the offline mock otherwise.

## Model

| Variable | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `auto` | `auto`, `ollama`, `anthropic`, `openai`, `azure`, `deepseek`, `openai_compatible`, `mock`. See [Models](architecture.md#models-and-providers) |
| `LLM_MODEL` | blank | One model name for whichever provider is active; wins over the provider settings below |
| `LLM_MODEL_FAST`, `LLM_MODEL_DEEP` | blank | Two-tier routing by role |
| `LLM_MODEL_<ROLE>` | blank | Pins one role: `PLAN`, `DECOMPOSE`, `REWRITE`, `SYNTHESIZE`, `VERIFY`, `JUDGE`, `VISION` |
| `LLM_TEMPERATURE` | `0.1` | Blank leaves the field out for models that reject it |
| `LLM_EXTRA_HEADERS` | blank | JSON object of extra request headers, for gateways |
| `REQUEST_TIMEOUT` | `60` | Seconds per model request |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | |
| `OLLAMA_MODEL` | blank | Blank auto-picks from the installed models |
| `ANTHROPIC_API_KEY` | blank | `<YOUR_API_KEY>` |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | Private or gateway endpoints |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | |
| `OPENAI_API_KEY` | blank | Required for api.openai.com |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Also used by `openai_compatible` |
| `OPENAI_MODEL` | `gpt-4o-mini` | |
| `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_KEY` | blank | |
| `AZURE_OPENAI_API_VERSION` | `2024-06-01` | |
| `DEEPSEEK_API_KEY` | blank | |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | |
| `DEEPSEEK_MODEL` | `deepseek-flash` | |

## Embeddings and retrieval

| Variable | Default | Notes |
|---|---|---|
| `EMBEDDINGS_PROVIDER` | `local` | `local` (hashed, no download), `sbert`, `multilingual`, `openai`. Changing it needs `rag reindex` |
| `SBERT_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | For `sbert`, needs the `[sbert]` extra |
| `MULTILINGUAL_EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | |
| `RETRIEVAL_MODE` | `hybrid` | `hybrid`, `vector`, `bm25` |
| `RETRIEVAL_K` | `5` | Results per search |
| `RERANKER` | `none` | `cross-encoder` needs the `[rerank]` extra |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | |
| `CONTEXT_TOKEN_BUDGET` | `2200` | Tokens of sources packed for synthesis |
| `ANSWER_LANGUAGE` | `auto` | `auto` answers in the question's language, or a language code |

## Ingestion and PDFs

| Variable | Default | Notes |
|---|---|---|
| `CHUNK_STRATEGY` | `structure` | `structure` or `length` |
| `CHUNK_TARGET_CHARS` | `900` | |
| `CHUNK_OVERLAP_CHARS` | `150` | |
| `PDF_VISION` | `auto` | `off`, `auto`, `on`. Needs the `[vision]` extra and a vision-capable model |
| `VISUAL_RETRIEVER` | `description` | `description` or `colpali` (needs the `[colpali]` extra) |
| `COLPALI_MODEL` | blank | Blank uses colSmol |
| `COLPALI_DEVICE` | blank | For example `cpu` or `cuda` |
| `COLPALI_BATCH_SIZE` | `2` | |
| `VISION_MAX_PAGES` | `20` | Pages rendered per PDF |
| `VISION_SCALE` | `2.0` | Render resolution |
| `VISION_CONTEXT_PAGES` | `2` | Page images attached to a synthesis prompt |

## Agent, orchestration, and verification

| Variable | Default | Notes |
|---|---|---|
| `MAX_AGENT_STEPS` | `6` | Steps per branch |
| `MAX_BRANCHES` | `3` | Parallel sub-questions; `1` turns splitting off |
| `MAX_TOTAL_AGENT_STEPS` | `12` | Tool calls across all branches of one question |
| `MAX_REFINE_ATTEMPTS` | `1` | Redrafts after a failed check |
| `MIN_GROUNDEDNESS` | `0.7` | Pass threshold, together with citation coverage of at least 0.5 |
| `VERIFIER_MODE` | `auto` | `auto` (lexical for the mock, model otherwise), `lexical`, `llm` |

## Tools and data

| Variable | Default | Notes |
|---|---|---|
| `SEARCH_PROVIDER` | `ddgs` | `ddgs` (keyless DuckDuckGo), `tavily`, `fixture` (offline), `none` |
| `TAVILY_API_KEY` | blank | For `tavily` |
| `WEB_FIXTURES_PATH` | `data/web_fixtures.json` | For `fixture` |
| `CATALOG_PATH` | `data/structured/catalog.json` | The `knowledge_base` tool |
| `SQL_DATABASE_PATH` | `data/structured/sales.sql` | `.sql` script or SQLite file; blank turns `sql_query` off |

## Knowledge graph

| Variable | Default | Notes |
|---|---|---|
| `GRAPH_EXTRACTION` | `true` | Extract entities and edges at ingest |
| `GRAPH_EXTRACTOR` | `auto` | `auto`, `offline`, `llm`. See [Knowledge graph](architecture.md#extraction) |
| `GRAPH_STORE` | `sqlite` | `sqlite` or `neo4j` (needs the `[neo4j]` extra) |
| `GRAPH_MAX_ENTITIES_PER_CHUNK` | `12` | |
| `GRAPH_EXTRACT_MAX_TOKENS` | `3000` | Reply budget for `llm` extraction |
| `GRAPH_MAX_CONSECUTIVE_FAILURES` | `5` | Failures in a row before a document's extraction stops |
| `GRAPH_HOPS` | `2` | Default traversal depth |
| `GRAPH_ALIAS_PATH` | `data/graph_aliases.json` | Exact-match alias table |
| `NEO4J_URI`, `NEO4J_USER` (`neo4j`), `NEO4J_PASSWORD`, `NEO4J_DATABASE` | blank | For `GRAPH_STORE=neo4j` |

## Server and storage

| Variable | Default | Notes |
|---|---|---|
| `STORAGE_DIR` | `storage` | Index, graph, page images, uploads |
| `API_AUTH_TOKEN` | blank | Blank keeps the API open; set it before exposing the server |
| `UPLOAD_MAX_MB` | `25` | Per-file upload cap |
| `INGEST_ROOTS` | `data` | Comma-separated folders `/api/ingest` may read; the CLI is not limited |

## Optional extras

```bash
pip install -e ".[vision]"         # PDF page rendering (pypdfium2, pillow)
pip install -e ".[colpali]"        # ColPali page retrieval (colpali-engine, torch)
pip install -e ".[sbert]"          # sentence-transformers embedder (EMBEDDINGS_PROVIDER=sbert)
pip install -e ".[multilingual]"   # the same package, for EMBEDDINGS_PROVIDER=multilingual
pip install -e ".[rerank]"         # cross-encoder reranking
pip install -e ".[neo4j]"          # Neo4j graph store
```

## Notes

- After switching `EMBEDDINGS_PROVIDER`, run `rag reindex` to re-embed the stored chunks. `rag reset --yes`
  wipes the index instead, and works even when the index no longer loads.
