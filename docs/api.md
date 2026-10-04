# API reference

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Pydantic](https://img.shields.io/badge/Pydantic-E92063?logo=pydantic&logoColor=white)](https://docs.pydantic.dev)
[![OpenAPI](https://img.shields.io/badge/OpenAPI-%2Fdocs-6BA539?logo=openapiinitiative&logoColor=white)](#api-reference)
[![SSE](https://img.shields.io/badge/streaming-server%20sent%20events-FF6C37)](#post-apichatstream)

`rag serve` runs the FastAPI app in `src/agentic_rag/api.py` on `127.0.0.1:8000` by default
(`--host`, `--port` to change). Every endpoint lives under `/api`. Interactive OpenAPI docs are at
`/docs`. When `frontend/dist` exists, the built console is served at `/`.

## Authentication

With `API_AUTH_TOKEN` empty (the default) the API is open, which is meant for localhost. With it set,
every endpoint except `GET /api/health` needs:

```text
Authorization: Bearer <YOUR_API_TOKEN>
```

A missing or wrong token gets `401`. The comparison is constant-time.

The console asks for the token the first time the server answers `401`, keeps it in that browser's
local storage, and sends it on every call, page images included.

CORS allows only the Vite dev server (`http://localhost:5173`, `http://127.0.0.1:5173`).

## Endpoints

| Method and path | Auth | Purpose |
|---|---|---|
| `GET /api/health` | never | Live status of every component |
| `POST /api/chat` | yes | One answer, multi-turn |
| `POST /api/chat/stream` | yes | The same, as server-sent events |
| `POST /api/ask` | yes | One-shot question, kept for compatibility |
| `POST /api/upload` | yes | Upload and ingest files |
| `POST /api/ingest` | yes | Ingest a path on the server, limited to `INGEST_ROOTS` |
| `GET /api/page-image?page_id=...` | yes | One rendered PDF page as PNG |

### GET /api/health

Each component is actually checked: a running Ollama is probed, the index is read, the catalog file and
the SQL database are opened, and the web search dependency is verified. Hosted providers are reported
as configured but not probed, because a probe would spend a paid call. `status` is `degraded` as soon
as any component is down.

```json
{
  "status": "ok",
  "version": "3.14.0",
  "llm": "mock",
  "embedder": "local-hash-v1",
  "search_provider": "ddgs",
  "retrieval_mode": "hybrid",
  "reranker": "none",
  "chunks_indexed": 21,
  "tools": ["vector_search", "web_search", "knowledge_base", "calculator", "sql_query", "graph_search"],
  "auth_required": false,
  "model_routing": null,
  "components": {
    "llm": {"status": "ok", "detail": "deterministic offline mock"},
    "index": {"status": "ok", "detail": "21 chunks, retrieval mode hybrid"},
    "catalog": {"status": "ok", "detail": "data/structured/catalog.json"},
    "database": {"status": "ok", "detail": "sales.sql, 2 tables, read-only"},
    "web_search": {"status": "ok", "detail": "ddgs installed"}
  }
}
```

That is a real response with the mock after `rag ingest data/sample_docs`. `model_routing` lists the
model per role when more than one model is configured.

### POST /api/chat

```json
{
  "question": "What does the Scale plan cost per robot per month?",
  "history": [{"question": "previous question", "answer": "previous answer"}]
}
```

`question` is 3 to 2000 characters. `history` holds at most 12 previous turns and may be empty. A
follow-up is rewritten into a standalone question when a real model is active.

The response is the answer payload:

| Field | Meaning |
|---|---|
| `question` | The question as asked |
| `text` | The answer, with `[n]` citations |
| `citations` | The sources the text cites |
| `evidence` | The packed sources, in citation order. Page evidence carries `image_url` instead of a server path |
| `verification` | `groundedness`, `citation_coverage`, `passed`, `method`, and a verdict per claim |
| `steps` | Every agent step, with the branch it belongs to |
| `attempts` | Refine attempts used |
| `timings_ms` | `retrieve_ms`, `assemble_ms`, `synthesize_ms`, `verify_ms`, `total_ms` |
| `rewritten_question` | The standalone question, or empty |
| `sub_questions`, `branches` | How the question was split and what each branch found |

### POST /api/chat/stream

Same request body. The response is `text/event-stream`: each event is `event: <name>` followed by
`data: <json>`. The events and their order are listed in
[Answer turn and streaming](architecture.md#the-event-stream). The stream ends with `answer` (the payload
above) and `done`, or with `error`.

### POST /api/ask

`{"question": "..."}`. One-shot, no history. Kept as a compatibility alias for `/api/chat`.

### POST /api/upload

Multipart form with one or more `files`. Each file must have a supported extension (`.txt`, `.md`,
`.markdown`, `.html`, `.htm`, `.pdf`) and stay under `UPLOAD_MAX_MB` (25). Accepted files are saved
under `storage/uploads/` and ingested.

```json
{
  "results": [
    {"file": "notes.md", "status": "saved", "stored_as": "notes.md"},
    {"file": "archive.zip", "status": "rejected", "detail": "unsupported type .zip"}
  ],
  "chunks_added": 4,
  "chunks_indexed": 35
}
```

### POST /api/ingest

`{"path": "data/sample_docs"}`. Ingests a file or folder on the server. The path must resolve inside
one of the comma-separated `INGEST_ROOTS` (default `data`) or the uploads folder; anything else, and
any missing path, gets the same `404`, so the endpoint cannot be used to probe the disk. The response
holds `files_added`, `files_skipped_existing`, `chunks_added`, the index statistics, and `errors` when a
file could not be read.

### GET /api/page-image

`?page_id=<id>` returns one rendered page as `image/png`. Only pages in the page index can be fetched.
A page id is `<doc-id>#page<N>`, where the document id is a hash of the file path; answer payloads
carry a ready `image_url` for every page they cite.

## Examples

```bash
curl -s localhost:8000/api/health
curl -s -X POST localhost:8000/api/chat -H "content-type: application/json" \
     -d '{"question": "How long does it run on a charge?", "history": []}'
curl -N -X POST localhost:8000/api/chat/stream -H "content-type: application/json" \
     -d '{"question": "How long does it run on a charge?"}'
curl -s -X POST localhost:8000/api/upload -F "files=@notes.md"
```

With a token, add `-H "Authorization: Bearer <YOUR_API_TOKEN>"` to every call except health.
