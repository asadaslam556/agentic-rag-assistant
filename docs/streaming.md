# Answer turn and streaming

What happens to one question from the moment it arrives until the answer is returned, and the live
events the console receives along the way.

Code: `AgenticRAG.chat` in `src/agentic_rag/pipeline.py`, `/api/chat/stream` in `src/agentic_rag/api.py`.

## The stages of one turn

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="diagrams/answer-turn.architecture.dark.png">
  <img alt="One answer turn: question, planning, assembling, synthesizing, verifying, passed. Empty branches go through retrying; a failed check goes through refining and, if it still fails, the answer is returned marked Needs review" src="diagrams/answer-turn.architecture.png">
</picture>

<sub>Interactive version: [`diagrams/answer-turn.architecture.html`](diagrams/answer-turn.architecture.html).</sub>

1. **Rewrite.** In a conversation, a follow-up such as "and what does it cost?" is rewritten into a
   standalone question from the recent turns. This needs a real model: with the mock, or with no
   history, the question is used as it is. A changed question is reported as a `rewrite` event.
2. **planning.** The [orchestrator](agent.md) decomposes the question and runs the agent loop per
   branch. Empty branches can add a `retrying` stage.
3. **assembling.** [Context assembly](retrieval.md) turns all evidence into numbered sources.
4. **synthesizing.** The model writes the answer from the numbered sources only, citing them as `[1]`
   or `[2][3]`. When a cited page image is in the context and the model can see, the image itself is
   attached (up to `VISION_CONTEXT_PAGES`, 2).
5. **verifying.** The answer is split into claims and each is checked against the sources it cites.
6. **refining.** If the check fails, the answer is rewritten with the failing claims as feedback and
   checked again, up to `MAX_REFINE_ATTEMPTS` (1) times.

### The pass rule

`verification/verifier.py` passes an answer when **groundedness is at least `MIN_GROUNDEDNESS` (0.7)
and citation coverage is at least 0.5**. Groundedness is the share of claims the cited sources
support; citation coverage is the share of claims that cite anything.

The fixed answer "The available sources do not contain enough information to answer this question."
always passes: abstaining is the correct outcome when the evidence is missing, and a verifier that
punished it would push the model towards guessing.

Every answer is returned. One that still fails after refining is shown in the console as
**Needs review** rather than hidden.

Claims are checked lexically when the mock is answering and with a dedicated model call otherwise
(`VERIFIER_MODE=auto`). Set `lexical` or `llm` to force one.

## The event stream

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="diagrams/chat-stream.sequence.dark.png">
  <img alt="Sequence: the console posts to /api/chat/stream, the API starts the pipeline on a worker thread with an event callback, and stage, step, token, and answer events flow back over server-sent events" src="diagrams/chat-stream.sequence.png">
</picture>

<sub>Interactive version: [`diagrams/chat-stream.sequence.html`](diagrams/chat-stream.sequence.html).</sub>

`POST /api/chat/stream` starts the pipeline on a worker thread with an event callback that puts every
event on a queue, and streams the queue as server-sent events (`event: <name>` then `data: <json>`).

| Event | Payload | When |
|---|---|---|
| `rewrite` | `{"question"}` | A follow-up was rewritten |
| `decompose` | `{"sub_questions"}` | The question was split into more than one part |
| `stage` | `{"name"}` | `planning`, `retrying`, `assembling`, `synthesizing`, `verifying`, `refining` |
| `step` | one agent step, with its `branch` | After every tool call or finish |
| `branch_error` | `{"branch", "message"}` | One branch raised; the others continue |
| `synthesis_start` | `{"attempt"}` | Before the first token of each draft, so a redraft can replace the text |
| `token` | `{"text"}` | Each piece of the streamed answer |
| `answer` | the full answer payload | Once, at the end |
| `error` | `{"message"}` | The pipeline failed, or no event arrived for 300 seconds |
| `done` | `{}` | The stream is over |

Because branches push their steps as they happen, parallel work reports live and interleaved: two
`plan` steps arrive back to back, then two `vector_search` steps, because both branches are working at
once.

If a proxy buffers or drops the stream, the console falls back to one plain `POST /api/chat` and
renders the same answer without the live view (`frontend/src/App.jsx`).

These event names and the framing are consumed by the console, so a change has to be made on both
sides together.

## Related

- [API reference](api.md) for the request and answer payloads.
- [Upload and ingest over the API](ingestion.md#uploading-through-the-console).
