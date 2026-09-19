# Changelog

## 3.13.0

Fixes for everything GitHub's CodeQL scan flagged on the first public push,
a bug that showed up while taking the new README screenshot, model listing
for DeepSeek, and a demo GIF.

### Security

- **`/api/ingest` only reads allowed folders.** It used to index any path on
  the server it was given. Paths are now resolved (so `..` and symlinks
  cannot climb out) and must sit under `INGEST_ROOTS`, default `data`, or the
  uploads folder. A forbidden path returns the same 404 as a missing one, so
  the endpoint cannot be used to probe the disk. `rag ingest` on the CLI is
  unchanged.
- **Upload names are sanitised properly.** Directory parts and unusual
  characters are stripped, and the final path is checked to be inside the
  uploads folder before anything is written.
- **Exception details stay on the server.** `/api/health` and the chat
  stream log the full error and send the client a short generic message.
  Ingest names a file it could not read and prints the reason to stderr,
  where `rag ingest` users still see it, instead of returning it in the
  response. Provider setup errors still come through, because they carry
  the fix the user needs.
- **No regex backtracking on hostile input.** The sentence splitter matches
  a single space (whitespace is collapsed first, so results are identical),
  the mock's arithmetic and percentage patterns have bounded repetitions, and
  the mock's source parser no longer uses a lazy multiline pattern.
- **The OpenAI key check compares the host.** It used a substring test, which
  `api.openai.com.example.net` would have passed.
- **CI runs with read-only repository permissions.**
- Regression tests cover the ingest boundary, upload names, the patterns
  on long adversarial input, and DeepSeek model listing. Suite: 232 to 236.

### Fixed: steps lost their branch in the saved answer

Live `step` events said which part of a split question produced them, but
the steps in the final answer did not, so the evidence drawer labelled every
step "part 1". `AgentStep` now carries `branch`, and a retried branch keeps
the number of the branch it replaces.

### Fixed: `rag models` with DeepSeek

`rag models` said listing was not supported for `LLM_PROVIDER=deepseek` and
pointed at Azure settings. DeepSeek serves an OpenAI-style `/models` route,
so it now lists the models your key can use and marks the one in use. Only
Azure keeps its own message, since deployments there are named by you.
The DeepSeek default and every example now use the names DeepSeek serves
today: `deepseek-flash` and `deepseek-v4-pro` (previously `deepseek-chat`
and `deepseek-reasoner`).

### Docs

- A demo GIF at the top of the README: a question split into parts, a
  follow-up, a multi-hop question through the knowledge graph, the
  calculator, a German question, and an honest "not in the sources".
- New README screenshot from a real run on Claude: a question split into
  two parts, cited and verified answers, and the reasoning view, in light
  and dark versions that follow the reader's GitHub theme.
- `INGEST_ROOTS` in the README configuration table, `.env.example`, the API
  reference, and `SECURITY.md`.

## 3.12.0

Dependency housekeeping after the first push to GitHub, and documentation
you can read at a glance.

### Changed: frontend dependencies

- React and React DOM 19, upgraded together. Dependabot had opened them as
  two separate pull requests, and each one failed CI on its own because the
  two packages must share a version.
- Vite 8 with `@vitejs/plugin-react` 6, which closes the esbuild dev-server
  advisory `npm audit` reported (0 vulnerabilities now). The console build
  now needs Node 20.19 or newer: `engines` says so, CI builds on Node 22, and
  the Docker image builds on `node:22-alpine`.
- `.github/dependabot.yml` groups `react` with `react-dom`, `vite` with
  `@vitejs/*`, and all GitHub Actions, so packages that must move together
  arrive in one pull request.

### Changed: CI

- `actions/checkout`, `actions/setup-python`, and `actions/setup-node` moved
  to v7.
- The console job installs with `npm ci` from the lockfile and caches npm
  downloads.

### Docs

- Mermaid diagrams throughout, each checked against Mermaid 11 and kept
  narrow enough to read in GitHub's column:
  - README: the whole system on one page, the layer map, and the path of
    one question from the console to the verified answer.
  - `docs/architecture.md`: the ASCII drawings are now diagrams, plus new
    ones for branch state and locks, the decomposer fallbacks, ingestion,
    retrieval and rank fusion, the verification loop, streaming events,
    provider selection, model routing, the knowledge graph schema, and the
    two page-image paths.
  - `docs/deployment.md`: which hosting option fits, and what runs where.
  - `docs/setup-guide.md`: the setup path, plus a console screenshot.
  - `CONTRIBUTING.md` and `SECURITY.md`: the pull request flow and the
    trust boundaries.
- Technology badges on every document, and a table of contents in the
  README, the architecture page, and the command reference.
- README badges now also cover sentence-transformers, SQLite, Neo4j,
  DuckDuckGo, and GitHub Actions.
- `CITATION.cff`, so GitHub offers "Cite this repository". Author details are
  also in the console sidebar, the interactive API docs at `/docs`, and the
  console's `package.json`.

## 3.11.0

