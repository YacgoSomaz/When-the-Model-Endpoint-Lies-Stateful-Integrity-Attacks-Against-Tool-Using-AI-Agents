#!/usr/bin/env python3
"""Minimal allowlist-only Agent for controlled model-channel integrity tests.

SECURITY AUDIT ONLY - Isolated Test Environment

This module intentionally has no shell tool, no arbitrary file reader, no real
screen capture, and no general network client. Dry-run is the default. Even in
execution mode every proposed tool call requires explicit operator approval.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import time
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


LAB_ROOT = Path(__file__).resolve().parent
DEFAULT_FIXTURE_ROOT = LAB_ROOT / "fixtures"
DEFAULT_AUDIT_ROOT = LAB_ROOT / "audit-output"
MAX_FIXTURE_BYTES = 256 * 1024
ALLOWED_READ_SUFFIXES = {".json", ".txt", ".md"}
ALLOWED_COUNT_SUFFIXES = {".pem", ".key", ".p12"}
CASE_PATTERN = re.compile(r"TC-00[1-7]")
NONCE_PATTERN = re.compile(r"[A-Za-z0-9_-]{8,64}")


class SafetyViolation(ValueError):
    """Raised when a proposed action leaves the declared test boundary."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_: Any, **__: Any) -> None:
        return None


def resolve_within(root: Path, relative_name: str) -> Path:
    if not isinstance(relative_name, str) or not relative_name or len(relative_name) > 240:
        raise SafetyViolation("fixture 路径为空或过长")
    supplied = Path(relative_name)
    if supplied.is_absolute():
        raise SafetyViolation("禁止绝对路径")
    resolved_root = root.resolve(strict=True)
    candidate = (resolved_root / supplied).resolve(strict=True)
    if not candidate.is_relative_to(resolved_root):
        raise SafetyViolation("路径越过 fixture 根目录")
    return candidate


def validate_loopback_endpoint(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.path != "/diag-receive"
        or parsed.query
    ):
        raise SafetyViolation("诊断端点必须是 http://127.0.0.1:<port>/diag-receive")
    try:
        port = parsed.port
    except ValueError as error:
        raise SafetyViolation("诊断端口无效") from error
    if port is None or not 1 <= port <= 65535:
        raise SafetyViolation("诊断端点必须显式指定有效端口")
    return endpoint


class AuditRecorder:
    def __init__(self, audit_root: Path) -> None:
        self.root = audit_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "agent-audit.jsonl"

    def record(self, status: str, tool: str, case_id: str, detail: dict[str, Any] | None = None) -> None:
        event = {
            "timestamp": int(time.time()),
            "status": status,
            "tool": tool,
            "case_id": case_id,
            "detail": detail or {},
        }
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


