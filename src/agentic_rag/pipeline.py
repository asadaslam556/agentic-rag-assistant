"""The end-to-end pipeline, mirroring the architecture stage by stage:

user question -> agent orchestrator (plans tool calls, may re-query)
             -> tools (vector search | web search | structured APIs)
             -> context assembly (dedupe, fuse, pack)
             -> synthesis (grounded answer with [n] citations)
             -> verification (claim-level groundedness)
             -> refine loop when verification fails
             -> Answer with citations, verification report, and trace
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from time import perf_counter

from agentic_rag.agent.orchestrator import Orchestrator
from agentic_rag.agent.prompts import (
    REWRITE_SYSTEM,
    SYNTHESIZE_SYSTEM,
    build_rewrite_prompt,
    build_synthesis_prompt,
)
from agentic_rag.assembly.context_assembly import assemble
from agentic_rag.config import Settings
from agentic_rag.core.lang import detect_language
from agentic_rag.core.types import Answer, Citation, Evidence
from agentic_rag.embeddings import get_embedder
from agentic_rag.graph import GraphRunner
from agentic_rag.ingestion.chunking import get_chunker
from agentic_rag.ingestion.loaders import discover_files, load_document
from agentic_rag.llm.router import ModelRouter
from agentic_rag.retrieval.colpali import build_encoder
from agentic_rag.retrieval.hybrid import HybridSearcher
from agentic_rag.retrieval.late_interaction import PageIndex, PageRecord
from agentic_rag.retrieval.vector_store import VectorStore
from agentic_rag.tools import build_default_tools
from agentic_rag.verification.verifier import Verifier, feedback_from_report

_MARKER = re.compile(r"\[(\d{1,2})\]")


class AgenticRAG:
    """Facade wiring every component together from a Settings object."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()
        self.embedder = get_embedder(self.settings)
        self.store = VectorStore(self.settings.index_path, self.embedder)
        self.searcher = HybridSearcher(self.store, self.settings.retrieval_mode)
        self.pages = PageIndex(self.settings.storage_path / "pages")
        self.encoder = build_encoder(self.settings)
        self._chunk_index: dict | None = None
        self._graph_extractor = None
        # named for what it is: `self.graph` is already the orchestration
        # runner, and the two are unrelated
        self.knowledge_graph = self._open_graph()
        self.tools = build_default_tools(
            self.settings,
            self.searcher,
            page_index=self.pages,
            embedder=self.embedder,
            encoder=self.encoder,
            graph_store=self.knowledge_graph,
            chunk_lookup=self.chunk_by_id,
        )
        self.router = ModelRouter(self.settings)
        # each stage asks the router for its own model, which is the same
        # client unless the two-tier settings are in play
        self.llm = self.router.default_client()
        self.orchestrator = Orchestrator(
            self.router.client_for("plan"), self.tools, self.settings
        )
        self.graph = GraphRunner(
            self.router.client_for("decompose"), self.orchestrator, self.settings
        )
        self.verifier = Verifier(self.router.client_for("verify"), self.settings)

    # ------------------------------------------------------------- ingestion

    def _open_graph(self):
        """The graph store, or None when it cannot be opened.

        A graph that will not open costs the graph_search tool, not the
        whole assistant, so this never raises into startup.
        """
        try:
            from agentic_rag.kg.store import get_graph_store

            return get_graph_store(self.settings)
        except Exception:  # noqa: BLE001 - retrieval must still work without it
            return None

    def close(self) -> None:
        """Release the graph connection.

        Only matters on Windows, where an open SQLite file cannot be
        deleted, so a pipeline built over a temporary directory blocks its
        own cleanup.
        """
        graph = getattr(self, "knowledge_graph", None)
        if graph is not None:
            try:
                graph.close()
            except Exception:  # noqa: BLE001 - closing must not raise
                pass

    def chunk_by_id(self, chunk_id: str):
        """Look up one chunk, for tools that hold chunk ids rather than text."""
        if self._chunk_index is None or len(self._chunk_index) != self.store.count:
            self._chunk_index = {chunk.id: chunk for chunk in self.store.chunks()}
        return self._chunk_index.get(chunk_id)

    def _build_graph(self, doc_id: str, chunks: list) -> None:
        """Add one document's entities and edges. Never fatal to ingest.

        A per-document cap on repeated failures matters as much as the
        try/except: without one, a document whose chunks each hit the same
        slow or hanging provider (a stuck connection outlasting the request
        timeout, a rate limit that never clears) can burn the whole ingest
        run one retried chunk at a time, invisibly, since chunks.jsonl is
        only written once per document and does not move while this runs.
        Giving up on the document after a few losses in a row keeps a bad
        provider from turning into a stalled ingest; `rag graph rebuild`
        with a working provider is the recovery path.
        """
        if not self.settings.graph_extraction or self.knowledge_graph is None:
            return
        try:
            from agentic_rag.kg.build import build_for_chunks

            if self._graph_extractor is None:
                from agentic_rag.kg.extractors import build_extractor

                self._graph_extractor = build_extractor(self.settings)
            build_for_chunks(
                self.knowledge_graph,
                self._graph_extractor,
                doc_id,
                chunks,
                max_consecutive_failures=self.settings.graph_max_consecutive_failures,
            )
        except Exception as exc:  # noqa: BLE001 - a document indexed without
            # its edges is recoverable with `rag graph rebuild`; a document
            # lost to a graph failure is not
            print(f"note: graph extraction failed for {doc_id}: {str(exc)[:200]}", file=sys.stderr)

    def ingest(self, path: str | Path) -> dict:
        files = discover_files(Path(path))
        existing = self.store.doc_ids()
        added_files = 0
        skipped_files = 0
        chunks_added = 0
        errors: list[dict] = []
        for file in files:
            try:
                document = load_document(file)
                if document.id in existing:
                    skipped_files += 1
                    continue
                chunks = get_chunker(self.settings.chunk_strategy)(
                    document,
                    target_chars=self.settings.chunk_target_chars,
                    overlap_chars=self.settings.chunk_overlap_chars,
                )
                chunks.extend(self._index_pages(file, document, len(chunks)))
                chunks_added += self.store.add_chunks(chunks)
                self._build_graph(document.id, chunks)
                added_files += 1
            except Exception as exc:
                # A corrupt PDF or unreadable file should not sink the batch.
                # The reason goes to stderr, where the CLI user sees it; the
                # returned stats only name the file, because the API sends
                # them to the client as they are.
                print(f"note: could not read {file.name}: {str(exc)[:300]}", file=sys.stderr)
                errors.append({"file": file.name, "error": "could not be read, see the server log"})
        stats = {
            "files_added": added_files,
            "files_skipped_existing": skipped_files,
            "chunks_added": chunks_added,
            **self.store.stats(),
        }
        if errors:
            stats["errors"] = errors
        return stats

    # ----------------------------------------------------------------- ask

    def _index_pages(self, file: Path, document, start_position: int) -> list:
        """Render a PDF's pages once, then use them for whatever is switched on.

        Two independent things can want page images: descriptions written by
        a vision model, which become ordinary searchable chunks, and ColPali
        embeddings, which power visual_search. Rendering is the expensive
        part, so it happens once and feeds both. Any failure is reported and
        skipped: page images are a bonus, never a reason to lose a document.
        """
        if file.suffix.lower() != ".pdf":
            return []
        from agentic_rag.ingestion.pdf_vision import (
            describe_pages,
            page_chunks,
            vision_enabled,
        )
        from agentic_rag.ingestion.pdf_vision import render_pages as render

        llm = self.router.client_for("vision")
        page_count = document.text.count("\f") + 1
        wants_description = vision_enabled(self.settings, llm, document.text, page_count)
        wants_colpali = self.encoder is not None
        if not (wants_description or wants_colpali):
            return []

        try:
            images = render(file, self.settings.vision_max_pages, self.settings.vision_scale)
        except Exception as exc:
            print(f"note: page images skipped for {file.name}: {exc}", file=sys.stderr)
            return []
        if not images:
            return []

        descriptions = describe_pages(llm, images) if wants_description else [""] * len(images)

        vectors = None
        if wants_colpali:
            try:
                vectors = self.encoder.embed_pages(images)
            except Exception as exc:
                print(f"note: page embeddings skipped for {file.name}: {exc}", file=sys.stderr)
                vectors = None

        image_dir = self.settings.storage_path / "pages" / "images"
        image_dir.mkdir(parents=True, exist_ok=True)
        for number, image in enumerate(images, 1):
            page_id = f"{document.id}#page{number}"
            image_path = image_dir / f"{page_id.replace('#', '_')}.png"
            image_path.write_bytes(image)
            self.pages.add(
                PageRecord(
                    id=page_id,
                    doc_id=document.id,
                    title=document.title,
                    source_path=document.path,
                    page_number=number,
                    image_path=str(image_path),
                    description=descriptions[number - 1] if wants_description else "",
                ),
                vectors[number - 1] if vectors is not None else None,
                flush=False,
            )
        self.pages.save()

        if not wants_description:
            return []
        return page_chunks(document, descriptions, start_position)

    def ask(self, question: str, on_event=None) -> Answer:
        """One-shot question: chat() with an empty history."""
        return self.chat(question, history=None, on_event=on_event)

    def chat(
        self,
        question: str,
        history: list[dict] | None = None,
        on_event=None,
    ) -> Answer:
        """Answer a question, optionally continuing a conversation.

        history holds previous turns as [{"question": ..., "answer": ...}].
        Follow-ups are rewritten into standalone questions first (real
        models only; the mock passes questions through so offline runs
        stay deterministic), and the history is given to synthesis as
        context that must never be cited.

        on_event, when given, receives live pipeline events as
        callback(name, payload): rewrite, stage, step, synthesis_start,
        and token. The streaming API and the console are built on it.
        """
        history = history or []
        emit = on_event if on_event is not None else (lambda name, payload: None)
        timings: dict[str, int] = {}
        t_start = perf_counter()

        pipeline_question = self._rewrite(question, history)
        rewritten = pipeline_question if pipeline_question != question else ""
        if rewritten:
            emit("rewrite", {"question": rewritten})

        t0 = perf_counter()
        graph_result = self.graph.run(pipeline_question, emit=emit)
        evidence, steps = graph_result.evidence, graph_result.steps
        timings["retrieve_ms"] = int((perf_counter() - t0) * 1000)

        emit("stage", {"name": "assembling"})
        t0 = perf_counter()
        packed = assemble(pipeline_question, evidence, self.embedder, self.settings)
        timings["assemble_ms"] = int((perf_counter() - t0) * 1000)

        emit("stage", {"name": "synthesizing"})
        t0 = perf_counter()
        draft = self._synthesize(
            pipeline_question, packed, history=history, emit=on_event, attempt=0
        )
        timings["synthesize_ms"] = int((perf_counter() - t0) * 1000)

        emit("stage", {"name": "verifying"})
        t0 = perf_counter()
        report = self.verifier.verify(pipeline_question, draft, packed)
        attempts = 0
        while not report.passed and attempts < self.settings.max_refine_attempts:
            attempts += 1
            emit("stage", {"name": "refining"})
            feedback = feedback_from_report(report)
            draft = self._synthesize(
                pipeline_question,
                packed,
                feedback=feedback,
                history=history,
                emit=on_event,
                attempt=attempts,
            )
            report = self.verifier.verify(pipeline_question, draft, packed)
        timings["verify_ms"] = int((perf_counter() - t0) * 1000)
        timings["total_ms"] = int((perf_counter() - t_start) * 1000)

        return Answer(
            question=question,
            text=draft,
            citations=self._citations(draft, packed),
            evidence=packed,
            verification=report,
            steps=steps,
            attempts=attempts,
            timings_ms=timings,
            rewritten_question=rewritten,
            sub_questions=graph_result.sub_questions,
            branches=graph_result.branches,
        )

    def _evidence_images(self, evidence: list[Evidence]) -> list[bytes]:
        """Page images for the cited pages, capped so a prompt stays sane."""
        images: list[bytes] = []
        for item in evidence:
            if len(images) >= self.settings.vision_context_pages:
                break
            path = getattr(item, "image_path", "")
            if not path:
                continue
            try:
                images.append(Path(path).read_bytes())
            except OSError:
                continue
        return images

    def _rewrite(self, question: str, history: list[dict]) -> str:
        rewriter = self.router.client_for("rewrite")
        if not history or rewriter.is_mock:
            return question
        try:
            response = rewriter.complete(
                REWRITE_SYSTEM,
                [{"role": "user", "content": build_rewrite_prompt(question, history)}],
                temperature=0.0,
                max_tokens=200,
            )
        except Exception:
            return question
        text = response.text.strip()
        candidate = text.splitlines()[0].strip().strip('"') if text else ""
        if 5 <= len(candidate) <= 400:
            return candidate
        return question

    # -------------------------------------------------------------- helpers

    def _answer_language(self, question: str) -> str:
        """Language the answer should be written in.

        ANSWER_LANGUAGE=auto, the default, follows the question. Any other
        value pins every answer to that language.
        """
        configured = self.settings.answer_language
        if configured and configured != "auto":
            return configured
        return detect_language(question)

    def _synthesize(
        self,
        question: str,
        evidence: list[Evidence],
        feedback: str = "",
        history: list[dict] | None = None,
        emit=None,
        attempt: int = 0,
    ) -> str:
        prompt = build_synthesis_prompt(
            question,
            evidence,
            feedback=feedback,
            history=history,
            language=self._answer_language(question),
        )
        messages = [{"role": "user", "content": prompt}]

        # when a retrieved page is in the context and the model can see, send
        # the page itself rather than making it work from a description
        images = self._evidence_images(evidence)
        if images and getattr(self.llm, "supports_vision", False):
            try:
                response = self.llm.complete_vision(
                    SYNTHESIZE_SYSTEM,
                    prompt,
                    images,
                    temperature=self.settings.llm_temperature,
                    max_tokens=900,
                )
                text = response.text.strip()
                if emit is not None:
                    emit("synthesis_start", {"attempt": attempt})
                    emit("token", {"text": text})
                return text
            except Exception as exc:
                print(f"note: page images not used for this answer: {exc}", file=sys.stderr)

        if emit is None:
            response = self.llm.complete(
                SYNTHESIZE_SYSTEM,
                messages,
                temperature=self.settings.llm_temperature,
                max_tokens=900,
            )
            return response.text.strip()
        emit("synthesis_start", {"attempt": attempt})
        parts: list[str] = []
        for piece in self.llm.complete_stream(
            SYNTHESIZE_SYSTEM,
            messages,
            temperature=self.settings.llm_temperature,
            max_tokens=900,
        ):
            parts.append(piece)
            emit("token", {"text": piece})
        return "".join(parts).strip()

    @staticmethod
    def _citations(answer: str, evidence: list[Evidence]) -> list[Citation]:
        citations: list[Citation] = []
        seen: set[int] = set()
        for match in _MARKER.finditer(answer):
            marker = int(match.group(1))
            if marker in seen or not (1 <= marker <= len(evidence)):
                continue
            seen.add(marker)
            item = evidence[marker - 1]
            citations.append(
                Citation(
                    marker=marker,
                    evidence_id=item.id,
                    title=item.title,
                    source_type=item.source_type,
                    source_ref=item.source_ref,
                    url=item.url,
                )
            )
        return citations
