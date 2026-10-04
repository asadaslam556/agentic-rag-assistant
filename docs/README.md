# Documentation

Every page here was checked against the code at version 3.14.0. Start with the
[setup guide](setup-guide.md) to run it, or the [architecture](architecture.md) page to understand it.

## Guides

| Page | What it covers |
|---|---|
| [Setup guide](setup-guide.md) | From zero to a running, verified assistant, step by step |
| [Command reference](commands.md) | Windows-first commands in order, cache clearing, a full reset |
| [Configuration](configuration.md) | Every environment variable with its default |
| [Deployment](deployment.md) | Docker, Render, Cloud Run, tunnels, and opening it on a phone |
| [API reference](api.md) | Every endpoint, request, response, and the auth rule |

## How it works

| Page | What it covers |
|---|---|
| [Architecture](architecture.md) | The system on one page, the layers, the design decisions |
| [The agent and the orchestrator](agent.md) | The plan-and-act loop, decomposition, parallel branches, shared state |
| [Answer turn and streaming](streaming.md) | The stages of one turn, the pass rule, the SSE events |
| [Ingestion](ingestion.md) | Files to chunks, vectors, graph edges, and page images; uploads |
| [Retrieval and context assembly](retrieval.md) | Hybrid search, fusion, reranking, packing, languages |
| [Text-to-SQL](text-to-sql.md) | The `sql_query` tool and how SQLite keeps it read-only |
| [Knowledge graph](knowledge-graph.md) | Schema, extraction, traversal, storage |
| [Models and providers](models.md) | Providers, per-role routing, the offline mock |

Outside `docs/`: [Security](../SECURITY.md), [Contributing](../CONTRIBUTING.md), and the
[Changelog](../CHANGELOG.md).

## Diagrams

All diagrams are built with archify, a diagram tool, from JSON specs in [`diagrams/`](diagrams/),
validated against its showcase quality checks, and exported as a light PNG, a dark PNG, and an SVG.
Architecture-type diagrams carry source references pinned to commit `215fdd5`.

| Diagram | Type | Used in |
|---|---|---|
| [System overview](diagrams/system-overview.architecture.html) | architecture | [README](../README.md), [architecture](architecture.md) |
| [Agent loop](diagrams/agent-loop.architecture.html) | architecture | [README](../README.md), [agent](agent.md) |
| [Orchestration](diagrams/orchestration.architecture.html) | architecture | [README](../README.md), [agent](agent.md) |
| [Answer turn](diagrams/answer-turn.architecture.html) | architecture | [streaming](streaming.md) |
| [Chat stream](diagrams/chat-stream.sequence.html) | sequence | [README](../README.md), [streaming](streaming.md) |
| [Ingest](diagrams/ingest.dataflow.html) | dataflow | [ingestion](ingestion.md) |
| [Upload and ingest](diagrams/upload-ingest.sequence.html) | sequence | [ingestion](ingestion.md) |
| [Context assembly](diagrams/context-assembly.dataflow.html) | dataflow | [retrieval](retrieval.md) |
| [Text-to-SQL](diagrams/text-to-sql.architecture.html) | architecture | [text-to-sql](text-to-sql.md) |
| [Knowledge graph](diagrams/knowledge-graph.architecture.html) | architecture | [knowledge-graph](knowledge-graph.md) |
| [Models](diagrams/models.architecture.html) | architecture | [models](models.md) |
| [Deployment](diagrams/deployment.architecture.html) | architecture | [deployment](deployment.md) |
| [Phone access](diagrams/phone-access.architecture.html) | architecture | [deployment](deployment.md) |
| [Trust boundaries](diagrams/trust-boundaries.architecture.html) | architecture | [Security](../SECURITY.md) |
| [CI](diagrams/ci.architecture.html) | architecture | [Contributing](../CONTRIBUTING.md) |
| [Setup path](diagrams/setup-path.architecture.html) | architecture | [setup guide](setup-guide.md) |

### Viewing the interactive diagrams

GitHub shows the `.html` files as source. To use them, open one locally in a browser, for example
`docs/diagrams/system-overview.architecture.html`. Each one works offline and has a light and dark
theme, pan and zoom, guided views, and an export menu (PNG, SVG, and more). The PNGs embedded in the
markdown follow your GitHub theme.

### Updating a diagram

Edit the `.json` spec, then validate and render it with archify:

```bash
node bin/archify.mjs validate architecture docs/diagrams/<name>.architecture.json --quality showcase
node bin/archify.mjs deliver architecture docs/diagrams/<name>.architecture.json docs/diagrams/<name>.architecture.html --quality showcase --repo-root .
```

Run those from the archify skill folder with absolute paths, then export the PNG and SVG from the
viewer's export menu. The generated HTML contains dash characters that `scripts/check_text.py`
rejects; replace them with hyphens before committing.

## Archive

[`archive/`](archive/) keeps the versions of the docs before this overhaul and the replaced
agent-loop workflow diagram. [`AUDIT.md`](AUDIT.md) records what was wrong in them.