A pass over the web console after using it for real: one button that did
nothing, a header full of numbers nobody asked for, and a handful of styles
that were written but never matched anything. Plus clearer `rag eval`
output.

### Fixed: the sidebar button did nothing on a desktop-width window

The menu button toggled a `sidebarOpen` flag, but only the mobile stylesheet
(under 860px) reacted to it. On a normal monitor the sidebar was always
visible and the button looked stuck. Desktop and mobile now have their own
state: on desktop the button collapses and restores the sidebar and the
choice is remembered, on phones it opens a slide-over drawer that closes on
the backdrop, the close button, Escape, or picking a chat. A collapsed
sidebar is also `visibility: hidden`, so Tab no longer lands on buttons you
can't see.

### Changed: the header status readout

The header used to show the raw model id and the chunk count as two pills
("mock", "28 chunks"). The chunk count was a debugging number from
`/api/health`: useful when checking an ingest, meaningless to someone asking
a question, and the empty-index case already has its own banner. Both pills
are replaced by a single status button: a coloured dot plus the model name,
"Demo mode" when the offline mock is answering, or "Offline" when the
backend is unreachable. Clicking it shows the details (model, passages
indexed, retrieval mode, version, and any component reporting a problem),
with a retry button when offline. Health is re-checked every 30 seconds
while the tab is visible and right after a failed request, so the dot no
longer says everything is fine after the server has stopped.

### Changed: theme picker

The single button that cycled through "auto", "light", and "dark" is now a
three-way Light / Dark / Auto switch with arrow-key support. Auto still
follows the operating system and is stored the same way as before.

### Changed: console layout and copy

- New icon set (inline SVG, no new dependency) replaces the text buttons
  ("edit", "del", "close", "+ files").
- The composer is a growing textarea: Enter sends, Shift+Enter adds a line,
  and you can keep typing while an answer streams.
- Brand mark moved to the sidebar; the header title no longer sits next to a
  green checkbox-lookalike.
- Welcome screen rewritten in plain language, with the sample questions as
  labelled cards.
- Clicking a citation opens the evidence drawer if it is closed and
  highlights the source, instead of doing nothing.
- The evidence drawer takes focus when it opens, hands it back when it
  closes, and can be dismissed by clicking the backdrop on desktop too (the
  backdrop was `display: none` above 860px).
- Notices are dismissible and coloured by outcome; upload results read as
  sentences.
- New chat reuses an existing empty chat instead of stacking blank ones.
  Deleting a chat that has questions in it asks first.
- Tokens only auto-scroll the thread when you are already near the bottom,
  so scrolling up to reread something is no longer yanked back down.

### Fixed: console bugs found along the way

- Unsupported claims in the verification report showed a green lamp. The
  red style targeted `.lamp.bad` but the class was only ever put on the
  parent `li`.
- The "verified" badge in the drawer was unstyled: the markup used
  `stamp`, the stylesheet defined `stamp-badge`.
- The gauges never turned amber or red for low scores; the `warn` and `bad`
  fill classes existed but were never applied.
- A stream that closed without an `answer` or `error` event left the turn
  spinning forever with the composer locked. It now falls back to the
  one-shot `/api/chat` request like any other stream failure.
- Questions under 3 characters were sent anyway and came back as a 422 from
  the API. They are now caught in the console with a readable message.
- The pre-paint theme script in `index.html` ran before the `theme-color`
  meta tag existed, so the browser chrome colour never switched to dark.
- `deleteSession` called `setCurrentId` from inside a state updater, which
  React may run twice.
- Source type labels and the live step chips now cover `graph_search`,
  `visual_search`, and the `page`, `graph`, and `calculation` source types.

### Fixed: `rag eval` rows no longer hide which check failed

A row printed FAIL whenever the answer, the citations, or the expected tools
missed, so a correct and cited answer that simply used a different tool
looked identical to a wrong answer. Failing rows now end with
`missed: answer, citations, tools` (whichever applied). Exit codes and the
JSON report are unchanged.

### Added: reasoning under each answer, and avatars

- A **Reasoning** toggle under every answer opens a short list of the steps
  the agent took: which tool, what it searched for, and the one-line reason
  it gave. It is built from the trace the answer already carries, so it
  costs nothing extra. The evidence drawer still has the full detail.
- The assistant has a robot avatar and your messages carry a 🧑‍💻 avatar.
- The verdict chip now counts claims when not all of them held up: "4 of 5
  claims verified" instead of "Verified 80%" next to a claim the verifier
  had rejected. The drawer badge reads "Passed" or "Needs review".
- Claim text in the verification report no longer shows a stray space
  before the full stop where citation markers were stripped.

### Fixed: long chat titles spilled out of the sidebar

Titles are truncated with an ellipsis in every browser. The row button used
flex layout, which Firefox refuses to shrink below its text width, so a long
title ran under the rename and delete buttons and past the sidebar edge with
a horizontal scrollbar.

### Changed: repository ready to publish

- `.gitignore` now also keeps out local editor settings, any
  `.env.*` file except the example, logs, scratch data folders, and
  third-party PDFs. Only the generated Auralis PDF and the two UN
  declaration PDFs are committed.
