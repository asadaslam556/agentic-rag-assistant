# Documentation audit

Audit of every document, diagram, and image in the repository at version 3.14.0
(`main` at `215fdd5`), checked against the code. It records the state before the
documentation overhaul on the `docs/overhaul` branch.

Status values: **accurate** (matches the code), **outdated** (was true once or is
incomplete), **wrong** (contradicts the code), **duplicate** (repeats another
doc), **missing** (a flow with no diagram or doc).

## Documents

| File | Status | Reason |
|---|---|---|
| `README.md` | outdated | Mostly correct, but says `PDF_VISION` is off by default (it is `auto`, `config.py:287`); says the Docker image runs on the mock (it uses a host Ollama when one answers, `docker-compose.yml:12` plus `LLM_PROVIDER=auto`); offers `rag reset --yes` after an embedder switch, which fails in that state (see Code observations); lint command omits `scripts`; five Mermaid diagrams with incomplete tool lists |
| `docs/architecture.md` | outdated | Accurate walkthrough overall; worker diagram omits `visual_search`; verification diagram omits the citation-coverage condition; ingestion diagram omits page images and ColPali vectors; "On this page" skips two sections |
| `docs/setup-guide.md` | outdated | Claims the multilingual eval reaches 8/8 after ingesting the PDFs; two of its cases need Siemens and SAP reports that are gitignored, so a clone reaches at most 6/8. `rag stats` output shown as `llm=ollama:...` (the one-line form is printed by `rag ask`, `cli.py:105`) |
| `docs/commands.md` | outdated | Shows `PDF_VISION=on` as the example value; Makefile list omits `make ingest`; lint command omits `scripts`; about 80% overlaps README and setup guide |
| `docs/deployment.md` | wrong | The Cloud Run command has no `--port 8000` while the image listens on 8000 (`Dockerfile` CMD) and Cloud Run defaults to 8080; says the console "will need" the API token, but the console never sends an `Authorization` header (`frontend/src/api.js`) |
| `SECURITY.md` | accurate | Matches `api.py`, `core/injection.py`, `tools/sql.py`, `Dockerfile` |
| `CONTRIBUTING.md` | outdated | CI flowchart and checklist omit `pip-audit`, `npm audit`, and the `scripts` lint scope (`.github/workflows/ci.yml`) |
| `CHANGELOG.md` | accurate | Release history; not rewritten (history is a record, not a guide) |
| `CITATION.cff` | accurate | Version 3.14.0 matches `pyproject.toml` |
| `.github/PULL_REQUEST_TEMPLATE.md` | outdated | Lint line omits `scripts` |
| `.github/ISSUE_TEMPLATE/*.md` | accurate | Generic templates |
| `.env.example` | outdated | Provider list on line 11 omits `deepseek`, which `llm/providers.py` registers. It is configuration, so it is flagged, not edited, in this overhaul |
| `docs/README.md` (index) | missing | No index of the docs |
| API reference | missing | Endpoints are only listed in a table in `docs/commands.md` |
| Per-module pages | missing | Knowledge graph, PDFs, text-to-SQL, models, and verification are spread across README and architecture.md |

## Diagrams

All 24 are Mermaid blocks rendered by GitHub. None has an interactive or exported version.

