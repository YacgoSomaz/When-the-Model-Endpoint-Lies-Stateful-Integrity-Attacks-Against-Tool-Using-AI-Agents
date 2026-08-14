#!/usr/bin/env python3
"""Build the inert demonstration ZIP from reviewed text-only sources."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "lab" / "safe-demo-package"
OUTPUT = ROOT / "lab" / "safe-demo-package.zip"
ALLOWED = ("README.txt", "manifest.json")


def main() -> None:
    present = sorted(path.name for path in SOURCE.iterdir() if path.is_file())
    if present != sorted(ALLOWED):
        raise SystemExit(f"Unexpected safe artifact contents: {present}")
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ALLOWED:
            archive.write(SOURCE / name, arcname=name)
    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    print(f"Built {OUTPUT.name}: {OUTPUT.stat().st_size} bytes, SHA256={digest}")


if __name__ == "__main__":
    main()
