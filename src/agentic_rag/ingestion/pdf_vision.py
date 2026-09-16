"""Reading what a PDF shows, not just what it says.

Text extraction gets the prose and loses everything that carries meaning
visually: bar charts, schematics, screenshots, and tables whose layout is
the information. For a corpus of reports and datasheets that is often the
half you actually wanted.

This module renders each page to an image and asks a vision-capable model
what is on it, then indexes that description as ordinary text chunks
beside the extracted prose. Retrieval, citations, and verification carry
on unchanged, and a chart becomes findable through the same hybrid search
as everything else.

Why this rather than ColPali: ColPali embeds page images directly with a
vision-language model and retrieves with late interaction, which avoids
the description step and keeps more visual nuance. It also needs a
multi-billion parameter model, a GPU to be usable, a torch install, and a
multi-vector index. That is a heavy dependency for a project that
otherwise runs offline on a laptop with no accelerator, and it cannot run
on the free hosting tiers this project targets. Describing pages through
the provider layer already in use gets most of the benefit for the cost
of one API call per page, with no new model infrastructure. The seam is
deliberately narrow: swap `describe_pages` for a ColPali retriever and
the rest of the pipeline does not change.

Rendering needs pypdfium2, which ships as a self-contained wheel:

    pip install -e ".[vision]"
"""

from __future__ import annotations

from pathlib import Path

from agentic_rag.config import Settings
from agentic_rag.core.types import Chunk, Document
from agentic_rag.llm.base import LLMClient

VISION_SYSTEM = """## MODE: PAGE

You are reading one page of a document as an image.

Describe what the page contains, in plain prose, so that someone
searching the document later can find this page by its content:
- Any chart or diagram: what it plots, the axes, the trend, and the
  values you can read with confidence.
- Any table: what it lists, the column headings, and the notable rows.
- Any figure, schematic, or screenshot: what it depicts and its labels.
- Headings and short body text that give the page its context.

Rules:
- Report only what is visible. Never guess at a number you cannot read.
- If the page is plain prose with no visual content, say exactly:
  NO VISUAL CONTENT
- No preamble, no markdown, just the description.
"""

# Pages with less text than this look like scans or figure pages, which is
# what "auto" mode is watching for.
_THIN_TEXT_PER_PAGE = 220


def vision_enabled(settings: Settings, llm: LLMClient, text: str, page_count: int) -> bool:
    """Decide whether this PDF is worth sending through a vision model.

    off  never. on   always. auto only when text extraction came back thin,
    which is the scanned or diagram-heavy case where it actually pays.
    """
    mode = (settings.pdf_vision or "auto").lower()
    if mode == "off" or not getattr(llm, "supports_vision", False):
        return False
    if mode == "on":
        return True
    if page_count <= 0:
        return False
    return len(text.strip()) / page_count < _THIN_TEXT_PER_PAGE


def render_pages(path: Path, max_pages: int, scale: float) -> list[bytes]:
    """Render the first max_pages pages to PNG bytes."""
    try:
        import pypdfium2
    except ImportError as exc:
        raise RuntimeError(
            "Page rendering needs pypdfium2. Install it with: pip install -e \".[vision]\" "
            "or set PDF_VISION=off to skip page images."
        ) from exc

    images: list[bytes] = []
    pdf = pypdfium2.PdfDocument(str(path))
    try:
        for index in range(min(len(pdf), max(1, max_pages))):
            page = pdf[index]
            bitmap = page.render(scale=scale)
            buffer = bitmap.to_pil()
            from io import BytesIO

            out = BytesIO()
            buffer.save(out, format="PNG")
            images.append(out.getvalue())
    finally:
        pdf.close()
    return images


def describe_pages(llm: LLMClient, images: list[bytes]) -> list[str]:
    """One description per page. A page that fails is skipped, not fatal."""
    descriptions: list[str] = []
    for number, image in enumerate(images, 1):
        try:
            response = llm.complete_vision(
                VISION_SYSTEM,
                f"This is page {number}. Describe it.",
                [image],
                temperature=0.0,
                max_tokens=700,
            )
            descriptions.append(response.text.strip())
        except Exception as exc:
            descriptions.append(f"PAGE READ FAILED: {str(exc)[:200]}")
    return descriptions


def page_chunks(doc: Document, descriptions: list[str], start_position: int) -> list[Chunk]:
    """Turn page descriptions into chunks that cite as "page N (visual)"."""
    chunks: list[Chunk] = []
    position = start_position
    for number, description in enumerate(descriptions, 1):
        body = description.strip()
        if not body or body.upper().startswith("NO VISUAL CONTENT"):
            continue
        if body.startswith("PAGE READ FAILED"):
            continue
        chunks.append(
            Chunk(
                id=f"{doc.id}#page{number}",
                doc_id=doc.id,
                text=f"Page {number} visual content. {body}",
                title=doc.title,
                heading=f"page {number} (visual)",
                position=position,
                source_path=doc.path,
            )
        )
        position += 1
    return chunks


def visual_chunks_for_pdf(
    path: Path, doc: Document, llm: LLMClient, settings: Settings, start_position: int
) -> list[Chunk]:
    """Full path from a PDF on disk to indexable descriptions of its pages."""
    images = render_pages(path, settings.vision_max_pages, settings.vision_scale)
    if not images:
        return []
    return page_chunks(doc, describe_pages(llm, images), start_position)
