"""Document loaders for .txt, .md, .html, and .pdf files."""

from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path

from agentic_rag.core.types import Document

SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".html", ".htm", ".pdf"}


class _HtmlTextExtractor(HTMLParser):
    _SKIP = {"script", "style", "noscript"}

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data.strip()
        elif data.strip():
            self._parts.append(data)

    @property
    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "".join(self._parts))


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PDF ingestion requires pypdf. Install it with: pip install pypdf") from exc
    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "") for page in reader.pages]
    return "\n\n".join(pages)


def _markdown_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip() or fallback
    return fallback


def load_document(path: Path) -> Document:
    path = Path(path)
    suffix = path.suffix.lower()
    fallback_title = path.stem.replace("_", " ").replace("-", " ").strip().title()
    if suffix in {".txt", ".md", ".markdown"}:
        text = path.read_text(encoding="utf-8", errors="replace")
        title = _markdown_title(text, fallback_title) if suffix != ".txt" else fallback_title
    elif suffix in {".html", ".htm"}:
        parser = _HtmlTextExtractor()
        parser.feed(path.read_text(encoding="utf-8", errors="replace"))
        text = parser.text
        title = parser.title or fallback_title
    elif suffix == ".pdf":
        text = _read_pdf(path)
        title = fallback_title
    else:
        raise ValueError(f"Unsupported file type: {path.name} (supported: {sorted(SUPPORTED_EXTENSIONS)})")
    doc_id = hashlib.md5(str(path.resolve()).encode("utf-8")).hexdigest()[:12]
    return Document(id=doc_id, path=str(path), title=title, text=text)


def discover_files(root: Path) -> list[Path]:
    root = Path(root)
    if root.is_file():
        return [root] if root.suffix.lower() in SUPPORTED_EXTENSIONS else []
    return sorted(
        p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )
