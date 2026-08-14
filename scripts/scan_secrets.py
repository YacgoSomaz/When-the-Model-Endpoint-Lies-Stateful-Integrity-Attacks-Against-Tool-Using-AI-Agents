#!/usr/bin/env python3
"""Small dependency-free pre-commit secret and private-data scanner."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", "__pycache__"}
SKIP_SUFFIXES = {".zip", ".png", ".jpg", ".jpeg", ".gif", ".pdf"}
PATTERNS = {
    "API key": re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    "Bearer token": re.compile(r"Authorization\s*[:=]\s*Bearer\s+(?![+{<])[A-Za-z0-9._-]{16,}", re.I),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "IPv4 address": re.compile(r"(?<![\d.])(?!(?:127\.0\.0\.1|0\.0\.0\.0)(?!\d))(?:\d{1,3}\.){3}\d{1,3}(?![\d.])"),
    "Windows user path": re.compile(r"[A-Za-z]:\\Users\\(?!<)[^\\\r\n]+\\", re.I),
    "mainland phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "Chinese resident ID": re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)"),
}


def main() -> None:
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{path.relative_to(ROOT)}:{line}: {label}")
    if findings:
        print("Potential secrets or private identifiers detected:")
        print("\n".join(findings))
        raise SystemExit(1)
    print("Secret scan passed")


if __name__ == "__main__":
    main()
