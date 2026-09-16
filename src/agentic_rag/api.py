"""REST API around the pipeline (FastAPI), plus the built web console.

Run it with:  rag serve --port 8000
Endpoints live under /api and interactive docs at /docs. When the React
frontend has been built (frontend/dist exists), it is served at the
root path, so one process hosts both the API and the console.

Security model: this is a local-first tool. The API is open by default
on localhost. Setting API_AUTH_TOKEN requires `Authorization: Bearer
<token>` on every endpoint except /api/health, which is the switch to
flip before exposing the server beyond your machine. /api/ingest reads
paths on the server machine by design; /api/upload is the remote-safe
way to add documents.
"""

from __future__ import annotations

import json
import queue
import threading
from pathlib import Path

from agentic_rag import __version__
from agentic_rag.config import Settings
from agentic_rag.ingestion.loaders import SUPPORTED_EXTENSIONS
from agentic_rag.pipeline import AgenticRAG

# FastAPI resolves endpoint annotations against this module's globals. With
# `from __future__ import annotations` above, every annotation is a string, so
# a name that only exists inside create_app() cannot be resolved: FastAPI then
# treats a request body model as a query parameter and every POST returns 422.
# Importing here, and defining the request models here, keeps the names
# resolvable. This module is never on the core import path (the CLI imports it
# only inside `rag serve`), so fastapi stays out of `import agentic_rag`.
try:
    from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("The API needs fastapi installed: pip install fastapi uvicorn") from exc

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    history: list[dict] = Field(
        default_factory=list,
        max_length=12,
        description='Previous turns: [{"question": ..., "answer": ...}]',
    )


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


class IngestRequest(BaseModel):
    path: str = Field(description="File or directory on the server to ingest")


# File(...) just builds a stateless marker FastAPI reads to know a parameter
# comes from the request's multipart file section, it carries no per-request
# state. Building it once here means the /api/upload default below is a name
# lookup, not a function call, which is what ruff's B008 rule wants: calling
# a function in a default is normally a real bug (the default only runs once,
# at import time, so a mutable result would be shared across every request).
# That's not what's happening here, but the rule can't tell the difference,
# so hoisting it out sidesteps the warning without changing any behavior.
_UPLOAD_FILES = File(...)


def _public_answer(answer) -> dict:
    """Answer payload with server filesystem paths swapped for fetchable URLs.

    Page evidence carries an absolute path on the machine running the API,
    which a client has no business seeing and could not read anyway.
    """
    from urllib.parse import quote

    payload = answer.to_dict()
    for item in payload.get("evidence", []):
        path = item.pop("image_path", "")
        item["image_url"] = f"/api/page-image?page_id={quote(item['id'], safe='')}" if path else ""
    return payload


