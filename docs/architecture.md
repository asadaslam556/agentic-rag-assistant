# Architecture

The [README](../README.md) covers what the assistant does. This page is the map of how: the system on
one page, the layers, and the design decisions. Each flow has its own page, linked below.

## The system on one page

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="diagrams/system-overview.architecture.dark.png">
  <img alt="System overview: the React console and the rag CLI reach the pipeline through the FastAPI app; the pipeline runs the orchestrator and agent loop, which call the tools; tools read the vector index, the knowledge graph, the structured data, and the web; synthesis and the verifier call models through the router" src="diagrams/system-overview.architecture.png">
</picture>

<sub>Interactive version: [`diagrams/system-overview.architecture.html`](diagrams/system-overview.architecture.html).
Each component links to the source file it was drawn from.</sub>

Everything flows through `src/agentic_rag/pipeline.py`, which is the best file to read first. A
question takes this path:

1. **Rewrite.** A follow-up in a conversation becomes a standalone question.
2. **Orchestrate.** The question is split into independent sub-questions when it has them, and each
   runs its own agent loop on its own thread. [The agent and the orchestrator](agent.md)
3. **Act.** Each loop plans one JSON action at a time and calls a tool: corpus search, graph
   traversal, page-image search, web search, the catalog, the SQL database, or the calculator.
4. **Assemble.** Evidence from every call is filtered, deduplicated, fused, re-scored, and packed into
   numbered sources. [Retrieval and context assembly](retrieval.md)
5. **Synthesise and verify.** The model writes a cited answer, every claim is checked against the
   sources it cites, and a failed check gets one targeted redraft.
   [Answer turn and streaming](streaming.md)

Every step emits live events that the console renders while the agent works.

## Pages per flow

| Page | Diagrams |
|---|---|
| [The agent and the orchestrator](agent.md) | agent loop, orchestration |
| [Answer turn and streaming](streaming.md) | answer-turn stages, chat stream sequence |
| [Ingestion](ingestion.md) | ingest data flow, upload sequence |
| [Retrieval and context assembly](retrieval.md) | context assembly |
| [Text-to-SQL](text-to-sql.md) | text-to-SQL |
| [Knowledge graph](knowledge-graph.md) | knowledge graph |
| [Models and providers](models.md) | models |
| [API reference](api.md) | |
| [Configuration](configuration.md) | |
| [Deployment](deployment.md) | deployment, phone access |
| [Security](../SECURITY.md) | trust boundaries |
| [Contributing](../CONTRIBUTING.md) | CI |
| [Setup guide](setup-guide.md) | setup path |

## The layers

Each layer only calls the layers below it. Interfaces never touch retrieval directly, and nothing below
`pipeline.py` knows whether a question came from the CLI, the API, or a test.

| Layer | Package | What it owns |
|---|---|---|
| Interfaces | `cli.py`, `api.py`, `frontend/` | The command line, the REST and SSE API, the web console |
| Wiring | `pipeline.py`, `config.py` | Builds every component from one `Settings` dataclass |
| Orchestration | `graph/` | Decomposition, parallel branches, shared budget, coverage retry, merge |
| Agent | `agent/` | The plan-and-act loop, the JSON protocol, prompts, a tolerant parser |
| Tools | `tools/` | `vector_search`, `graph_search`, `visual_search`, `web_search`, `knowledge_base`, `sql_query`, `calculator` |
| Knowledge graph | `kg/` | Extraction, SQLite or Neo4j store, multi-hop traversal |
| Retrieval | `retrieval/` | NumPy vector store, BM25, hybrid fusion, reranker, page-image late interaction, reindex |
| Ingestion | `ingestion/` | Loaders, two chunking strategies, PDF page images |
| Assembly | `assembly/` | Injection filtering, dedupe, cross-tool fusion, re-scoring, token-budget packing |
| Verification | `verification/` | Claim splitting, groundedness, refine feedback, the eval judge |
| Models | `llm/`, `embeddings/` | Provider registry, per-role model router, the mock, embedders |
| Core | `core/` | Shared types, language detection, the tokeniser, injection patterns |

## Design decisions

**No agent framework.** The orchestration, fusion, streaming, and verifier are plain Python. For a
system whose point is showing how agentic RAG works, a framework would hide the parts worth reading.
The console follows the same rule: React and one stylesheet, no UI library.

**Local-first, cloud-optional.** Ollama is the default because it costs nothing and keeps data on your
machine. The same interface covers Claude, OpenAI, Azure, DeepSeek, and compatible gateways, so
switching is one variable.

**A strict JSON protocol, and a mock that speaks it.** The loop runs on a small JSON contract instead
of provider-specific function calling. That is what makes a deterministic offline mock possible, and
why the tests, the eval, the streaming events, and CI run with no network and no keys.

**Isolated branch state.** Each branch owns its evidence, steps, and errors. The step budget, the lazy
BM25 build, and the SQLite connections are the shared exceptions, and each has a lock.

**Enforce limits in the engine, not in a filter.** The SQL tool does not scan queries for dangerous
keywords; SQLite's authorizer refuses anything but a read. The injection filter is the one place text
matching is used, and it sits behind prompts that already treat sources as data.

**Verification is the feature.** The answer is split into claims, each is checked against what it
cites, failed claims trigger a redraft with targeted feedback, and an unanswerable question gets an
explicit abstention.

**Honest limitations.** Offline, the verifier and judge are lexical approximations. The hashed
embedder is a demo device; use `sbert` or `multilingual` for real semantic quality. The vector store
is exact NumPy search, fine up to tens of thousands of chunks and intentionally not a vector database.
Follow-up rewriting and decomposition need a real model, and very small models sometimes struggle with
the JSON tool loop.

## Testing philosophy

The model is mocked in every test. What is verified is everything around it: the guardrails, the
retrieval fusion, the verification maths, and the control flow. That tools loop back to the planner,
that decomposition stays conservative, that branches really run at the same time, that the shared
budget holds exactly under contention, that one failing branch is contained, and that streaming emits
its events and exactly one final answer. Model quality changes the answers; it does not change whether
the loop is safe.
