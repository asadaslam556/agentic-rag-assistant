"""Build the demo PDF used to show visual retrieval.

Hand-writes the PDF so the repository does not need a reporting library
just to ship one sample. The document deliberately puts some facts only
in the pictures: the quarterly bar chart carries a trend no sentence
states, the table's meaning is its layout, and the schematic labels a
flow. Text extraction pulls the labels and misses the relationships,
which is exactly the gap page-image reading is meant to close.

    python scripts/make_sample_pdf.py
"""

from __future__ import annotations

import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "sample_pdfs"
PAGE_W, PAGE_H = 595, 842  # A4 at 72 dpi


def esc(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


class Canvas:
    """Just enough PDF drawing: text, rectangles, lines."""

    def __init__(self) -> None:
        self.parts: list[str] = []

    def text(self, x: float, y: float, body: str, size: int = 11, font: str = "F1", gray: float = 0.0):
        self.parts.append(
            f"BT /{font} {size} Tf {gray:.2f} g {x:.1f} {PAGE_H - y:.1f} Td ({esc(body)}) Tj ET"
        )

    def rect(self, x: float, y: float, w: float, h: float, fill: tuple | None = None,
             stroke: tuple | None = None, width: float = 1.0):
        if fill:
            self.parts.append(f"{fill[0]:.3f} {fill[1]:.3f} {fill[2]:.3f} rg")
            self.parts.append(f"{x:.1f} {PAGE_H - y - h:.1f} {w:.1f} {h:.1f} re f")
        if stroke:
            self.parts.append(f"{stroke[0]:.3f} {stroke[1]:.3f} {stroke[2]:.3f} RG {width:.1f} w")
            self.parts.append(f"{x:.1f} {PAGE_H - y - h:.1f} {w:.1f} {h:.1f} re S")

    def line(self, x1: float, y1: float, x2: float, y2: float, gray: float = 0.0, width: float = 1.0):
        self.parts.append(f"{gray:.2f} G {width:.1f} w {x1:.1f} {PAGE_H - y1:.1f} m {x2:.1f} {PAGE_H - y2:.1f} l S")

    def stream(self) -> bytes:
        return "\n".join(self.parts).encode("latin-1", errors="replace")


PETROL = (0.043, 0.431, 0.369)
LIGHT = (0.890, 0.937, 0.922)


def page_one() -> Canvas:
    c = Canvas()
    c.text(60, 80, "Auralis Dynamics", 22)
    c.text(60, 106, "Quarterly operations review", 14, gray=0.35)
    c.line(60, 122, 535, 122, gray=0.8)

    lines = [
        "This review covers fleet growth, regional deployment, and the service",
        "architecture for the Atlas platform. Figures in this document are",
        "illustrative and describe a fictional company.",
        "",
        "The fleet expanded across every region during the year, with the",
        "strongest single quarter driven by three large logistics sites coming",
        "online together. Support load per robot fell as the fleet grew, which",
        "the operations team attributes to the remote diagnostics rollout.",
        "",
        "Page two charts the quarterly fleet figures. Page three lists the",
        "regional breakdown and service tiers. Page four shows how a task",
        "moves through the scheduling stack.",
    ]
    y = 156
    for line in lines:
        c.text(60, y, line, 11, gray=0.15)
        y += 18

    c.rect(60, 400, 475, 92, fill=LIGHT)
    c.text(76, 428, "At a glance", 12)
    c.text(76, 450, "Deployed robots grew through the year across four regions.", 10.5, gray=0.25)
    c.text(76, 468, "Exact quarterly values are in the chart on page two.", 10.5, gray=0.25)
    return c


def page_two() -> Canvas:
    """A bar chart. The trend and the biggest jump exist only as geometry."""
    c = Canvas()
    c.text(60, 80, "Fleet growth by quarter", 18)
    c.text(60, 104, "Deployed robots, end of quarter", 11, gray=0.4)

    base_y, base_x = 520, 90
    chart_h, bar_w, gap = 300, 62, 44
    values = [("Q1", 410), ("Q2", 640), ("Q3", 1180), ("Q4", 1850)]
    top = 2000

    c.line(base_x, base_y, base_x + 430, base_y, gray=0.2, width=1.2)
    c.line(base_x, base_y, base_x, base_y - chart_h, gray=0.2, width=1.2)

    for tick in range(0, top + 1, 500):
        y = base_y - (tick / top) * chart_h
        c.line(base_x - 4, y, base_x + 430, y, gray=0.85, width=0.5)
        c.text(base_x - 42, y + 3, str(tick), 9, gray=0.45)

    # no printed values on purpose: the bar heights are the only record of
    # the quarterly figures, which is the case page-image reading exists for
    x = base_x + 26
    for label, value in values:
        height = (value / top) * chart_h
        c.rect(x, base_y - height, bar_w, height, fill=PETROL)
        c.text(x + 20, base_y + 18, label, 11, gray=0.2)
        x += bar_w + gap

    c.text(60, 580, "Robots per site averaged 20 at year end.", 10.5, gray=0.3)
    c.text(60, 600, "The Nordics region opened in Q3.", 10.5, gray=0.3)
    return c


def page_three() -> Canvas:
    """A table. Meaning is the row and column layout."""
    c = Canvas()
    c.text(60, 80, "Regional deployment and service tiers", 18)
    c.text(60, 104, "End of Q4", 11, gray=0.4)

    headers = ["Region", "Sites", "Robots", "Service tier", "Response"]
    rows = [
        ["Central Europe", "38", "760", "Scale", "4 hours"],
        ["Nordics", "12", "240", "Scale", "8 hours"],
        ["Iberia", "21", "410", "Growth", "next day"],
        ["United Kingdom", "21", "440", "Growth", "next day"],
    ]
    widths = [140, 60, 70, 100, 90]
    x0, y0, row_h = 60, 140, 30

    x = x0
    c.rect(x0, y0, sum(widths), row_h, fill=LIGHT)
    for header, width in zip(headers, widths, strict=True):
        c.text(x + 8, y0 + 20, header, 10.5)
        x += width

    y = y0 + row_h
    for row in rows:
        x = x0
        for cell, width in zip(row, widths, strict=True):
            c.text(x + 8, y + 20, cell, 10.5, gray=0.15)
            x += width
        c.line(x0, y + row_h, x0 + sum(widths), y + row_h, gray=0.85, width=0.5)
        y += row_h

    x = x0
    for width in widths:
        c.line(x, y0, x, y, gray=0.85, width=0.5)
        x += width
    c.line(x, y0, x, y, gray=0.85, width=0.5)
    c.rect(x0, y0, sum(widths), y - y0, stroke=(0.6, 0.6, 0.6), width=0.8)

    c.text(60, y + 46, "Scale sites carry a four hour response commitment.", 10.5, gray=0.3)
    c.text(60, y + 66, "Growth sites are next business day.", 10.5, gray=0.3)
    return c


def page_four() -> Canvas:
    """A schematic. The arrows carry the order, the text does not."""
    c = Canvas()
    c.text(60, 80, "How a task reaches a robot", 18)
    c.text(60, 104, "Scheduling stack, simplified", 11, gray=0.4)

    boxes = [
        (60, 150, "Warehouse system", "order or pick request"),
        (60, 250, "Atlas Hive", "queues and assigns"),
        (60, 350, "Fleet scheduler", "picks a robot and route"),
        (60, 450, "Atlas P2", "executes and reports"),
    ]
    for x, y, title, subtitle in boxes:
        c.rect(x, y, 300, 60, fill=LIGHT, stroke=PETROL, width=1.2)
        c.text(x + 16, y + 26, title, 12)
        c.text(x + 16, y + 46, subtitle, 9.5, gray=0.35)

    for y in (210, 310, 410):
        c.line(210, y, 210, y + 40, gray=0.3, width=1.4)
        c.line(204, y + 32, 210, y + 40, gray=0.3, width=1.4)
        c.line(216, y + 32, 210, y + 40, gray=0.3, width=1.4)

    c.rect(400, 250, 135, 160, stroke=(0.7, 0.7, 0.7), width=0.8)
    c.text(414, 274, "Telemetry", 11)
    c.text(414, 296, "battery", 9.5, gray=0.35)
    c.text(414, 314, "position", 9.5, gray=0.35)
    c.text(414, 332, "task state", 9.5, gray=0.35)
    c.text(414, 358, "sent every", 9.5, gray=0.35)
    c.text(414, 376, "two seconds", 9.5, gray=0.35)
    c.line(360, 330, 400, 330, gray=0.3, width=1.0)

    c.text(60, 560, "A task never skips the scheduler, which is what keeps two", 10.5, gray=0.3)
    c.text(60, 580, "robots from being sent to the same aisle.", 10.5, gray=0.3)
    return c


def page_five() -> Canvas:
    """A line chart with no printed values. The peak is the whole point."""
    c = Canvas()
    c.text(60, 80, "Throughput against battery charge", 18)
    c.text(60, 104, "Pallets moved per hour, averaged across the fleet", 11, gray=0.4)

    base_y, base_x = 500, 90
    chart_h, chart_w = 280, 420
    c.line(base_x, base_y, base_x + chart_w, base_y, gray=0.2, width=1.2)
    c.line(base_x, base_y, base_x, base_y - chart_h, gray=0.2, width=1.2)

    for step in range(0, 6):
        x = base_x + (step / 5) * chart_w
        c.text(x - 8, base_y + 18, f"{step * 20}%", 9, gray=0.45)
        c.line(x, base_y, x, base_y + 4, gray=0.4, width=0.8)

    # throughput rises, peaks near 60 percent charge, then falls away
    shape = [0.30, 0.55, 0.78, 1.00, 0.86, 0.52]
    points = [
        (base_x + (i / 5) * chart_w, base_y - value * chart_h * 0.92)
        for i, value in enumerate(shape)
    ]
    for start, end in zip(points, points[1:], strict=False):
        c.line(start[0], start[1], end[0], end[1], gray=0.05, width=2.0)
    for x, y in points:
        c.rect(x - 3, y - 3, 6, 6, fill=PETROL)

    c.text(60, 560, "Sustained work above 80 percent charge is rare because the", 10.5, gray=0.3)
    c.text(60, 580, "fleet scheduler holds robots back for opportunity charging.", 10.5, gray=0.3)
    c.text(60, 612, "The vertical axis is deliberately unlabelled in this draft.", 10, gray=0.5)
    return c


def build_pdf(pages: list[Canvas]) -> bytes:
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    bold_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")

    # the page tree is written last but referenced by every page, so reserve
    # its id now: current objects, plus a content and a page object per page
    pages_id = len(objects) + 2 * len(pages) + 1
    page_ids: list[int] = []
    for canvas in pages:
        raw = zlib.compress(canvas.stream())
        content_id = add(
            b"<< /Length " + str(len(raw)).encode() + b" /Filter /FlateDecode >>\nstream\n" + raw + b"\nendstream"
        )
        page_id = add(
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
            f"/Resources << /Font << /F1 {font_id} 0 R /F2 {bold_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>".encode()
        )
        page_ids.append(page_id)

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    actual_pages_id = add(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode())
    assert actual_pages_id == pages_id, "page tree id drifted from the reserved slot"
    catalog_id = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "auralis-quarterly-review.pdf"
    target.write_bytes(build_pdf([page_one(), page_two(), page_three(), page_four(), page_five()]))
    print(f"wrote {target.relative_to(OUT.parents[1])} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