| Location | Depicts | Status | Reason |
|---|---|---|---|
| README.md:133-154 | whole system | outdated | Tool list omits `visual_search` |
| README.md:164-176 | orchestrator | duplicate | Simpler copy of architecture.md:43-60 without the coverage retry |
| README.md:180-195 | worker loop | outdated | Omits `graph_search` and `visual_search` |
| README.md:205-237 | package layers | accurate | Matches the package layout |
| README.md:259-289 | request sequence | accurate | Omits `branch_error` and `error` events, which is acceptable at this level |
| docs/architecture.md:20-37 | worker loop | outdated | Omits `visual_search` |
| docs/architecture.md:43-60 | orchestrator with retry | accurate | Matches `graph/runner.py` |
| docs/architecture.md:72-90 | branch state and locks | accurate | Matches `graph/state.py`, `retrieval/hybrid.py` |
| docs/architecture.md:108-115 | decomposer fallback | accurate | Matches `graph/decompose.py` |
| docs/architecture.md:129-139 | ingestion | outdated | Omits `pages/` records and ColPali vectors |
| docs/architecture.md:145-162 | retrieval and assembly | accurate | Matches `assembly/context_assembly.py` |
| docs/architecture.md:172-181 | text-to-SQL | outdated | Omits the function allowlist and value cap |
| docs/architecture.md:193-204 | verification states | outdated | Pass also needs citation coverage of at least 0.5 (`verification/verifier.py`) |
| docs/architecture.md:212-229 | streaming sequence | accurate | Omits `branch_error` and `error` |
| docs/architecture.md:239-247 | provider registry | accurate | Matches `llm/providers.py` |
| docs/architecture.md:257-275 | model routing | accurate | Matches `llm/router.py` |
| docs/architecture.md:285-294 | knowledge graph schema | accurate | Matches `kg/schema.py` |
| docs/architecture.md:304-313 | page images | accurate | Matches `ingestion/pdf_vision.py`, `retrieval/late_interaction.py` |
| SECURITY.md:12-25 | trust boundaries | accurate | Matches the code paths |
| CONTRIBUTING.md:22-30 | pull request flow | outdated | CI box omits the dependency audits |
| docs/deployment.md:26-35 | phone access decision | accurate | Guidance, not code |
| docs/deployment.md:44-56 | hosted topology | accurate | Described hosting only; no platform config exists in the repo |
| docs/setup-guide.md:18-28 | setup path | accurate | Section numbers exist |

ASCII and text diagrams:

| Location | Status | Reason |
|---|---|---|
| README.md terminal blocks (graph explain, SQL trace, real output, eval, tree) | accurate | Real output format of the CLI |
| docs/commands.md:515-586 text tables | duplicate | Repeat README tables |
| `src/agentic_rag/pipeline.py:1-10` docstring | outdated | Lists only vector, web, and structured tools. Source code, so flagged and not edited |
| `src/agentic_rag/graph/runner.py:5-8` docstring | accurate | Matches the code |

## Images

| File | Status | Reason |
|---|---|---|
| `docs/logo.png` | accurate | README logo |
| `docs/demo.gif` | accurate | Real run; 17 MB, the heaviest asset on the README |
| `docs/dashboard.png`, `docs/dashboard-light.png` | accurate | Current console layout |
| `docs/social-preview.png` | accurate | GitHub social preview; not referenced from markdown, by design |
| `frontend/public/*.png` | accurate | PWA icons from `scripts/make_icons.py` |

## Flows with no diagram

- Upload and ingest over the API (`POST /api/upload` to `AgenticRAG.ingest`)
- The full ingest data path, including where each file under `STORAGE_DIR` comes from
- The answer-turn lifecycle as the console sees it (the `stage` values from planning to done)
- The actual Docker build and runtime (two build stages, volume, host Ollama, health check)
- The CI pipeline as it runs today
- The console: which component consumes which endpoint and event

## Code observations

Found while checking the documentation. Each was confirmed by reading the code;
none was changed.

1. Page-image links always return 404. `tools/visual_search.py:63` sets the
   evidence id to the page id, `agent/orchestrator.py:130` renames every piece of
   evidence to `e1`, `e2`, and so on, `api.py:126` builds the image URL from that
   renamed id, and `api.py:337-338` looks the page up by its original id.
2. `PDF_VISION=auto` judges text density over the whole PDF, not per page:
   `pipeline.py:213` counts pages by form-feed characters, but
   `ingestion/loaders.py:59` joins PDF pages with blank lines, so the count is 1.
3. Evidence ids and call ids restart in every parallel branch
   (`agent/orchestrator.py:59,130`), and context assembly keys rank fusion by id
   and groups by call id (`assembly/context_assembly.py:67-71`), so a split
   question can merge scores of unrelated evidence. The offline mock never
   splits questions, which is why tests do not see it.
4. `rag reset` cannot recover from the index errors that recommend it:
   `cli.py:178` builds the pipeline first, the vector store raises
   (`retrieval/vector_store.py:47-67`), and the CLI exits with code 2
   (`cli.py:25-27`).
5. The console cannot send an API token (no `Authorization` header in
   `frontend/src/api.js`), so setting `API_AUTH_TOKEN` breaks every protected
   call from the console.
6. `Makefile` runs `ruff check src tests` while CI runs
   `ruff check src tests scripts`, and `.PHONY` lists an `ask` target that
   does not exist.
7. The Docker image runs Python 3.11, which CI does not test (the matrix is
   3.10 and 3.12), and `.dockerignore` excludes `data/sample_pdfs`, so the
   visual retrieval demo PDF is not in the image.