- `SETUP_GUIDE.md` and `COMMANDS.md` moved to `docs/setup-guide.md` and
  `docs/commands.md`, with their console walkthroughs, Docker notes, and
  install commands brought up to date.
- The hand-drawn `docs/console.svg` is replaced by real light and dark
  screenshots, shown to match the reader's GitHub theme.
- `scripts/check_text.py` enforces the no-em-dash rule and catches
  machine-specific paths in tracked files. CI runs it, and ruff now lints
  `scripts/` too.
- Docker: an `EXTRAS` build argument adds optional dependencies (for example
  `[multilingual]`), `docker-compose.yml` keeps the index and uploads in a
  named volume and documents how to opt in to `.env`, the frontend stage
  installs from the lockfile with `npm ci`, and `.dockerignore` drops local
  PDFs from the build context.

### Docs

- `README.md`: a Quick start heading (the offline badge linked to an anchor
  that did not exist), a Docker section, the new console features, the
  knowledge graph in the tools list, the tokenizer comparison moved into
  Languages, one copy of the graph walk instead of two, and the sample PDF
  paragraph corrected to what the repository actually ships. The test badge
  and CI paragraph still said 123 tests, now 232.
- `CONTRIBUTING.md` lists the offline-guarantee rules directly.
- Console package version synced with the project version.

## 3.10.0

Fixes from running the assistant on Windows against a large, real PDF
corpus with a hosted model, plus a flaky test, an incomplete dependency list,
and stale numbers in the docs.

### Fixed: two Windows-only bugs

The graph store used one shared sqlite3 connection with no explicit lock.
Fine on Linux (`sqlite3.threadsafety == 3`), but a real Windows machine
raised `sqlite3.InterfaceError: bad parameter or other API misuse` under the
parallel-branches test, because Python's implicit cursors interleave across
threads regardless of the library's threadsafety level. `SqliteGraphStore`
now wraps every DB access in a `threading.RLock()`.

Separately, `scripts/quickcheck.py` failed on Windows with
`PermissionError: WinError 32`, because the temp directory couldn't be
deleted while the graph's sqlite connection was still open. Added
`AgenticRAG.close()` (releases the graph connection), called by
`quickcheck.py`, plus `ignore_cleanup_errors=True` on the tempdir as a
backstop.

### Fixed: vector-search previews cut mid-token, causing repeat searches

The vector-search tool's observation text cut passages at a hard 160
characters, sometimes landing mid-number ("EUR 64..."). The model read that
as a truncated or missing source and re-searched three or four more times
chasing a figure it already had, turning a 10-second question into 20 to 65
or more seconds. New `preview()` helper in `tools/base.py` stops at a word
boundary (240-char default) instead, and the observation text now says
outright that these are shortened previews.

### Fixed: a stuck graph extraction could stall ingest for hours, invisibly

A full ingest with `GRAPH_EXTRACTOR=llm` appeared to hang for hours with
`chunks.jsonl` never growing. Root cause: the gateway model had extended
thinking on, and the extractor's `max_tokens=800` was entirely consumed by
thinking with zero JSON text produced. Every chunk's extraction call was
silently failing and falling back to offline rules, because the exception
handler treated a real provider failure exactly like one chunk's reply not
parsing, which is supposed to be harmless, per-chunk noise.

Three fixes:

- The Anthropic client now detects a thinking-only reply (or
  `stop_reason == "max_tokens"`) and raises a clear, named `ProviderError`
  instead of an opaque "Unexpected Anthropic response".
- The extractor now separates "the call itself failed" (loud warning, since
  this degrades the whole run) from "the reply didn't parse" (quiet
  per-chunk fallback, still harmless).
- New `GRAPH_EXTRACT_MAX_TOKENS` setting (default 3000) gives a
  thinking-capable model room to finish its JSON. New
  `GRAPH_MAX_CONSECUTIVE_FAILURES` setting (default 5) gives up on a
  document's remaining chunks after that many failures in a row, since
  `chunks.jsonl` only advances once per whole document and a stuck document
  was previously invisible from outside the process. Any success resets the
  counter, so scattered flakiness never trips it.

### Fixed: offline location extraction matched business language, not places

