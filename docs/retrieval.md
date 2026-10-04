# Retrieval and context assembly

How the corpus is searched, and how evidence from every tool call becomes the numbered sources the
model cites.

Code: `src/agentic_rag/retrieval/` and `src/agentic_rag/assembly/context_assembly.py`.

## Hybrid search

`vector_search` runs `HybridSearcher` (`retrieval/hybrid.py`). With `RETRIEVAL_MODE=hybrid` (default)
it fetches BM25 keyword hits and vector hits (at least 8 of each) and fuses the two rankings with
reciprocal rank fusion. `vector` and `bm25` use one method alone.

Rank fusion is why hybrid retrieval needs no score calibration. BM25 scores and cosine similarities
live on different scales, so instead of adding them, RRF adds `1 / (60 + rank)` from each list. A chunk
ranked well by both wins, and a chunk only one method found still gets in. BM25 catches exact terms
such as "ISO 3691-4" that an embedder can rank below a paraphrase; vectors catch the paraphrase.

The BM25 index is built lazily on the first search and rebuilt when the chunk count changes. That
build is behind a lock, because parallel branches can search at the same moment.

## Context assembly

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="diagrams/context-assembly.dataflow.dark.png">
  <img alt="Context assembly: tool evidence is filtered for injections and deduplicated, scored by rank fusion and by relevance from the embedder or a reranker, fused as 0.6 relevance plus 0.4 RRF, and packed into numbered sources for synthesis and the verifier" src="diagrams/context-assembly.dataflow.png">
</picture>

<sub>Interactive version: [`diagrams/context-assembly.dataflow.html`](diagrams/context-assembly.dataflow.html).</sub>

`assemble()` runs over the merged evidence of every branch and every tool:

1. **Filter.** `core/injection.py` replaces sentences that try to instruct the model with a visible
   `[removed: ...]` marker. Text with no match comes back unchanged, character for character, which
   keeps English retrieval and the eval byte-identical.
2. **Deduplicate.** Evidence with the same normalised text is merged, keeping the best raw score.
3. **Rank fusion across tool calls.** Within each tool call, evidence is sorted by its rank and
   scores `1 / (60 + position)`.
4. **Relevance.** Each candidate is scored against the question. By default the embedder embeds
   question and passage separately and compares them. `RERANKER=cross-encoder` (needs
   `pip install -e ".[rerank]"`) reads the pair together instead; if it raises, assembly falls back to
   the embedder with a note on stderr, so a reranker problem costs precision, never an answer.
5. **Fuse.** `0.6 * relevance + 0.4 * normalised RRF`. The reranker replaces only the relevance term,
   so a strong hit from one tool still counts.
6. **Pack.** Highest fused score first, greedily, into `CONTEXT_TOKEN_BUDGET` (2200 tokens). The top
   item always fits, an item that would overflow is skipped so a smaller one may still fit, and at most
   12 sources are kept.

The packed order is final: the sources the model sees as `[1]`, `[2]`, `[3]` are the numbers the
console links to and the [verifier](streaming.md#the-pass-rule) checks against.

`RERANKER_MODEL` defaults to `cross-encoder/ms-marco-MiniLM-L-6-v2` (English). For other languages,
`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` is an option. The bundled golden set already scores 11/11
without a reranker, so measure on your own corpus before relying on one.

## Languages

Retrieval works beyond English, and English behaves exactly as it did before.

- Tokenisation (`core/textutils.py`) keeps letters from any script, so umlauts survive and Arabic and
  Urdu produce real tokens. English output is byte-identical to the earlier ASCII-only rule;
  `tests/test_multilingual.py` keeps a copy of the old rule to check against.
- Chinese and Japanese runs are indexed as overlapping bigrams, on both the index and the query side.
- `core/lang.py` detects the language from the script first, then from stopword hits, and leans
  towards English on weak evidence. English, German, Arabic, Chinese, and Urdu ship with stopword
  lists.
- Answers come back in the language of the question; `ANSWER_LANGUAGE` pins one instead.

For a genuinely multilingual corpus, the hashed `local` embedder only matches shared tokens. Switch to
the multilingual model and rebuild:

```bash
pip install -e ".[multilingual]"
# in .env: EMBEDDINGS_PROVIDER=multilingual
rag reindex
```

## Known issue

Evidence ids and call ids restart in every parallel branch (`agent/orchestrator.py`), and assembly
keys rank fusion by id and groups by call id. A split question can therefore merge scores of unrelated
evidence. The mock never splits questions, so the offline tests do not exercise it.
