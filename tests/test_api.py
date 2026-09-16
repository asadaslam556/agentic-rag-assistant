"""API contract tests. Skipped automatically when fastapi is not
installed (the offline core has no hard dependency on it); CI installs
fastapi and runs them."""

import json
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from agentic_rag.api import create_app  # noqa: E402
from agentic_rag.config import Settings  # noqa: E402
from agentic_rag.pipeline import AgenticRAG  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(tmp_path):
    settings = Settings(
        llm_provider="mock",
        embeddings_provider="local",
        search_provider="none",
        storage_dir=str(tmp_path / "storage"),
        catalog_path=str(ROOT / "data" / "structured" / "catalog.json"),
    )
    pipeline = AgenticRAG(settings)
    pipeline.ingest(ROOT / "data" / "sample_docs")
    return TestClient(create_app(pipeline))


def test_health_reports_pipeline_state(client):
    payload = client.get("/api/health").json()
    assert payload["status"] == "ok"
    assert payload["llm"] == "mock"
    assert payload["chunks_indexed"] > 10
    assert "vector_search" in payload["tools"]


def test_ask_returns_the_full_answer_shape(client):
    response = client.post("/api/ask", json={"question": "What is the payload capacity of the Atlas P2?"})
    assert response.status_code == 200
    payload = response.json()
    assert "450" in payload["text"]
    assert payload["citations"][0]["marker"] == 1
    assert payload["verification"]["passed"] is True
    assert payload["steps"], "the agent trace is part of the contract"


def test_ingest_rejects_missing_paths(client):
    response = client.post("/api/ingest", json={"path": "does/not/exist"})
    assert response.status_code == 404


def test_chat_carries_history_and_reports_rewrite_field(client):
    response = client.post(
        "/api/chat",
        json={
            "question": "How long does the Atlas P2 run on a single charge?",
            "history": [{"question": "payload?", "answer": "450 kg. [1]"}],
        },
    )
    payload = response.json()
    assert response.status_code == 200
    assert "14" in payload["text"]
    assert payload["rewritten_question"] == ""  # mock passes questions through


def test_chat_stream_emits_events_and_the_final_answer(client):
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"question": "What is the payload capacity of the Atlas P2?", "history": []},
    ) as response:
        assert response.status_code == 200
        body = "".join(chunk for chunk in response.iter_text())
    assert "event: stage" in body
    assert "event: token" in body
    assert "event: answer" in body
    assert body.rstrip().endswith("event: done\ndata: {}")


def _multipart_available() -> bool:
    for name in ("python_multipart", "multipart"):
        try:
            __import__(name)
            return True
        except ImportError:
            continue
    return False


def test_upload_ingests_supported_files_and_rejects_others(client):
    if not _multipart_available():
        pytest.skip("python-multipart not installed")
    files = [
        ("files", ("notes.md", b"# Notes\n\nThe secret launch codeword is aquamarine.", "text/markdown")),
        ("files", ("virus.exe", b"MZ...", "application/octet-stream")),
    ]
    response = client.post("/api/upload", files=files)
    assert response.status_code == 200
    payload = response.json()
    statuses = {entry["file"]: entry["status"] for entry in payload["results"]}
    assert statuses["notes.md"] == "saved"
    assert statuses["virus.exe"] == "rejected"
    assert payload["chunks_added"] >= 1
    follow_up = client.post("/api/ask", json={"question": "What is the secret launch codeword?"})
    assert "aquamarine" in follow_up.json()["text"]


def test_auth_token_gates_every_endpoint_except_health(tmp_path):
    settings = Settings(
        llm_provider="mock",
        embeddings_provider="local",
        search_provider="none",
        storage_dir=str(tmp_path / "storage"),
        catalog_path=str(ROOT / "data" / "structured" / "catalog.json"),
        api_auth_token="secret-token",
    )
    pipeline = AgenticRAG(settings)
    pipeline.ingest(ROOT / "data" / "sample_docs")
    locked = TestClient(create_app(pipeline))
    assert locked.get("/api/health").status_code == 200
    body = {"question": "What is the payload capacity of the Atlas P2?"}
    assert locked.post("/api/ask", json=body).status_code == 401
    ok = locked.post("/api/ask", json=body, headers={"Authorization": "Bearer secret-token"})
    assert ok.status_code == 200 and "450" in ok.json()["text"]


def test_health_reports_component_status(client):
    payload = client.get("/api/health").json()
    components = payload["components"]
    assert payload["status"] == "ok"
    assert components["llm"]["status"] == "ok"
    assert "mock" in components["llm"]["detail"]
    assert components["index"]["status"] == "ok"
    assert components["catalog"]["status"] == "ok"
    assert components["web_search"]["detail"].startswith("disabled")


def test_answers_never_expose_server_filesystem_paths(client, tmp_path):
    """Evidence carries an absolute path internally, which must not reach a client."""
    from agentic_rag.api import _public_answer
    from agentic_rag.core.types import (
        Answer,
        Citation,
        Evidence,
        VerificationReport,
    )

    evidence = [
        Evidence(
            id="doc#page2",
            text="Bar chart of fleet growth.",
            source_type="page",
            source_ref="doc.pdf#page2",
            title="Doc (page 2)",
            tool_name="visual_search",
            image_path="/home/someone/storage/pages/images/doc_page2.png",  # check_text: allow
        )
    ]
    answer = Answer(
        question="q",
        text="a [1]",
        citations=[
            Citation(
                marker=1,
                evidence_id="doc#page2",
                title="Doc (page 2)",
                source_type="page",
                source_ref="doc.pdf#page2",
            )
        ],
        evidence=evidence,
        verification=VerificationReport(
            passed=True, groundedness=1.0, citation_coverage=1.0, verdicts=[], method="lexical"
        ),
        steps=[],
        attempts=0,
        timings_ms={"total_ms": 1},
    )
    payload = _public_answer(answer)
    item = payload["evidence"][0]
    assert "image_path" not in item
    assert item["image_url"] == "/api/page-image?page_id=doc%23page2"
    assert "/home/someone" not in json.dumps(payload)


def test_page_image_endpoint_refuses_unknown_pages(client):
    response = client.get("/api/page-image", params={"page_id": "nope#page9"})
    assert response.status_code == 404


def test_fastapi_stays_off_the_core_import_path():
    """Importing the pipeline or the CLI must not drag fastapi in.

    api.py imports fastapi at module scope so FastAPI can resolve endpoint
    annotations, which is safe only because nothing on the core path imports
    api.py. This runs in a subprocess because another test importing the API
    would already have put fastapi in sys.modules.
    """
    import subprocess
    import sys
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src"
    code = (
        f"import sys; sys.path.insert(0, {str(src)!r});"
        "import agentic_rag, agentic_rag.pipeline, agentic_rag.cli;"
        "print('fastapi' in sys.modules)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False", "fastapi leaked onto the core import path"
