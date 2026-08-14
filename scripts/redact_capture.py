#!/usr/bin/env python3
"""Create a structure-preserving, identity-redacted JSON research capture."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


PATTERNS = (
    ("api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "<API_KEY>"),
    ("bearer", re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~-]{12,}"), r"\1<BEARER_TOKEN>"),
    ("email", re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I), "<EMAIL>"),
    ("windows_home", re.compile(r"(?i)[A-Za-z]:\\Users\\[^\\\r\n]+"), "<USER_HOME>"),
    ("unix_home", re.compile(r"/(?:home|Users)/[^/\s]+"), "<USER_HOME>"),
    ("ipv4", re.compile(r"(?<![\d.])(?!(?:127\.0\.0\.1|0\.0\.0\.0)(?!\d))(?:\d{1,3}\.){3}\d{1,3}(?![\d.])"), "<IP_ADDRESS>"),
)
SENSITIVE_QUERY_KEYS = {"access_token", "api_key", "key", "secret", "sig", "signature", "token"}


def sanitize_urls(text: str, counts: dict[str, int]) -> str:
    def replace(match: re.Match[str]) -> str:
        raw = match.group(0)
        try:
            parts = urlsplit(raw)
            pairs = parse_qsl(parts.query, keep_blank_values=True)
        except ValueError:
            return raw
        changed = False
        clean = []
        for key, value in pairs:
            if key.lower() in SENSITIVE_QUERY_KEYS and value:
                clean.append((key, "<REDACTED>"))
                counts["url_query"] = counts.get("url_query", 0) + 1
                changed = True
            else:
                clean.append((key, value))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(clean), parts.fragment)) if changed else raw

    return re.sub(r"https?://[^\s\"'<>]+", replace, text)


def sanitize_string(value: str, literals: list[str], counts: dict[str, int]) -> str:
    result = value
    for literal in literals:
        if literal:
            hits = result.lower().count(literal.lower())
            if hits:
                result = re.sub(re.escape(literal), "<LOCAL_USER>", result, flags=re.I)
                counts["explicit_literal"] = counts.get("explicit_literal", 0) + hits
    for label, pattern, replacement in PATTERNS:
        result, hits = pattern.subn(replacement, result)
        counts[label] = counts.get(label, 0) + hits
    return sanitize_urls(result, counts)


def sanitize(value: Any, literals: list[str], counts: dict[str, int]) -> Any:
    if isinstance(value, str):
        return sanitize_string(value, literals, counts)
    if isinstance(value, list):
        return [sanitize(item, literals, counts) for item in value]
    if isinstance(value, dict):
        return {key: sanitize(item, literals, counts) for key, item in value.items()}
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--redact-literal", action="append", default=[])
    args = parser.parse_args()

    raw = json.loads(args.input.read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    redacted = sanitize(raw, args.redact_literal, counts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(redacted, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    messages = redacted.get("messages", []) if isinstance(redacted, dict) else []
    tools = redacted.get("tools", []) if isinstance(redacted, dict) else []
    metadata = {
        "source_sha256": sha256(args.input),
        "redacted_sha256": sha256(args.output),
        "source_bytes": args.input.stat().st_size,
        "redacted_bytes": args.output.stat().st_size,
        "message_count": len(messages),
        "message_content_characters": [
            len(message.get("content", "")) if isinstance(message, dict) and isinstance(message.get("content"), str) else None
            for message in messages
        ],
        "tool_count": len(tools),
        "redaction_counts": counts,
        "notes": "Semantics and JSON structure preserved; identity and secret-like values replaced.",
    }
    args.metadata.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Redacted capture written: {args.output.name}; replacements={sum(counts.values())}")


if __name__ == "__main__":
    main()