def create_app(pipeline: AgenticRAG | None = None):
    rag = pipeline or AgenticRAG(Settings.from_env())
    app = FastAPI(
        title="Agentic RAG Knowledge Assistant",
        version=__version__,
        description="Agentic retrieval with tool planning, context assembly, "
        "claim verification, and cited, streamed answers.",
        contact={"name": "Asad Aslam", "url": "https://github.com/asadaslam556/agentic-rag-assistant"},
        license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
    )
    # The Vite dev server proxies /api to this app, but direct calls from
    # localhost:5173 during frontend development are also allowed.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    auth_token = rag.settings.api_auth_token

    def check_auth(authorization: str | None = Header(default=None)) -> None:
        if not auth_token:
            return
        if authorization != f"Bearer {auth_token}":
            raise HTTPException(status_code=401, detail="Missing or invalid API token.")

    protected = [Depends(check_auth)]

    @app.get("/api/health")
    def health() -> dict:
        """Live status of every moving part, not a hardcoded ok.

        Each component is actually checked: a running Ollama gets probed,
        the index gets read, the catalog file and the search dependency get
        verified. The overall status flips to "degraded" the moment any
        component reports down, so the console header and any monitoring
        can key off one field. Top-level fields stay as they were for
        existing clients, the per-component detail lives in "components".
        """
        components: dict[str, dict] = {}

        llm_name = rag.llm.name
        if llm_name.startswith("ollama:"):
            from agentic_rag.llm.ollama import list_models

            model = getattr(rag.llm, "model", "")
            installed = list_models(rag.settings.ollama_base_url, timeout=1.0)
            if installed is None:
                components["llm"] = {
                    "status": "down",
                    "detail": f"{llm_name} answered at startup but Ollama is no longer "
                    f"reachable at {rag.settings.ollama_base_url}. Restart Ollama, "
                    "then restart rag serve.",
                }
            elif model and model not in installed:
                components["llm"] = {
                    "status": "down",
                    "detail": f"model {model} is no longer installed (ollama pull {model})",
                }
            else:
                components["llm"] = {"status": "ok", "detail": llm_name}
        elif rag.llm.is_mock:
            components["llm"] = {"status": "ok", "detail": "deterministic offline mock"}
        else:
            # cloud providers: a real probe would spend a paid call per health hit
            components["llm"] = {"status": "ok", "detail": f"{llm_name} (configured, not probed)"}

        try:
            chunk_count = rag.store.count
            components["index"] = {
                "status": "ok",
                "detail": f"{chunk_count} chunks, retrieval mode {rag.settings.retrieval_mode}",
            }
        except Exception as exc:
            chunk_count = 0
            components["index"] = {"status": "down", "detail": str(exc)[:200]}

        catalog = Path(rag.settings.catalog_path)
        if catalog.exists():
            components["catalog"] = {"status": "ok", "detail": str(catalog)}
        else:
            components["catalog"] = {
                "status": "down",
                "detail": f"{catalog} not found, the knowledge_base tool will return nothing",
            }

        provider = rag.settings.search_provider
        if provider == "none":
            components["web_search"] = {"status": "ok", "detail": "disabled (SEARCH_PROVIDER=none)"}
        elif provider == "fixture":
            components["web_search"] = {"status": "ok", "detail": "fixture provider (offline)"}
        elif provider == "tavily":
            if rag.settings.tavily_api_key:
                components["web_search"] = {"status": "ok", "detail": "tavily configured"}
            else:
                components["web_search"] = {
                    "status": "down",
                    "detail": "SEARCH_PROVIDER=tavily but TAVILY_API_KEY is empty",
                }
        else:
            try:
                import ddgs  # noqa: F401

                components["web_search"] = {"status": "ok", "detail": "ddgs installed"}
            except ImportError:
                try:
                    import duckduckgo_search  # noqa: F401

                    components["web_search"] = {"status": "ok", "detail": "duckduckgo_search installed"}
                except ImportError:
                    components["web_search"] = {
                        "status": "down",
                        "detail": "SEARCH_PROVIDER=ddgs but the ddgs package is missing",
                    }

        status = "ok" if all(c["status"] == "ok" for c in components.values()) else "degraded"
        return {
            "status": status,
            "version": __version__,
            "llm": llm_name,
            "embedder": rag.embedder.name,
            "search_provider": provider,
            "retrieval_mode": rag.settings.retrieval_mode,
            "chunks_indexed": chunk_count,
            "tools": list(rag.tools),
            "auth_required": bool(auth_token),
            "model_routing": rag.router.describe() if rag.router.is_split() else None,
            "components": components,
        }

    @app.post("/api/ask", dependencies=protected)
    def ask(request: AskRequest) -> dict:
        """One-shot question (kept for API compatibility; /api/chat supersedes it)."""
        return _public_answer(rag.ask(request.question))

    @app.post("/api/chat", dependencies=protected)
    def chat(request: ChatRequest) -> dict:
        return _public_answer(rag.chat(request.question, history=request.history))

    @app.post("/api/chat/stream", dependencies=protected)
    def chat_stream(request: ChatRequest) -> StreamingResponse:
        """Server-sent events: rewrite, stage, step, synthesis_start, token,
        then a final `answer` event with the complete payload and `done`."""
        events: queue.Queue = queue.Queue()

        def emit(name: str, payload: dict) -> None:
            events.put((name, payload))

        def worker() -> None:
            try:
                answer = rag.chat(request.question, history=request.history, on_event=emit)
                events.put(("answer", _public_answer(answer)))
            except Exception as exc:  # surfaced to the client as an error event
                events.put(("error", {"message": str(exc)[:500]}))
            finally:
                events.put(None)

        threading.Thread(target=worker, daemon=True).start()

        def generate():
            while True:
                try:
                    item = events.get(timeout=300)
                except queue.Empty:
                    yield 'event: error\ndata: {"message": "Timed out waiting for the pipeline."}\n\n'
                    return
                if item is None:
                    yield "event: done\ndata: {}\n\n"
                    return
                name, payload = item
                yield f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/page-image", dependencies=protected)
    def page_image(page_id: str):
        """Serve one rendered page. Only pages in the index can be fetched,
        which keeps this from becoming a way to read arbitrary files."""
        for record in rag.pages.records():
            if record.id == page_id:
                path = Path(record.image_path)
                if not path.exists():
                    raise HTTPException(status_code=404, detail="Page image is no longer on disk.")
                return FileResponse(path, media_type="image/png")
        raise HTTPException(status_code=404, detail=f"No indexed page with id {page_id!r}.")

    @app.post("/api/ingest", dependencies=protected)
    def ingest(request: IngestRequest) -> dict:
        path = Path(request.path)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Path not found: {request.path}")
        return rag.ingest(path)

    @app.post("/api/upload", dependencies=protected)
    async def upload(files: list[UploadFile] = _UPLOAD_FILES) -> dict:
        max_bytes = rag.settings.upload_max_mb * 1024 * 1024
        upload_dir = rag.settings.storage_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        results: list[dict] = []
        saved: list[Path] = []
        for file in files:
            name = Path(file.filename or "upload").name
            suffix = Path(name).suffix.lower()
            if suffix not in SUPPORTED_EXTENSIONS:
                results.append(
                    {
                        "file": name,
                        "status": "rejected",
                        "detail": f"unsupported type {suffix or '(none)'}",
                    }
                )
                continue
            target = upload_dir / name
            stem, counter = target.stem, 1
            while target.exists():
                target = upload_dir / f"{stem}-{counter}{suffix}"
                counter += 1
            size = 0
            too_big = False
            with target.open("wb") as out:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        too_big = True
                        break
                    out.write(chunk)
            if too_big:
                target.unlink(missing_ok=True)
                results.append(
                    {
                        "file": name,
                        "status": "rejected",
                        "detail": f"larger than {rag.settings.upload_max_mb} MB",
                    }
                )
                continue
            saved.append(target)
            results.append({"file": name, "status": "saved", "stored_as": target.name})
        chunks_added = 0
        for path in saved:
            stats = rag.ingest(path)
            chunks_added += stats.get("chunks_added", 0)
        return {
            "results": results,
            "chunks_added": chunks_added,
            "chunks_indexed": rag.store.count,
        }

    if FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="console")

    return app
