#!/usr/bin/env python3
"""Build deterministic, inert fixtures for the controlled integrity lab."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "lab" / "fixtures" / "synthetic-screen.png"


def png_chunk(kind: bytes, data: bytes) -> bytes:
    payload = kind + data
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)


def build_png(width: int = 640, height: int = 360) -> bytes:
    """Return a simple generated image; no screen-capture API is involved."""

    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            panel = 28 < x < width - 28 and 36 < y < height - 28
            stripe = panel and (y // 42) % 2 == 0
            if not panel:
                color = (31, 41, 55)
            elif stripe:
                color = (226, 232, 240)
            else:
                color = (248, 250, 252)
            row.extend(color)
        rows.append(bytes(row))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", header) + png_chunk(
        b"IDAT", zlib.compress(b"".join(rows), 9)
    ) + png_chunk(b"IEND", b"")


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(build_png())
    print(f"Built inert synthetic fixture: {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
