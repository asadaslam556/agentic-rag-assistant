# Setup guide

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Node.js](https://img.shields.io/badge/Node.js-18%2B-5FA04E?logo=nodedotjs&logoColor=white)](https://nodejs.org)
[![Git](https://img.shields.io/badge/Git-F05032?logo=git&logoColor=white)](https://git-scm.com)
[![Ollama](https://img.shields.io/badge/Ollama-optional-000000?logo=ollama&logoColor=white)](https://ollama.com/download)
[![Docker](https://img.shields.io/badge/Docker-optional-2496ED?logo=docker&logoColor=white)](https://www.docker.com)
[![PowerShell](https://img.shields.io/badge/Windows-PowerShell-5391FE?logo=powershell&logoColor=white)](commands.md)

From zero to a running, verified, streaming assistant. Windows PowerShell
commands first, macOS and Linux variants where they differ. Nothing here
needs an API key or a paid service.

Windows users who just want the commands in order, with cache clearing and
a full reset, can use [`commands.md`](commands.md) instead. To view the
console on a phone or put it online, see [`deployment.md`](deployment.md).

```mermaid
flowchart LR
    A["1-2<br/>Install"] --> B["3-4<br/>Offline run<br/>and checks"]
    B --> C{"Pick a model"}
    C -->|free, local| D["5<br/>Ollama"]
    C -->|hosted| E["5b<br/>Claude, OpenAI,<br/>DeepSeek"]
    D --> F["7<br/>Web console"]
    E --> F
    F --> G["12<br/>Your own<br/>documents"]
```

Every step after the first run is optional. The numbers match the sections below.

## 1. What you need

- Python 3.10 or newer (`python --version`)
- Node 18 or newer for the console (`node --version`)
- git
- Optional but recommended: [Ollama](https://ollama.com/download) for real
  local answers at zero cost

## 2. Install

```powershell
git clone https://github.com/asadaslam556/agentic-rag-assistant.git
cd agentic-rag-assistant
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

macOS and Linux: `source .venv/bin/activate` instead of the Activate.ps1 line.

If PowerShell refuses to run the activation script, allow local scripts once:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## 3. First run, fully offline

```powershell
rag ingest data/sample_docs
rag ask "What does the Scale plan cost per robot per month?" --trace
```

You get a cited answer, a PASSED verification line, and the agent trace
showing which tools were called and why. No model is installed yet, so the
deterministic mock is answering. That is by design: the whole pipeline works
before you configure anything.

Two more commands worth knowing from the start:

```powershell
rag stats            # which LLM, embedder, and index the pipeline resolved
rag chat             # interactive multi-turn session in the terminal
```

## 4. Sanity checks

```powershell
pytest                        # 232 tests, all offline
ruff check src tests          # lint, should be silent
python scripts/quickcheck.py  # ingest + ask + verify in one go, prints PASS
rag eval                      # golden set, 8/8 expected
```

If all four pass, the installation is sound.

## 5. Real answers with Ollama

Install Ollama, then pull a model that follows JSON instructions well:

```powershell
ollama pull qwen2.5:7b-instruct
```

That is the entire configuration. Ask anything again and check the header:

```powershell
rag stats
```

`llm=ollama:qwen2.5:7b-instruct` means the auto-detection found the server
and picked the model. The default `LLM_PROVIDER=auto` probes
`localhost:11434` on startup, takes the most capable installed model, and
falls back to the mock with a one-line note when Ollama is off. To pin a
specific model, set `OLLAMA_MODEL=llama3.1:8b` in `.env` (copy
`.env.example` to `.env` first). Leave it empty to return to auto-pick.

With a real model active, answers stream token by token in the console, the
verifier switches from lexical matching to a dedicated LLM verification
call, and follow-up questions get rewritten into standalone queries.

## 5b. Or run it on Claude, OpenAI, or a private endpoint

Ollama is only the default. Any provider is one block in `.env`:

```text
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your-key
LLM_MODEL=claude-sonnet-4-6
```

For OpenAI, use `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, and an `LLM_MODEL`
such as `gpt-4o-mini`. DeepSeek is `LLM_PROVIDER=deepseek` with
`DEEPSEEK_API_KEY` and `DEEPSEEK_MODEL=deepseek-chat`. Restart `rag serve`
after changing `.env`, then check `rag stats` to confirm which client
resolved.

The LLM and the embedder are configured separately, and neither Anthropic
nor DeepSeek sells embeddings, so a paid model does not bring paid
embeddings with it. Keep embeddings free and local:

```text
EMBEDDINGS_PROVIDER=multilingual
```

That runs multilingual-e5-small on your own machine (about 470 MB on first
run, no key). It is worth doing for any corpus that is not English, because
the default `local` embedder is a hashed bag of words with no model behind
it. It needs `pip install -e ".[multilingual]"` and one rebuild, since the
vector dimensions change:

```powershell
rag reindex
```

Pointing at a private or self-hosted endpoint instead of the public API:

```text
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your-key
ANTHROPIC_BASE_URL=https://your-endpoint.example/api
LLM_MODEL=claude-sonnet-4-6@default
```

Two things that trip people up on those endpoints:

```powershell
rag models
```

lists exactly what your endpoint serves and marks whether your `LLM_MODEL` is
on the list. Model names there often differ from the public ones, for example
a trailing `@default`. Whatever you set is sent through untouched.

And if a model answers 400 saying temperature is not supported, set it blank:

```text
LLM_TEMPERATURE=
```

That drops the field from every request rather than sending a number, which
is the only thing those models accept. It covers the verifier, judge,
decomposer, and rewriter too, which ask for a fixed 0.0 of their own.

## 5c. Multi-hop questions and other languages

Ingest builds a knowledge graph alongside the vector index, no setup and no
key. It answers questions whose answer is not in any single passage:

```powershell
rag graph explain "Which safety standard applies to the robot made by the company headquartered in Munich?" --hops 3
rag graph stats
```

Retrieval and answers work in German, Arabic, Chinese, and Urdu as well as
English, and answers come back in the language of the question. Two more
eval sets cover those paths:

```powershell
rag eval --golden eval/golden_set_graph.jsonl          # 4/4
rag eval --golden eval/golden_set_multilingual.jsonl   # 8/8, needs the PDFs ingested
```

The [README](../README.md) has the schema, the routing rule, and the
before-and-after evidence.

## 6. Web search

On by default through keyless DuckDuckGo (`SEARCH_PROVIDER=ddgs`). The agent
only reaches for it when a question needs outside information. Set
`SEARCH_PROVIDER=none` in `.env` for a fully local setup, or `tavily` plus
`TAVILY_API_KEY` if you have one.

## 7. The console

Two terminals during development:

```powershell
rag serve                     # terminal 1: API on http://localhost:8000
cd frontend; npm install; npm run dev    # terminal 2: console on http://localhost:5173
```

For a single-port setup, build the console once and let the API host it:

```powershell
cd frontend; npm run build; cd ..
rag serve                     # console + API together on http://localhost:8000
```

![The console with a verified, cited answer](console-light.png)

What to try in it:

- Click one of the sample questions or type your own. You watch the run
  live: the current stage, each tool call as it happens, then the answer
  growing token by token.
- Ask a follow-up like "and how long does deployment take?". With a real
  model, a "Searched for" line above the answer shows the standalone
  question the agent derived from the conversation.
- Click **Reasoning** under an answer to see the steps the agent took and
  why. Click a citation marker, the verdict, or the sources button to open
  the evidence drawer: the verification report with a verdict per claim,
  the sources, and the full trace with timings.
- Click the paperclip in the composer and pick your own pdf, md, txt, or
  html files. They are checked, stored under `storage/uploads/`, and indexed
  immediately, so the next question can use them.
- Ask something with two independent parts, like "what does the Scale plan
  cost and how long does deployment take". With a real model the question is
  split, both parts are researched at the same time, and every step is
  tagged with the part it belongs to.
- **Export as JSON** in the evidence drawer downloads the complete record:
  answer, citations, verification report, and trace.
- The status button in the header shows which model is answering ("Demo
  mode" means the offline mock), and the switch next to it picks Light,
  Dark, or Auto.

## 8. Install the console as an app

The console ships a web manifest and icons, so browsers treat it as
installable:

- Desktop Chrome or Edge: open the console, click the install icon at the
  right end of the address bar, confirm. It opens in its own window from
  then on.
- Android: browser menu, "Add to Home screen".
- iPhone or iPad: Safari share button, "Add to Home Screen". The icon comes
  from `apple-touch-icon.png`.

For phone use, the phone has to reach the machine running `rag serve`
(same network, use the machine's LAN address instead of localhost).

## 9. Evaluation, with and without a judge

```powershell
rag ingest data/sample_docs
rag eval
rag eval --judge
```

`rag eval` checks the eight golden questions for correctness and citations
and exits non-zero on any regression, which is exactly what CI runs.
`--judge` adds two graded scores per answer: faithfulness (is every
statement supported by the retrieved sources) and relevance (does the
answer address the question). With Ollama active those come from a
dedicated judge call to your model. Offline, a deterministic lexical scorer
stands in, so the numbers exist everywhere but mean the most with a real
model.

This is also the honest way to compare models: pull a candidate, run
`rag eval --judge`, and compare the faithfulness averages side by side.

## 10. Securing the API

Everything is open on localhost by default, which is right for a personal
tool. The moment the port is reachable by anyone else, set a token in
`.env`:

```text
API_AUTH_TOKEN=pick-something-long-and-random
```

Every endpoint except `/api/health` then requires the header:

```powershell
curl -s -X POST localhost:8000/api/chat `
     -H "content-type: application/json" `
     -H "Authorization: Bearer pick-something-long-and-random" `
     -d '{"question": "What is the payload capacity of the Atlas P2?", "history": []}'
```

`SECURITY.md` covers the rest (TLS in front, why `/api/ingest` must never
be exposed to untrusted clients, what `/api/upload` enforces).

## 11. Docker

```powershell
docker compose up --build
```

One image with the console built in and the sample corpus pre-ingested,
served on port 8000. The compose file maps `host.docker.internal` so the
container can reach an Ollama server on your machine, and keeps the index
and uploads in a named volume so they survive rebuilds.

`.env` is deliberately not copied into the image, so the container answers
with the offline mock until you opt in: uncomment `env_file` in
`docker-compose.yml`. If your `.env` sets
`EMBEDDINGS_PROVIDER=multilingual`, also set the `EXTRAS` build argument to
`[multilingual]`, because the image leaves sentence-transformers out by
default to stay small.

Without compose: `docker build -t agentic-rag .` then
`docker run -p 8000:8000 agentic-rag`.

## 12. Use your own documents

Two ways:

```powershell
rag ingest C:\path\to\your\docs      # CLI: any folder of txt, md, html, pdf
```

or the paperclip button in the console. Re-ingesting the same files skips
them (tracked by content), and `rag reset --yes` wipes the index for a
fresh start. PDFs need embedded text: scanned image-only PDFs come out
empty because OCR is out of scope here.

## 13. Push it to your GitHub

For a fork or a fresh copy of your own:

```powershell
git remote add origin https://github.com/<your-username>/agentic-rag-assistant.git
git push -u origin main
```

`.gitignore` keeps `.env`, `storage/`, local editor settings, and third-party
PDFs out of the repository. CI runs on the push: lint, the full test suite on Python 3.10 and 3.12, the
golden-set eval, and a frontend build, all without any secrets configured.

## 14. Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Answers come from `mock` although Ollama is installed | The server is not running or the URL is off. Start Ollama (it serves on 11434), check `rag stats`, and confirm `OLLAMA_BASE_URL` if you changed it. |
| `LLM_PROVIDER=ollama` errors out instead of falling back | That mode is strict on purpose. Use `auto` for the graceful fallback. |
| "Model not found" from Ollama | The pinned `OLLAMA_MODEL` is not installed. `ollama list` to see what is, `ollama pull qwen2.5:7b-instruct` to get the recommended one. |
| First answer with a model is slow | The model is loading into memory. `ollama ps` shows when it is resident, later questions are fast. |
| Console shows nothing until the full answer appears | Something between browser and API buffers the stream. Use the single-port setup on `http://localhost:8000` directly, the dev proxy and plain localhost pass SSE through fine. |
| 401 Unauthorized on API calls | `API_AUTH_TOKEN` is set. Send `Authorization: Bearer <token>` or clear the variable for local use. |
| Upload fails with a server error about multipart | The `python-multipart` package is missing from the environment. `pip install -e ".[dev]"` again inside the venv. |
| `npm install` fails behind a proxy | Configure npm's proxy (`npm config set proxy ...`) or run it on a network without one. The Python side never needs npm. |
| Port 8000 or 5173 already in use | `rag serve --port 8010` and adjust the proxy target in `frontend/vite.config.js`, or stop the other process. |
| The endpoint answers 404 for your model | The name is wrong for that endpoint. Run `rag models` and copy one of the listed names into `LLM_MODEL`. |
| A 400 about the temperature parameter | That model refuses it. Set `LLM_TEMPERATURE=` (blank) in `.env` to omit the field everywhere, including the verifier and judge. |
| Retrieval is weak on non-English documents | The default `local` embedder matches shared tokens only. Set `EMBEDDINGS_PROVIDER=multilingual`, `pip install -e ".[multilingual]"`, then `rag reindex`. |
| `EMBEDDINGS_PROVIDER=multilingual requires sentence-transformers` | The extra is not installed in this environment. `pip install -e ".[multilingual]"`, or build the Docker image with `EXTRAS=[multilingual]`. |
| The console says "Demo mode" although `.env` has a key | Docker does not read `.env` unless `env_file` is enabled in `docker-compose.yml`. Locally, check `rag stats`. |
| `graph_search` never gets used | The graph is empty, so the tool is not offered. Run `rag graph stats`, and `rag graph rebuild` if it shows nothing. |
| Questions never split into branches | Decomposition is skipped for the offline mock by design. Configure a real provider, or check `MAX_BRANCHES` is above 1. |
| A PDF ingests but questions about it fail | It is a scanned image without a text layer. Convert it with OCR first or supply the text as md. |
| Verification keeps failing on your own corpus | Look at the failing claims in the trace. If the model paraphrases too freely for the lexical matcher, lower `MIN_GROUNDEDNESS` slightly in `.env`, or run a real model so verification is semantic. |

## 15. Where to look in the code

`src/agentic_rag/pipeline.py` wires everything and is the best starting
point. From there: `agent/` for the loop and prompts, `retrieval/` for the
hybrid search, `verification/` for the claim checks and the judge,
`api.py` for the REST and SSE surface, and `frontend/src/App.jsx` for the
console. [`architecture.md`](architecture.md) explains the design, and
[`CONTRIBUTING.md`](../CONTRIBUTING.md) lists the rules that keep the offline
guarantees intact.