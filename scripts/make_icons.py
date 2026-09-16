"""Generate the console's PWA icons without any imaging dependency.

Rasterises the brand mark (petrol rounded square, white check) with
NumPy at 4x supersampling and writes the PNG files by hand (zlib and
struct only). Regenerate after changing colors:

    python scripts/make_icons.py
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np

PETROL = (11, 110, 94)  # #0B6E5E
OUT = Path(__file__).resolve().parents[1] / "frontend" / "public"


def _png_bytes(rgba: np.ndarray) -> bytes:
    height, width, _ = rgba.shape
    raw = b"".join(b"\x00" + rgba[row].tobytes() for row in range(height))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def _segment_distance(px: np.ndarray, py: np.ndarray, a: tuple, b: tuple) -> np.ndarray:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / length_sq, 0.0, 1.0)
    return np.hypot(px - (ax + t * dx), py - (ay + t * dy))


def render(size: int, corner_ratio: float, check_scale: float = 1.0) -> np.ndarray:
    scale = 4  # supersampling factor
    s = size * scale
    ys, xs = np.mgrid[0:s, 0:s]
    x = (xs + 0.5) / s
    y = (ys + 0.5) / s

    # rounded-square coverage
    radius = corner_ratio
    cx = np.clip(x, radius, 1 - radius)
    cy = np.clip(y, radius, 1 - radius)
    inside = np.hypot(x - cx, y - cy) <= radius

    # check mark: two segments, round caps via distance threshold
    def warp(p: tuple) -> tuple:
        return (0.5 + (p[0] - 0.5) * check_scale, 0.5 + (p[1] - 0.5) * check_scale)

    p0, p1, p2 = warp((0.29, 0.52)), warp((0.45, 0.68)), warp((0.73, 0.34))
    stroke = 0.115 * check_scale / 2
    d = np.minimum(_segment_distance(x, y, p0, p1), _segment_distance(x, y, p1, p2))
    check = d <= stroke

    rgba = np.zeros((s, s, 4), dtype=np.uint8)
    rgba[inside] = (*PETROL, 255)
    rgba[inside & check] = (255, 255, 255, 255)

    # downsample (mean over scale x scale blocks) for anti-aliasing
    small = rgba.reshape(size, scale, size, scale, 4).mean(axis=(1, 3))
    return small.round().astype(np.uint8)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    targets = [
        ("icon-192.png", 192, 0.22, 1.0),
        ("icon-512.png", 512, 0.22, 1.0),
        # maskable: full-bleed background, mark inside the 80% safe zone
        ("icon-maskable-512.png", 512, 0.0, 0.72),
        ("apple-touch-icon.png", 180, 0.0, 0.9),
    ]
    for name, size, corner, check_scale in targets:
        path = OUT / name
        path.write_bytes(_png_bytes(render(size, corner, check_scale)))
        print(f"wrote {path.relative_to(OUT.parents[1])} ({size}x{size})")


if __name__ == "__main__":
    main()
