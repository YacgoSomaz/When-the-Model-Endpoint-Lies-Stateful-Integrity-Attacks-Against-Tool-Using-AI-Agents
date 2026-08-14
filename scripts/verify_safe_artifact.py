#!/usr/bin/env python3
"""Reject executable or unexpected content in the demonstration ZIP."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "lab" / "safe-demo-package.zip"
EXPECTED = {"README.txt", "manifest.json"}
BLOCKED_SUFFIXES = {
    ".app", ".bat", ".cmd", ".com", ".dll", ".dmg", ".exe", ".hta",
    ".jar", ".js", ".lnk", ".msi", ".ps1", ".py", ".scr", ".sh", ".vbs",
}


def main() -> None:
    if not ARCHIVE.is_file():
        raise SystemExit("Archive missing; run build_safe_artifact.py first")
    with zipfile.ZipFile(ARCHIVE) as archive:
        names = set(archive.namelist())
        if names != EXPECTED:
            raise SystemExit(f"Unexpected archive members: {sorted(names)}")
        if any(Path(name).suffix.lower() in BLOCKED_SUFFIXES for name in names):
            raise SystemExit("Executable or script-like member detected")
        manifest = json.loads(archive.read("manifest.json"))
        required_false = ("executable", "installable", "network_access")
        if any(manifest.get(field) is not False for field in required_false):
            raise SystemExit("Manifest safety declarations are invalid")
    print("Safe artifact verified: text/JSON only; no executable member")


if __name__ == "__main__":
    main()