On real financial-report text, the `_LOCATION` regex fired on any bare "in",
"at", or "from" followed by capitalised words, producing edges like
`Siemens Healthineers -[LOCATED_IN]-> Barclays` (an analyst's employer) or
`-[LOCATED_IN]-> China Revenue` (a table header). Tightened to require an
explicit cue phrase ("headquartered in", "based in", "located in", "founded
in", "offices in", "headquarters in", "plant in", "site in"), narrowed the
capture to one capitalised word plus an optional country, and added a
stoplist of financial-reporting nouns.

That tightening then missed a real sentence: "Auralis Dynamics was founded
in 2019 in Munich, Germany", because the year sits between the cue phrase
and the actual place. Added an optional `(?:\d{4}\s+in\s+)?` clause to skip
a year between the cue and the place. Two regression tests cover both the
noise cases (now zero locations) and the real cases (Munich, Forchheim,
Walldorf all still extracted).

### Fixed: rag reset left the graph pointing at deleted chunks

`rag reset --yes` cleared the vector index but not the knowledge graph, so a
reset followed by a partial re-ingest could leave graph entries pointing at
chunk IDs that no longer existed. `rag reset --yes` now clears the graph
too.

### Fixed: sentence-transformers dimension lookup used a deprecated method

`get_sentence_embedding_dimension()` is being renamed to
`get_embedding_dimension()` in newer sentence-transformers releases; the old
name still works but warns. The multilingual embedder now tries the new
name first and falls back to the old one when it isn't there.

### Added: fontTools dependency

Recommended alongside the existing `cryptography` PDF dependency (same
reasoning: small, pure-Python, pypdf's own suggested companion) to quiet
CFF font-encoding warnings and improve glyph fidelity on some corporate
PDFs. Added to `requirements.txt`.

### Fixed: editable install was missing two dependencies

`cryptography` and `fontTools` were only listed in `requirements.txt`,
never in `pyproject.toml`'s `dependencies`, so the documented editable
install path, and CI, which uses `pip install -e ".[dev]"` and never
touches `requirements.txt`, skipped both. Both are now declared in
`pyproject.toml` too.

### Fixed: a graph-reset test could fail depending on the local environment

`test_reset_clears_the_graph_too` isolated `STORAGE_DIR` and `LLM_PROVIDER`
but not `EMBEDDINGS_PROVIDER`, so it inherited whatever a local `.env` set.
With `EMBEDDINGS_PROVIDER=multilingual` in `.env` and sentence-transformers
not installed, the test raised `SystemExit: 2` instead of testing what it
meant to test, even though the actual `rag reset` behaviour was correct.
Now sets `EMBEDDINGS_PROVIDER=local` explicitly alongside the other two
overrides.

### Lint and docs

- 8 files were missing a trailing newline (`W292`): `cli.py`, `config.py`,
  `embeddings/multilingual.py`, `kg/build.py`, `kg/extractors.py`,
  `llm/anthropic_client.py`, `pipeline.py`, and
  `tests/test_knowledge_graph.py`.
- The last four ruff findings are fixed too, so `ruff check src tests` is
  clean and the blocking lint step in CI passes: `File(...)` in the upload
  endpoint moved to a module-level default (B008), `zip()` got an explicit
  `strict` in `context_assembly.py` and `test_chunking.py` (B905), and a
  quoted return annotation in `config.py` lost its quotes (UP037).
- `README.md` said "123 tests" in two places; it now says 232.
- `COMMANDS.md` had `LLM_PROVIDER` and `rag stats` each listed twice with
  inconsistent details. Merged into one entry each.

Suite: 232, unchanged. All 232 now pass from a clean checkout regardless of
local `.env` contents.

## 3.9.1

### Fixed: blank LLM_TEMPERATURE was ignored by half the pipeline

A gateway model that rejects the temperature parameter would fail with
HTTP 400 even with `LLM_TEMPERATURE=` blank in .env, and the error advised
setting the very thing that was already set.

`LLM_TEMPERATURE=` blank means "leave the field out of every request", and
planning and synthesis honoured it. But verifying, judging, splitting, and
rewriting all want output that cannot drift, so they passed a fixed
`temperature=0.0` of their own. A model that rejects the parameter rejects
0.0 as well, so those four requests still carried it. Planning succeeded and
the run died later in the verifier, which is why the failure looked
unrelated to configuration.

The check now lives in the clients, which already hold the settings, rather
than at the call sites, so no present or future caller can put the field
back. Both clients build every request through one `_payload`, including
streaming and vision, so one guard per client covers every path. A
configured numeric temperature behaves exactly as before.

Four regression tests cover it: every requested value omitted when blank, a
configured value still sent, the deterministic 0.0 preserved when
temperature is allowed, and the same on OpenAI-compatible endpoints.

## 3.9.0

Routing fix, README demo, wider Arabic eval coverage, and a review of the
3.5 to 3.8 changes.

### Fixed: standard numbers routed to the calculator

"Who makes the robot that complies with ISO 3691-4:2023?" reached the
calculator and came back as 3,687, because `3691-4` parses as subtraction.
Expression detection now rejects a numeric run when it is glued to letters or
identifier punctuation, when a word like ISO, EN, version, or SKU introduces
it, or when it is a span of years. A tight hyphen only counts as subtraction
when nothing else in the question suggests a part number, so spaced
subtraction is untouched.

Two things turned up alongside it:

- `12% of 4000` was never detected at all, and `safe_eval` reads `%` as
  modulo, so percentages are now rewritten as `4000 * 12 / 100`.
- `(12 + 8) / 4` arrived as `12 + 8) / 4`, because the pattern starts at a
  digit and left the opening bracket behind. Now rebalanced.

The question routes to `graph_search` end to end, and is the fourth case in
the graph golden set. Regression tests cover both directions: eight
identifier forms that must not reach the calculator, and seven arithmetic
forms that must, each checked through `safe_eval`.

### Added: README demo

A "why graph retrieval" section near the top: the three-hop Munich path from
`rag graph explain`, then a table of the two questions where traversal hits
and similarity misses, with a line on why the comparison is at retrieval
level. A second short section shows the German and Arabic tokenisation
before and after.

### Added: Arabic eval coverage

Two more Arabic cases in the multilingual golden set, over the Arabic sample
document: the safety standard and the runtime. That set is now 8/8 with three
Arabic questions.

I also tried adding an Arabic textbook PDF to the corpus and left it out.
Its Arabic is image-only: 128 pages, 130 embedded images, and about 120
characters of extractable text per page, all of it an English copyright
line. That gives 19 chunks, only 3 distinct after whitespace normalisation,
and no Arabic at all, for 8.5 MB of repository weight. Reading a document
like that needs the vision extra and a vision-capable model.

### Hardening

- SQLite reads under parallel branches were verified rather than assumed:
  `sqlite3.threadsafety` is 3 and 8 threads traversing concurrently raise
  nothing. A test now covers it, and the connection carries a note saying
  why `check_same_thread=False` is safe here.
- Removed an unused test parameter, trimmed three module docstrings that had
  grown past the point of being useful, and added coverage for the unknown
  extractor error and `close()`.
- Edge cases probed across the kg package, language detection, tokenisation,
  and reindex: empty and whitespace input, emoji, zero-width characters,
  malformed alias JSON, missing files, self-loop edges, zero and negative
  hops, and quote-heavy entity names against SQL injection. All handled;
  nothing needed fixing.
- No secrets anywhere, `.env` gitignored and absent from the tree,
  `.env.example` placeholders empty. No TODO, FIXME, debug artifacts, unused
  imports, or dead code.

Suite: 209 to 217.

## 3.8.0

A knowledge graph: entities and relationships extracted at ingest, stored
beside the vector index, and traversed by a new `graph_search` tool, so a
question whose answer is not written in any single passage can be answered
by following relationships instead of ranking similarity.

Naming, because it is a real trap: `agentic_rag.graph` is the orchestration
graph that decomposes a question and merges branches. The knowledge graph is
unrelated and lives in `agentic_rag.kg`. The pipeline attribute is
`knowledge_graph`, because `self.graph` was already taken and assigning over
it failed quietly.

### Added: extraction at ingest

- New `agentic_rag.kg` package: schema, extractors, store, traversal, build.
- Two extractors behind `GRAPH_EXTRACTOR`, registered the way LLM providers
  are. `offline` is patterns and rules, needs no key and no network, and is
  what the tests and a fresh clone use. `llm` asks the configured provider
  for JSON per chunk and reads far more, at one model call per chunk. An
  unparseable reply falls back to the offline rules for that chunk.
- `auto`, the default, stays offline unless `LLM_PROVIDER` was set
  deliberately, so a plain `rag ingest` cannot start spending money because
  Ollama happened to be running.
- Five entity types (COMPANY, PRODUCT, PERSON, STANDARD, LOCATION) and four
  edge types (MADE_BY, SUPPLIES, COMPLIES_WITH, LOCATED_IN), documented in
  the README with the type pairs each edge may join. Entities per chunk are
  capped by `GRAPH_MAX_ENTITIES_PER_CHUNK`, default 12.
- Extraction runs on non-English chunks. Standard numbers survive
  translation, and the alias table carries names across scripts. Surface
  forms are stored as they appeared, so an Arabic chunk records أطلس while
  resolving to the same node as Atlas P2.
- Entity resolution is case and whitespace normalisation plus an exact-match
  alias table (`data/graph_aliases.json`). No fuzzy matching, no
  coreference, no disambiguation. The limits are written down in the README
  rather than half-solved.

### Added: graph store

- SQLite by default, at `storage/index/graph.sqlite3`, from the standard
  library: a fresh clone gets a working graph with no service to install,
  the same bargain the hashed local embedder makes for vectors.
- Writes are idempotent per document, like file ingest. Re-ingesting a
  document replaces what it contributed instead of doubling it.
- Optional Neo4j backend via `GRAPH_STORE=neo4j` and the new `[neo4j]`
  extra. Never required; no test and no default run touches it.

### Added: graph_search and routing

- New `graph_search` tool alongside the existing ones: links the question to
  seed entities, walks k hops (`GRAPH_HOPS`, default 2), and returns the
  traversed path plus the chunks the walked edges came from, so answers stay
  grounded in and cited to source text.
- Routing rule, documented in the README and carried in the planner prompt:
  a question that names something by its relationship, or needs two or more
  facts chained, goes to `graph_search`; a single fact stated in one passage
  stays on `vector_search`. The offline mock routes on a narrow list of
  relational phrases, checked by a test against the golden-set questions so
  it cannot divert them.
- The tool is only offered once the graph holds edges, so the planner never
  sees a tool whose only possible answer is "nothing here".
- `rag graph explain "<question>"` prints seeds, the path hop by hop, the
  nodes reached, and the sentence behind each edge.

### Added: operations

- `rag graph rebuild` rebuilds from stored chunks, no source files needed,
  following the `rag reindex` precedent so chunk ids stay stable and every
  edge keeps its evidence.
- `rag graph stats` reports counts by entity and edge type.
- `GRAPH_EXTRACTION` switches extraction off without touching the rest of
  ingest. Graph failures never break ingest: a chunk the extractor chokes on
  is skipped and counted, a failing document is reported, and the documents
  still land in the index. Rebuild is the recovery path.

### Fixed, found by running the extractor over the real corpus

- A bare "EN" or "CE" was read as a standards family. The numbered families
  now have to carry their number.
- "SOC 2" was stored alongside "SOC 2 Type II". Named standards and aliases
  now claim their span before the looser patterns run, so the longer name
  wins.
- A product and a standard in the same sentence produced a COMPLIES_WITH
  edge with no cue word, which had the robot complying with GDPR from a
  sentence about cloud telemetry. Every edge now needs its cue. A missing
  edge costs a hop; a wrong one sends traversal somewhere false.
- "in Hive" was read as a location. Aliases resolve it to the Atlas Hive
  product instead.

### Tests and eval

- 45 new tests, all offline: schema and edge-domain checks, extractor
  determinism, non-English extraction and script preservation, store
  round-trip and idempotency, two-hop and three-hop traversal, routing
  decisions including a guard that the golden-set questions are not
  diverted, the tool hidden until the graph has edges, ingest surviving a
  failing extractor, and rebuild from stored chunks. Suite: 164 to 209.
- New `eval/golden_set_graph.jsonl`, 3/3 passing with `graph_search` as the
  expected tool. Separate file because CI ingests only `data/sample_docs`.
- `rag eval` stays 8/8 and the multilingual set stays 6/6.

On the before-and-after evidence: comparing at the answer level is
misleading here, because the offline mock writes its answer by quoting
whichever retrieved sentence overlaps the question most, so wording reflects
the mock as much as the retriever. The comparison in the tests is therefore
at the retrieval level. For "Where is the company that makes the Atlas P2
headquartered?" and "Who makes the robot that complies with ISO
3691-4:2023?", traversal returns the passage holding the answer and
similarity search does not. The three-hop Munich question is answered
correctly through traversal, but it is not a discriminating example: its
answer sentence happens to read like the question, so BM25 finds it too.

## 3.7.0

Three separate pieces of work: the API tests are fixed, connecting a real
model is documented and smoke-testable, and the sample corpus grows.

### Fixed: the seven API test failures

`api.py` combined `from __future__ import annotations` with request models
and `UploadFile` defined or imported inside `create_app()`. FastAPI resolves
endpoint annotations against module globals, so those names could not be
resolved: body models were read as query parameters and every POST answered
422. Moved the fastapi and pydantic imports, and the three request models,
to module scope. The module is still only imported inside `rag serve`, so
fastapi stays off the core import path, which a test now checks.

Two of the seven were a different problem hiding behind the first: once the
app built, `test_answers_never_expose_server_filesystem_paths` failed on its
own scaffolding, which constructed `Citation` and `VerificationReport` with
field names those dataclasses stopped using. Fixed in the test, since the
production code and the rest of the suite agree on the current fields.

### Added: connecting a real model

Most of this already existed. The provider registry, the Claude client, the
OpenAI-compatible client that DeepSeek runs through, `LLM_PROVIDER`, and the
`ANTHROPIC_*` and `DEEPSEEK_*` settings were all in place, and a missing key
already raised `ProviderError` with the variable named. What was missing was
proof and documentation:

- New `scripts/smoke_language.py`: one command that asks a German question
  end to end, prints the answer, and reports the language it came back in.
  Exit codes separate a wrong-language answer (1) from an unconfigured
  provider (2) and an empty index (3).
- New tests for DeepSeek, which had none: missing-key error, default
  endpoint, and the environment round-trip for keys, base URLs, and model
  names including the `claude-sonnet-5@default` gateway form.
- README and COMMANDS now document provider setup, that `.env` is
  gitignored, and that model names pass through untouched.
- `LLM_PROVIDER` still defaults to `auto`, so the project runs with no keys.

How the answer-language rule is verified: the offline suite cannot do it.
The mock quotes retrieved sentences rather than writing new ones, so it only
proves a German question routes to German evidence. Two checks cover the
rest. The suite asserts the synthesis prompt carries `ANSWER LANGUAGE:
German` for a German question and stays byte-identical for English, and
`scripts/smoke_language.py` checks a real model's answer against the
question's language over the network.

### Added: expanded sample corpus

Five curated PDFs in `data/sample_pdfs/`, about 3.4 MB: SAP Q1 2024 and
Siemens Healthineers Q3 FY2026 quarterly statements, Attention Is All You
Need, and the Universal Declaration of Human Rights in German and Chinese.

All six PDFs in the folder extract text and produce chunks, so none needs
the vision path. Counts: attention 54, SAP 47, Siemens 40, UDHR German 16,
UDHR Chinese 8, Auralis 3. The two financial statements are table-heavy and
still extract cleanly, because the figures are real text rather than pixels.

- Fixed, found by the Chinese PDF: text extraction puts a space between
  every Han character, so the index stored single characters while a typed
  query produced bigrams and the two never matched. Tokenisation now closes
  whitespace that has a CJK character on both sides. Other scripts are
  untouched, and English tokenisation is still byte-identical to the
  original rule (re-verified over the English corpus and 125k fuzz cases).
- New `eval/golden_set_multilingual.jsonl`: six questions over the expanded
  corpus, German, Arabic, Chinese, and English, 6/6 passing. It is a
  separate file because the default set and CI ingest only
  `data/sample_docs`; adding these there would have broken CI.
- The Arabic case runs over the existing `data/sample_docs_multilingual`
  Arabic document, because the attached set contains no Arabic PDF.
- README notes that more PDFs can be dropped into `data/sample_pdfs` and
  picked up with `rag ingest`, and that `rag reindex` will not see them.

Test suite grows to 163, all passing.

## 3.6.0

Multilingual retrieval and answers. English is unchanged: the tokeniser was
verified to produce identical output on ASCII text, so English retrieval,
the deterministic mock, and the golden-set eval all behave exactly as before.

- New: Unicode-aware tokenisation for BM25 and for query time. German umlauts
  and eszett survive instead of splitting words into fragments, and Arabic and
  Urdu produce real tokens where they previously produced none at all.
- New: Chinese and Japanese are segmented into overlapping bigrams, since
  neither is written with spaces to split on. Index and query use the same
  rule so the two sides match.
- New: language detection with per-language stopwords for English, German,
  Arabic, Chinese, and Urdu. Script decides first, stopword hits break the tie
  between Urdu and Arabic and between German and English. Short queries with
  no signal fall back to English.
- New: `EMBEDDINGS_PROVIDER=multilingual` with `MULTILINGUAL_EMBEDDING_MODEL`,
  defaulting to `intfloat/multilingual-e5-small`. The e5 query and passage
  prefixes are applied automatically, since the family needs them.
- New: `rag reindex` and `scripts/reindex.py` rebuild the vector store and
  BM25 from the chunks already stored, which is what makes an embedder change
  survivable. Chunk ids are preserved so citations still line up.
- New: `ANSWER_LANGUAGE`, `auto` by default, follows the language of the
  question. The synthesis prompt carries the rule, and names the language
  outright for non-English questions.
- Fixed: the local hashed embedder had its own copy of the ASCII-only token
  rule, so the default embedder produced empty vectors for non-Latin text. It
  now shares the one tokeniser.
- Test suite grows to 156 tests, 33 of them new.

Known issue, pre-existing and not related to this change: the seven tests in
`tests/test_api.py` fail against current FastAPI releases. `api.py` combines
`from __future__ import annotations` with request models defined inside
`create_app()`, so the body annotations resolve to unresolvable forward
references and FastAPI reads them as query parameters.

## 3.5.0

Fixes from a code review, plus the page images they made visible.

- Fixed: `rag reset` cleared the text index but left page records, embeddings,
  and rendered images on disk, which duplicated pages on the next ingest.
- Fixed: answers returned by the API carried the absolute server path of each
  page image. Paths now stay server-side and clients get a guarded
  `/api/page-image` URL instead.
- Fixed: a tab closed mid-answer left a turn marked streaming in browser
  storage, which kept the composer disabled after a reload.
- Fixed: the page manifest was rewritten once per page during ingest instead
  of once per document.
- New: cited pages show as thumbnails in the console, so a chart the answer
  relies on is visible next to the claim.
- README carries technology badges, and COMMANDS.md documents every CLI
  command, flag, API route, and make target the code defines.
- Test suite grows to 123 tests.

## 3.4.0

- Page-image retrieval, the ColPali path: page images are embedded directly
  and ranked with late interaction (MaxSim) through a new visual_search tool.
  VISUAL_RETRIEVER=description|colpali, with colSmol as the CPU-friendly
  default model. The scoring maths is pure NumPy and tested without torch.
- Retrieved pages reach synthesis as images, so a vision-capable model reads
  the actual chart instead of a description of it.
- A demo PDF ships with the repository, generated by
  scripts/make_sample_pdf.py: prose, an unlabelled bar chart, a table, a
  schematic, and a trend line. Its quarterly figures exist only as bar
  heights, and a test asserts text extraction cannot recover them.
- Page index persists records and per-page embeddings beside the text index,
  with a clear message when it is corrupt.
- New colpali extra, kept separate from the small vision extra.
- Test suite grows to 119 tests.

## 3.3.0

- DeepSeek provider, registered alongside Ollama, Claude, OpenAI, and Azure.
- Per-role model routing driven entirely from .env: LLM_MODEL_FAST and
  LLM_MODEL_DEEP split the mechanical roles from the writing ones, and
  LLM_MODEL_<ROLE> pins any single role. rag stats and /api/health print the
  resolved map. With one model configured, behaviour is unchanged.
- PDF page-image understanding: pages are rendered and described by a
  vision-capable model so charts, schematics, and layout-heavy tables are
  indexed and citable as "page N (visual)". PDF_VISION=off|auto|on, with auto
  only spending a call when text extraction came back thin.
- Vision support on the Anthropic and OpenAI-compatible clients, plus a
  deterministic mock so the path is testable offline.
- Deployment guide rewritten for current free tiers, including why a private
  model endpoint cannot resolve from a public host.
- Test suite grows to 108 tests.

## 3.2.0

- Console rebuilt: conversation sidebar with rename and delete kept in the
  browser, chat bubbles with avatars and timestamps, per-answer verdict chip,
  copy button, and a slide-over evidence drawer holding the verification
  strip, sources, and trace.
- Light and dark themes that follow the system by default, with no flash on
  load, plus a full mobile layout (drawer sidebar, full-screen evidence
  sheet, safe-area padding).
- Evaluation scores tool correctness against each case's expected tools and
  breaks results down by category. Golden cases now carry category,
  difficulty, and expected tools.
- Second chunking strategy: CHUNK_STRATEGY=length gives fixed windows for
  text with no headings, alongside the structure-aware default.
- COMMANDS.md with the complete Windows and Linux command sequences, and
  docs/deployment.md covering mobile access and hosting.
- Test suite grows to 93 tests.

## 3.1.0

- Parallel retrieval graph: a question is decomposed into independent
  sub-questions, each researched by its own agent loop on its own thread,
  then merged. Single-part questions run inline and behave exactly as before.
- Per-branch state isolation, a step budget shared across branches behind a
  lock, per-branch error containment, and a bounded retry for empty branches.
- Provider registry (`llm/providers.py`): Claude, OpenAI, Azure, Ollama, and
  any compatible endpoint, each one registered builder function.
- `LLM_MODEL` names the model for whichever provider is active and is sent to
  the endpoint untouched, so gateway-specific names work.
- Blank `LLM_TEMPERATURE=` omits the parameter for models that reject it.
- Streaming for Claude and OpenAI, so hosted providers stream like Ollama.
- `rag models` lists what the configured endpoint actually serves.
- Setup failures become ProviderError with the fix in the message.
- Console shows parallel branches as lanes with per-step branch tags.
- docs/architecture.md covers the graph, state design, and concurrency work.
- Test suite grows to 89 tests.

## 3.0.0

- Conversational console: multi-turn chat with memory. Follow-ups are
  rewritten into standalone questions (real models, while the mock passes through
  for deterministic offline runs) and shown as "interpreted as".
- Live streaming end to end: the pipeline emits rewrite, stage, step,
  synthesis_start, and token events, and /api/chat/stream serves them as SSE and
  the console renders the agent working in real time, with a non-stream
  fallback.
- Hybrid retrieval by default: BM25 keyword scores fused with vector
  similarity through reciprocal rank fusion (RETRIEVAL_MODE=hybrid|vector|bm25).
- Document upload from the console (/api/upload): type whitelist, filename
  sanitising, size cap, immediate indexing.
- LLM-as-judge evaluation: `rag eval --judge` adds faithfulness and relevance
  scores (LLM judge with real models, deterministic lexical scoring offline).
- Optional API auth: API_AUTH_TOKEN gates every endpoint except /api/health.
- Installable console (PWA): manifest plus generated icons
  (scripts/make_icons.py, NumPy only), so the console installs to a phone or
  desktop home screen.
- docker-compose.yml, CONTRIBUTING.md, SECURITY.md, answer export as JSON.
- Component-level health: /api/health probes Ollama live, reads the index,
  and checks the catalog and search dependency, reporting degraded when
  anything is down.
- Hardened error paths: bad numeric .env values fail with the variable
  name, a corrupt index says to run rag reset, streaming connection
  failures carry the URL, and one unreadable file no longer sinks an
  ingest batch.
- Test suite grows to 66 tests.

## 2.0.0

- React (Vite) web console replaces the Streamlit app: answer with clickable
  citations, verification gauges with claim-by-claim verdicts, source cards,
  the agent trace, and stage timings.
- Ollama becomes the default real LLM. LLM_PROVIDER=auto detects a local
  server, lists the installed models, and picks the most JSON-reliable one.
  The deterministic offline mock remains the fallback and the CI provider,
  so nothing ever requires a key.
- Web search is on by default through keyless DuckDuckGo (SEARCH_PROVIDER=ddgs).
  The agent decides per question whether the web is needed.
- API endpoints moved under /api with CORS for the Vite dev server. After
  `npm run build`, `rag serve` hosts the console and the API on one port.
- Docker builds the console in a node stage and serves everything on :8000.
- New tests: Ollama detection and fallback, the API contract, and the
  deterministic web-search path (38 tests total).

## 1.0.0

- Initial release: agent orchestrator with a provider-agnostic JSON protocol,
  four tools (vector_search, web_search, knowledge_base, calculator), context
  assembly with reciprocal rank fusion, claim-level verification with a refine
  loop, CLI, FastAPI, golden-set eval, and the offline mock provider.