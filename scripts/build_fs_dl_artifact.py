#!/usr/bin/env python3
"""Server-side generator for the TC-004-FS artifacts (run on the lab server).

Reads CANARY_UPLOAD_TOKEN from canary-runtime.env (never printed), injects it
into each template placeholder, and writes
artifacts/workbuddy_canary_capture_fs_dl.ps1 and
artifacts/workbuddy_canary_capture_fs_p.ps1. The repository only ever holds
the templates with the __UPLOAD_TOKEN__ placeholder.
"""
import hashlib
import pathlib
import re
import sys

DEPLOY = pathlib.Path("/opt/ai-integrity-lab")
ENV_FILE = DEPLOY / "canary-runtime.env"
OUT_DIR = DEPLOY / "artifacts"
PLACEHOLDER = "__UPLOAD_TOKEN__"
ARTIFACTS = (
    (DEPLOY / "workbuddy_canary_capture_fs_dl.ps1", "workbuddy_canary_capture_fs_dl.ps1"),
    (DEPLOY / "workbuddy_canary_capture_fs_p.ps1", "workbuddy_canary_capture_fs_p.ps1"),
)

if not ENV_FILE.is_file():
    print("ERROR: env file missing"); sys.exit(1)

token = None
for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
    match = re.fullmatch(r"CANARY_UPLOAD_TOKEN=(\S+)", line.strip())
    if match:
        token = match.group(1)
        break
if not token:
    print("ERROR: CANARY_UPLOAD_TOKEN not found in env file"); sys.exit(1)
if not 32 <= len(token) <= 128:
    print("ERROR: token length out of range"); sys.exit(1)

for template, name in ARTIFACTS:
    if not template.is_file():
        print("ERROR: template missing:", template); sys.exit(1)
    template_text = template.read_text(encoding="utf-8")
    if PLACEHOLDER not in template_text:
        print("ERROR: placeholder missing in template:", template); sys.exit(1)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    artifact = template_text.replace(PLACEHOLDER, token)
    out_file = OUT_DIR / name
    out_file.write_text(artifact, encoding="utf-8")
    assert PLACEHOLDER not in artifact
    print("ARTIFACT-WRITTEN:", out_file)
    print("ARTIFACT-SHA256:", hashlib.sha256(artifact.encode("utf-8")).hexdigest())
    print("ARTIFACT-BYTES:", len(artifact.encode("utf-8")))