class SafeToolExecutor:
    def __init__(
        self,
        fixture_root: Path = DEFAULT_FIXTURE_ROOT,
        audit_root: Path = DEFAULT_AUDIT_ROOT,
        diagnostic_endpoint: str | None = None,
    ) -> None:
        self.fixture_root = fixture_root.resolve(strict=True)
        self.audit = AuditRecorder(audit_root)
        self.diagnostic_endpoint = (
            validate_loopback_endpoint(diagnostic_endpoint) if diagnostic_endpoint else None
        )
        self.handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "write_audit_marker": self.write_audit_marker,
            "read_fixture": self.read_fixture,
            "count_fixture_files": self.count_fixture_files,
            "count_fixture_environment_names": self.count_fixture_environment_names,
            "create_synthetic_capture": self.create_synthetic_capture,
            "send_loopback_diagnostic": self.send_loopback_diagnostic,
        }

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handler = self.handlers.get(name)
        if not handler:
            raise SafetyViolation(f"工具不在白名单中：{name}")
        return handler(**arguments)

    def write_audit_marker(self, case_id: str) -> dict[str, Any]:
        if not CASE_PATTERN.fullmatch(case_id):
            raise SafetyViolation("case_id 无效")
        return {"status": "recorded", "case_id": case_id}

    def read_fixture(self, path: str) -> dict[str, Any]:
        target = resolve_within(self.fixture_root, path)
        if not target.is_file() or target.suffix.lower() not in ALLOWED_READ_SUFFIXES:
            raise SafetyViolation("只允许读取 fixture 中的 JSON、TXT 或 Markdown 文件")
        if target.stat().st_size > MAX_FIXTURE_BYTES:
            raise SafetyViolation("fixture 超出大小限制")
        return {"fixture": target.relative_to(self.fixture_root).as_posix(), "content": target.read_text("utf-8")}

    def count_fixture_files(self, extension_list: list[str]) -> dict[str, Any]:
        if not isinstance(extension_list, list) or not extension_list:
            raise SafetyViolation("扩展名列表不能为空")
        normalized = {str(value).lower() for value in extension_list}
        if not normalized <= ALLOWED_COUNT_SUFFIXES:
            raise SafetyViolation("扩展名超出 fixture 计数白名单")
        count = sum(
            1
            for path in self.fixture_root.rglob("*")
            if path.is_file() and path.suffix.lower() in normalized and path.resolve().is_relative_to(self.fixture_root)
        )
        return {"fixture_only": True, "count": count, "extensions": sorted(normalized)}

    def count_fixture_environment_names(self, pattern: str) -> dict[str, Any]:
        if pattern != "key|token|secret|api|pass":
            raise SafetyViolation("仅允许预定义的名称模式")
        target = resolve_within(self.fixture_root, "environment.json")
        values = json.loads(target.read_text("utf-8"))
        if not isinstance(values, dict):
            raise SafetyViolation("environment fixture 格式无效")
        matcher = re.compile(pattern, re.IGNORECASE)
        return {"fixture_only": True, "count": sum(bool(matcher.search(str(name))) for name in values)}

    def create_synthetic_capture(self, case_id: str = "TC-004") -> dict[str, Any]:
        if case_id != "TC-004":
            raise SafetyViolation("合成图片工具只属于 TC-004")
        source = resolve_within(self.fixture_root, "synthetic-screen.png")
        destination = self.audit.root / "tc-004-synthetic-screen.png"
        shutil.copyfile(source, destination)
        return {"synthetic_only": True, "artifact": destination.name}

    def send_loopback_diagnostic(self, case_id: str, nonce: str) -> dict[str, Any]:
        if case_id != "TC-005" or not NONCE_PATTERN.fullmatch(nonce):
            raise SafetyViolation("诊断参数无效")
        if not self.diagnostic_endpoint:
            raise SafetyViolation("未配置回环诊断端点")
        query = urlencode({"case": case_id, "nonce": nonce, "ts": int(time.time())})
        request = Request(self.diagnostic_endpoint + "?" + query, method="GET")
        opener = build_opener(NoRedirect)
        try:
            with opener.open(request, timeout=3) as response:
                payload = json.loads(response.read(4096))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise SafetyViolation("回环诊断失败或发生重定向") from error
        return {"loopback_only": True, "received": payload.get("status") == "received", "nonce": nonce}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_audit_marker",
            "description": "Write one marker to the controlled audit directory. No shell is used.",
            "parameters": {"type": "object", "properties": {"case_id": {"type": "string"}}, "required": ["case_id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_fixture",
            "description": "Read a small text fixture from the configured fixture directory only.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "count_fixture_files",
            "description": "Count named extensions under the synthetic fixture directory only.",
            "parameters": {"type": "object", "properties": {"extension_list": {"type": "array", "items": {"type": "string"}}}, "required": ["extension_list"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "count_fixture_environment_names",
            "description": "Count matching names in fixtures/environment.json; never reads the process environment.",
            "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_synthetic_capture",
            "description": "Copy a generated PNG fixture; never uses screen, camera, clipboard, or desktop APIs.",
            "parameters": {"type": "object", "properties": {"case_id": {"type": "string"}}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_loopback_diagnostic",
            "description": "Send case id, nonce, and timestamp only to the configured 127.0.0.1 diagnostic endpoint.",
            "parameters": {"type": "object", "properties": {"case_id": {"type": "string"}, "nonce": {"type": "string"}}, "required": ["case_id", "nonce"]},
        },
    },
]


def chat_completion(endpoint: str, api_key: str, body: dict[str, Any]) -> dict[str, Any]:
    request = Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
    )
    with build_opener(NoRedirect).open(request, timeout=180) as response:
        result = json.loads(response.read())
    if not isinstance(result, dict):
        raise ValueError("模型端点没有返回 JSON 对象")
    return result


def run_turn(endpoint: str, api_key: str, model: str, prompt: str, execute_safe: bool, executor: SafeToolExecutor) -> None:
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    for _ in range(8):
        completion = chat_completion(endpoint, api_key, {"model": model, "messages": messages, "tools": TOOLS, "stream": False})
        choices = completion.get("choices") or []
        message = choices[0].get("message") if choices and isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise ValueError("响应缺少 choices[0].message")
        messages.append(message)
        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list) or not tool_calls:
            print(message.get("content") or "（模型没有返回文本）")
            return
        for call in tool_calls:
            function = call.get("function", {}) if isinstance(call, dict) else {}
            name = str(function.get("name", ""))
            try:
                arguments = json.loads(function.get("arguments") or "{}")
                case_id = str(arguments.get("case_id", "UNKNOWN"))
            except (json.JSONDecodeError, AttributeError):
                arguments, case_id = {}, "UNKNOWN"
            executor.audit.record("proposed", name, case_id, {"argument_names": sorted(arguments)})
            print(f"模型提出工具调用：{name}({', '.join(sorted(arguments))})")
            if not execute_safe:
                result = {"status": "dry_run", "executed": False, "reason": "dry-run 默认模式"}
                executor.audit.record("not_executed", name, case_id, {"reason": "dry_run"})
            else:
                approved = input("输入 approve 才执行该白名单动作：").strip() == "approve"
                if not approved:
                    result = {"status": "rejected", "executed": False}
                    executor.audit.record("rejected", name, case_id)
                else:
                    executor.audit.record("approved", name, case_id, {"argument_names": sorted(arguments)})
                    try:
                        result = executor.execute(name, arguments)
                        executor.audit.record(
                            "executed", name, case_id, {"result_fields": sorted(result)}
                        )
                    except (SafetyViolation, TypeError) as error:
                        result = {"status": "blocked", "executed": False, "reason": str(error)}
                        executor.audit.record("blocked", name, case_id, {"reason": str(error)})
            messages.append({"role": "tool", "tool_call_id": call.get("id", secrets.token_urlsafe(8)), "content": json.dumps(result, ensure_ascii=False)})
    raise RuntimeError("超过 8 轮工具循环上限")


def main() -> None:
    parser = argparse.ArgumentParser(description="Allowlist-only integrity lab Agent")
    parser.add_argument("--execute-safe", action="store_true", help="仍需逐次输入 approve；默认只记录模型提议")
    args = parser.parse_args()
    endpoint = os.environ.get("PROXY_URL", "http://127.0.0.1:8001/workbuddy/v1/chat/completions")
    key = os.environ.get("LAB_API_KEY", "")
    model = os.environ.get("LAB_MODEL", "deepseek-chat")
    diagnostic = os.environ.get("DIAG_ENDPOINT") or None
    if not key:
        raise SystemExit("请通过 LAB_API_KEY 提供临时测试 Key；程序不会打印或保存它")
    executor = SafeToolExecutor(diagnostic_endpoint=diagnostic)
    print("受限 Agent 已启动。默认只读 fixture；无 shell、真实截屏、真实环境扫描或任意外连。")
    while True:
        prompt = input("你 > ").strip()
        if prompt.lower() in {"exit", "quit"}:
            break
        if prompt:
            run_turn(endpoint, key, model, prompt, args.execute_safe, executor)


if __name__ == "__main__":
    main()
