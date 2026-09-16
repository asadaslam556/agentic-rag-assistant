# Commands

[![Windows](https://img.shields.io/badge/Windows-PowerShell-5391FE?logo=powershell&logoColor=white)](#part-1-windows-step-by-step)
[![Linux and macOS](https://img.shields.io/badge/Linux%20%26%20macOS-bash-4EAA25?logo=gnubash&logoColor=white)](#part-2-linux-and-macos)
[![Docker](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white)](#docker-either-platform)
[![API](https://img.shields.io/badge/API-REST%20%2B%20SSE-009688?logo=fastapi&logoColor=white)](#api)

Everything needed to run this project from nothing, in order. Windows first
and in detail, then the Linux and macOS equivalents, then the day-to-day
reference.

Nothing here needs an API key or a paid service. The project runs fully
offline with a deterministic mock model, and you can attach a real model
later.

**Jump to:** [Windows step by step](#part-1-windows-step-by-step) · [Linux and macOS](#part-2-linux-and-macos) · [Docker](#docker-either-platform) · [Command reference](#part-3-command-reference) · [Configuration](#configuration-worth-knowing) · [API](#api) · [Full reset](#windows-full-reset) · [Snags](#windows-snags)

---

# Part 1: Windows, step by step

## Step 1. Install the prerequisites

| Tool | Why | Where |
| --- | --- | --- |
| Python 3.10+ | the backend | <https://www.python.org/downloads/windows/> (tick **Add python.exe to PATH**) |
| Node 20.19+ (22 or 24 LTS) | the web console | <https://nodejs.org/en/download> |
| Git | cloning and pushing | <https://git-scm.com/download/win> |
| Ollama (optional) | free local model | <https://ollama.com/download> |

Close and reopen PowerShell after installing, then confirm:

```powershell
python --version
node --version
npm --version
git --version
```

If `python` opens the Microsoft Store instead of running, turn off the alias:
Settings, Apps, Advanced app settings, App execution aliases, switch off both
python entries, reopen PowerShell.

Allow the virtual environment activation script to run, once per user:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## Step 2. Clear caches

Worth doing before a fresh start, especially if an earlier version of this
project has been on the machine. None of it touches your code.

```powershell
python -m pip cache purge
npm cache clean --force
```

Inside the project folder (skip if you have not cloned it yet):

```powershell
Get-ChildItem -Path . -Include __pycache__ -Recurse -Directory | Remove-Item -Recurse -Force
Get-ChildItem -Path . -Include *.pyc -Recurse -File | Remove-Item -Force
Remove-Item -Recurse -Force .pytest_cache, .ruff_cache -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force frontend\node_modules, frontend\dist -ErrorAction SilentlyContinue
```

## Step 3. Get the code

```powershell
cd C:\Users\<you>\projects
git clone https://github.com/asadaslam556/agentic-rag-assistant.git
cd agentic-rag-assistant
```

From the zip instead: extract it, then `cd` into the extracted
`agentic-rag-assistant` folder.

## Step 4. Create the environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
```

The prompt now starts with `(.venv)`. Every command below belongs in that
activated shell, and every new terminal needs the activate line again.

## Step 5. Install

```powershell
pip install -e ".[dev]"
```

Editable install plus the test and lint tools. Confirm the CLI landed:

```powershell
rag --help
```

## Step 6. Verify before using

```powershell
pytest
ruff check src tests
python scripts\quickcheck.py
```

Expected: the suite passes, ruff prints nothing, quickcheck ends with `PASS`.

## Step 7. First run, offline

```powershell
rag ingest data\sample_docs
rag ask "What does the Scale plan cost per robot per month?" --trace
rag eval
```

You get a cited answer, a passed verification line, the agent trace, and 8/8
on the golden set, with no model installed.

## Step 8. Attach a real model

**Free and local, with Ollama.** In a normal PowerShell window:

```powershell
ollama pull qwen2.5:7b-instruct
```

Nothing else to configure. Back in the project shell:

```powershell
rag stats
rag ask "How long does a typical Atlas deployment take?"
```

**Or a hosted model.** Copy the config template and edit it:

```powershell
Copy-Item .env.example .env
notepad .env
```

```text
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your-key-here
LLM_MODEL=claude-sonnet-4-6
```

For a private or self-hosted endpoint, add its address and ask it what it
serves:

```text
ANTHROPIC_BASE_URL=https://your-endpoint.example/api
```

```powershell
rag models
```

Copy an exact name from that list into `LLM_MODEL`. If a model answers 400
saying temperature is not supported, set `LLM_TEMPERATURE=` with nothing
after it.

**Or DeepSeek.**

```text
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your-key-here
LLM_MODEL=deepseek-chat
```

**Or OpenAI.** `LLM_PROVIDER=openai`, `OPENAI_API_KEY=...`,
`LLM_MODEL=gpt-4o-mini`.

**Split cheap and strong models by job.** Planning, splitting a question,
rewriting a follow-up, and judging an eval are mechanical. Writing the answer
and verifying it are not. Set both and each role goes to the right model:

```text
LLM_MODEL_FAST=deepseek-chat
LLM_MODEL_DEEP=deepseek-reasoner
```

Any single role can be pinned, which beats the tiers:
`LLM_MODEL_PLAN`, `LLM_MODEL_DECOMPOSE`, `LLM_MODEL_REWRITE`,
`LLM_MODEL_SYNTHESIZE`, `LLM_MODEL_VERIFY`, `LLM_MODEL_JUDGE`,
`LLM_MODEL_VISION`. Run `rag stats` and the resolved map is printed whenever
more than one model is in play.

**Reading charts and tables in PDFs.** Text extraction cannot see a bar chart.
The repository ships `data\sample_pdfs\auralis-quarterly-review.pdf` to
demonstrate it: five pages of prose, an unlabelled bar chart, a table, a
schematic, and a trend line. The quarterly figures exist only as bar heights.

There are two ways to handle it, and they can be used together.

*Option 1, describe the pages.* Small install, works anywhere:

```powershell
pip install -e ".[vision]"
```

```text
PDF_VISION=on        # off | auto | on
VISION_MAX_PAGES=20
```

Each page is rendered and read by a vision-capable model, and the description
is indexed as text. Needs a provider that can see, so Claude, OpenAI, or
DeepSeek rather than the offline mock.

*Option 2, retrieve the pages as pictures (ColPali).* Larger install, better
retrieval:

```powershell
pip install -e ".[colpali]"
```

```text
VISUAL_RETRIEVER=colpali
COLPALI_MODEL=vidore/colSmol-256M
```

Page images are embedded directly and ranked by late interaction, and a
`visual_search` tool appears for the agent to use. The first run downloads
the model, and `colSmol` is the small one that works on a CPU. Expect a few
seconds per page while indexing.

Then, either way:

```powershell
rag ingest data\sample_pdfs
rag ask "How many robots were deployed by the end of Q4?" --trace
rag ask "At what battery charge is throughput highest?" --trace
```

Both answers live only in the charts. The trace shows which tool found them.

Confirm whichever you chose:

```powershell
rag stats
```

## Step 9. Run the web console

Two terminals during development.

Terminal 1, the API:

```powershell
.venv\Scripts\Activate.ps1
rag serve
```

Terminal 2, the console:

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

One terminal instead, by building the console once and letting the API host
it:

```powershell
cd frontend
npm install
npm run build
cd ..
rag serve
```

Open <http://localhost:8000>. API docs at <http://localhost:8000/docs>,
component status at <http://localhost:8000/api/health>.

## Step 10. Your own documents

```powershell
rag ingest C:\path\to\your\documents
```

Or use the paperclip button in the console for pdf, md, txt, and html. Start
the index over with:

```powershell
rag reset --yes
rag ingest data\sample_docs
```

### Multi-hop questions and the knowledge graph

Ingest builds a knowledge graph alongside the vector index, with no extra
setup and no key: entities and the relationships between them, stored in
SQLite next to the index.

```powershell
rag graph stats
rag graph explain "Which safety standard applies to the robot made by the company headquartered in Munich?" --hops 3
```

That question is answered by walking Munich to Auralis Dynamics to the
Atlas P2 to ISO 3691-4:2023, because no single passage contains the chain.
Questions that name something by its relationship route to `graph_search`;
single-fact lookups stay on `vector_search`.

If a document was indexed before extraction was switched on, rebuild
without re-reading the source files:

```powershell
rag graph rebuild
```

### Connecting a real model

Nothing is needed to start: with no configuration the project uses a local
Ollama if one is running and the deterministic mock otherwise. To use Claude,
copy `.env.example` to `.env` and fill in:

```powershell
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-5@default
```

`.env` is gitignored, so keys never land in the repository. A missing key
prints one line naming the variable rather than a stack trace.

One command to check the whole path end to end, including whether the model
answers in the language it was asked in:

```powershell
python scripts\smoke_language.py
```

### Documents that are not in English

Retrieval and answers work in German, Arabic, Chinese, and Urdu as well as
English, with no extra setup. There is a small sample corpus to try:

```powershell
rag ingest data\sample_docs_multilingual
rag ask "Wie hoch ist die Traglast der Atlas P2?"
```

The built-in `local` embedder matches on shared tokens only, so for a corpus
that is genuinely multilingual, switch to a multilingual model. It downloads
on first use, roughly 470 MB:

```powershell
pip install -e ".[multilingual]"
# in .env:  EMBEDDINGS_PROVIDER=multilingual
rag reindex
```

`rag reindex` is needed because the vector dimensions change with the model.
It re-embeds the chunks already in the index, so the original files do not
have to be present, and it copies chunks.jsonl to chunks.jsonl.bak first.
The BM25 index needs no separate step: it is rebuilt in memory from the same
chunks on the next search.

## Step 11. Push to GitHub

The repository is already a git repository on `main`. Point it at your
GitHub copy and push:

```powershell
git remote add origin https://github.com/<your-username>/agentic-rag-assistant.git
git push -u origin main
```

`.gitignore` keeps `.env`, `storage/`, `node_modules/`, editor and assistant
settings, third-party PDFs, and caches out of the commit. `.gitattributes` normalises line endings so a Windows checkout does
not commit CRLF. CI then runs lint, the suite on two Python versions, the
offline eval, and a console build, with no secrets configured.

## Windows full reset

Returns to a clean tree and reinstalls, without touching your code:

```powershell
deactivate
Remove-Item -Recurse -Force .venv, storage, .pytest_cache, .ruff_cache -ErrorAction SilentlyContinue
Get-ChildItem -Path . -Include __pycache__ -Recurse -Directory | Remove-Item -Recurse -Force
Remove-Item -Recurse -Force frontend\node_modules, frontend\dist -ErrorAction SilentlyContinue
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
rag ingest data\sample_docs
pytest
```

## Windows snags

| Symptom | Fix |
| --- | --- |
| `python` opens the Microsoft Store | Turn off the App execution aliases for python, reopen PowerShell. |
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`. |
| `rag` is not recognised | The environment is not active in this window. Run `.venv\Scripts\Activate.ps1`. |
| `pip install` fails building a wheel | `python -m pip install --upgrade pip setuptools wheel`, then retry. |
| Path with spaces breaks a command | Quote it: `rag ingest "C:\My Documents\docs"`. |
| Port already in use | `rag serve --port 8010`, and update the proxy target in `frontend\vite.config.js`. |
| Ollama installed but answers come from the mock | Ollama is not running. Start it, then check `rag stats`. |
| Console shows nothing until the answer finishes | A proxy is buffering the stream. Use the single-port build on `http://localhost:8000`. |
| Firewall prompt on first `rag serve` | Allow on private networks. It binds to localhost unless you pass `--host`. |

---

# Part 2: Linux and macOS

Same steps, three differences: activation, path separators, and the Python
command name.

```bash
# prerequisites: python3.10+, node 20.19+, git. Optional: ollama.
python3 --version && node --version && git --version

# caches
python3 -m pip cache purge
npm cache clean --force
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
rm -rf .venv .pytest_cache .ruff_cache frontend/node_modules frontend/dist

# code
git clone https://github.com/asadaslam556/agentic-rag-assistant.git
cd agentic-rag-assistant

# environment and install
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"

# verify
pytest
ruff check src tests
python scripts/quickcheck.py

# first run
rag ingest data/sample_docs
rag ask "What does the Scale plan cost per robot per month?" --trace
rag eval

# real model (free, local)
ollama pull qwen2.5:7b-instruct
rag stats

# or a hosted model
cp .env.example .env
$EDITOR .env          # set LLM_PROVIDER, the key, and LLM_MODEL
rag models

# console
rag serve                                   # terminal 1
cd frontend && npm install && npm run dev   # terminal 2
# or single port:
cd frontend && npm install && npm run build && cd .. && rag serve
```

There is a Makefile for the common targets:

```bash
make install     # pip install -e ".[dev]"
make demo        # ingest the sample corpus and ask one traced question
make test        # pytest
make lint        # ruff check src tests
make eval        # golden set
make serve       # rag serve --port 8000
make ui-install  # npm install in frontend
make ui-dev      # npm run dev
make ui-build    # npm run build
make icons       # regenerate the PWA icons
make sample-pdf  # rebuild the demo PDF with charts and tables
make clean       # remove storage and caches
```

## Docker, either platform

```bash
docker compose up --build
```

One image with the console built in and the sample corpus pre-indexed, on
port 8000. The compose file maps `host.docker.internal`, so a container can
reach an Ollama server running on your machine, and stores the index and
uploads in a named volume. `.env` is not read unless you uncomment
`env_file` in `docker-compose.yml`, so by default the container answers with
the offline mock. For the multilingual embedder, also set the `EXTRAS` build
argument to `[multilingual]`. Without compose:

```bash
docker build -t agentic-rag .
docker run -p 8000:8000 agentic-rag
```

---

# Part 3: Command reference

## Everyday

```text
rag ingest <path>            index a file or folder (pdf, md, txt, html)
rag ask "question"           one question, cited answer
rag ask "question" --trace   with the full agent trace
rag ask "question" --json    machine-readable output
rag chat                     multi-turn session with memory
rag serve                    API on :8000, plus the console when built
rag stats                    active provider, model routing, embedder, index size
rag models                   what the configured endpoint actually serves
rag eval                     golden set, non-zero exit on regression
rag eval --judge             adds faithfulness and relevance scores
rag eval --golden FILE       run a different question set
rag eval --golden eval/golden_set_multilingual.jsonl   multilingual eval set (8 cases)
rag graph stats              entity and relationship counts
rag graph rebuild            rebuild the graph from stored chunks
rag graph explain "<q>"      show the entities and edges a question walks
rag eval --golden eval/golden_set_graph.jsonl          graph eval set (4 cases)
rag reindex                  re-embed stored chunks after changing the embedder
rag reindex --no-backup      same, without the chunks.jsonl.bak copy
rag reset --yes              wipe the index and start over
```

## Development

```text
pytest                        the whole suite, offline
pytest tests/test_graph.py    one file
ruff check src tests          lint
ruff check --fix src tests    lint and autofix
python scripts/quickcheck.py  end-to-end sanity run without pytest
python scripts/check_text.py  em dashes and personal paths in tracked text
python scripts/make_icons.py  regenerate the PWA icons
python scripts/make_sample_pdf.py   rebuild the demo PDF with charts and tables
```

## Configuration worth knowing

Copy `.env.example` to `.env` first. Full list is in that file.

```text
LLM_PROVIDER      auto | ollama | anthropic | deepseek | openai | azure | openai_compatible | mock
                  (auto probes Ollama, falls back to the offline mock)
LLM_MODEL         one model name for whichever provider is active
LLM_MODEL_FAST    cheap model for plan, decompose, rewrite, judge
LLM_MODEL_DEEP    stronger model for synthesize, verify, vision
LLM_MODEL_<ROLE>  pin one role, beats the two settings above
LLM_TEMPERATURE   0.1 by default. Blank omits the field for models that reject it
RETRIEVAL_MODE    hybrid | vector | bm25
CHUNK_STRATEGY    structure | length
PDF_VISION        off | auto | on, read PDF pages as images
VISUAL_RETRIEVER  description | colpali, how indexed pages are ranked
COLPALI_MODEL     blank uses colSmol, the CPU-friendly model
EMBEDDINGS_PROVIDER          local | sbert | multilingual | openai
MULTILINGUAL_EMBEDDING_MODEL model used when the provider is multilingual,
                             defaults to intfloat/multilingual-e5-small
ANSWER_LANGUAGE   auto follows the question, or pin a code: en | de | ar | zh | ur
GRAPH_EXTRACTION  true builds the knowledge graph during ingest
GRAPH_EXTRACTOR   offline (rules, free) | llm (one call per chunk) | auto
GRAPH_STORE       sqlite (embedded, default) | neo4j (optional extra)
GRAPH_HOPS        how many relationships graph_search follows, default 2
ANTHROPIC_API_KEY key for LLM_PROVIDER=anthropic, read from .env or the shell
ANTHROPIC_BASE_URL point at a private endpoint instead of the public API
ANTHROPIC_MODEL   sent through untouched, e.g. claude-sonnet-5@default
DEEPSEEK_API_KEY  key for LLM_PROVIDER=deepseek (OpenAI-compatible)
DEEPSEEK_BASE_URL defaults to https://api.deepseek.com
MAX_BRANCHES      how many sub-questions may run in parallel, 1 disables splitting
API_AUTH_TOKEN    set before exposing the API beyond your machine
UPLOAD_MAX_MB     per-file cap for console uploads
```

## API

Start it with `rag serve`. Interactive docs at <http://localhost:8000/docs>.

| Route | Method | What it does |
| --- | --- | --- |
| `/api/health` | GET | Per-component status: model backend, index, catalog, web search. Never needs auth |
| `/api/chat` | POST | Ask a question, optionally with history. Returns the full answer payload |
| `/api/chat/stream` | POST | Same body, answers as server-sent events |
| `/api/ask` | POST | One-shot question, kept for older clients |
| `/api/ingest` | POST | Index a path on the server machine |
| `/api/upload` | POST | Upload documents and index them, the remote-safe way to add files |
| `/api/page-image` | GET | Fetch a rendered page by `page_id`, used by citations that point at a page |

```bash
# status of every component
curl -s localhost:8000/api/health

# a question, with conversation history
curl -s -X POST localhost:8000/api/chat \
     -H "content-type: application/json" \
     -d '{"question": "What is the payload capacity of the Atlas P2?", "history": []}'

# the same question, streamed
curl -N -X POST localhost:8000/api/chat/stream \
     -H "content-type: application/json" \
     -d '{"question": "What does the Scale plan cost?", "history": []}'

# index a folder that already sits on the server
curl -s -X POST localhost:8000/api/ingest \
     -H "content-type: application/json" \
     -d '{"path": "data/sample_docs"}'

# upload documents from anywhere
curl -s -X POST localhost:8000/api/upload -F "files=@report.pdf" -F "files=@notes.md"

# a page image behind a citation
curl -s "localhost:8000/api/page-image?page_id=auralis-quarterly-review%23page2" -o page2.png
```

With `API_AUTH_TOKEN` set, every call except `/api/health` needs
`-H "Authorization: Bearer <token>"`.

On PowerShell use backticks for line continuation, and prefer
`curl.exe` so you get real curl rather than the PowerShell alias:

```powershell
curl.exe -s -X POST localhost:8000/api/chat `
  -H "content-type: application/json" `
  -d '{\"question\": \"What is the payload capacity of the Atlas P2?\", \"history\": []}'
```

---

## Deploying and showing it on a phone

A tunnel or LAN address only works while your computer is on. For a link that
works anywhere, deploy the container. Full walkthrough in
[`deployment.md`](deployment.md), including why a private model
endpoint will not resolve from a public host.

```powershell
# quick tunnel, while your machine stays on
cd frontend; npm run build; cd ..
rag serve
cloudflared tunnel --url http://localhost:8000   # second terminal
```

---

Related docs: the [README](../README.md) for what the project is and how it
is built, [`architecture.md`](architecture.md) for the internals,
[`deployment.md`](deployment.md) for putting it online and viewing it on a
phone, [`setup-guide.md`](setup-guide.md) for the narrated version of Part 1.