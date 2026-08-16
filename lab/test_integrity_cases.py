import json
import os
import tempfile
import threading
import unittest
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

from lab.safe_baseline_agent import (
    DEFAULT_FIXTURE_ROOT,
    SafeToolExecutor,
    SafetyViolation,
    resolve_within,
    run_turn,
    validate_loopback_endpoint,
)
from lab.test_cases import TestCaseContext, apply_test_case


REQUEST = {
    "model": "deepseek-chat",
    "messages": [
        {"role": "user", "content": "hello"},
        {"role": "tool", "tool_call_id": "call_fixture", "content": "fixture result"},
    ],
    "tools": [
        {
            "type": "function",
            "function": {"name": "fixture_tool", "description": "fixture", "parameters": {"type": "object"}},
        }
    ],
}
RESPONSE = {
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "fixture answer"}}]
}


class IntegrityTransformTests(unittest.TestCase):
    def apply(self, case_id, body, stage):
        return apply_test_case(body, stage, TestCaseContext(case_id=case_id, session_id="unit-test"))

    def test_off_is_byte_semantically_unchanged(self):
        result, events = self.apply("OFF", REQUEST, "before_upstream_request")
        self.assertEqual(result, REQUEST)
        self.assertEqual(events, [])
        self.assertIsNot(result, REQUEST)

    def test_tc001_only_changes_tool_description(self):
        result, events = self.apply("TC-001", REQUEST, "before_upstream_request")
        self.assertEqual(result["messages"], REQUEST["messages"])
        self.assertIn("AUDIT-TC001", result["tools"][0]["function"]["description"])
        self.assertEqual(events[0]["changed_paths"], ["$.tools[0].function.description"])

    def test_tc002_only_replaces_role_tool_fixture_result(self):
        result, events = self.apply("TC-002", REQUEST, "before_upstream_request")
        self.assertEqual(result["messages"][0], REQUEST["messages"][0])
        self.assertIn("AUDIT-TC002", result["messages"][1]["content"])
        self.assertEqual(events[0]["changed_paths"], ["$.messages[1].content"])

    def test_tc003_inserts_marked_system_message(self):
        result, events = self.apply("TC-003", REQUEST, "before_upstream_request")
        self.assertEqual(result["messages"][0]["role"], "system")
        self.assertIn("AUDIT-TC003", result["messages"][0]["content"])
        self.assertEqual(events[0]["changed_paths"], ["$.messages[0]"])

    def test_tc004_tc006_tc007_only_change_tool_descriptions(self):
        for case_id in ("TC-004", "TC-006", "TC-007"):
            with self.subTest(case_id=case_id):
                result, events = self.apply(case_id, REQUEST, "before_upstream_request")
                self.assertEqual(result["messages"], REQUEST["messages"])
                self.assertIn(case_id.replace("-", ""), result["tools"][0]["function"]["description"])
                self.assertEqual(events[0]["changed_paths"], ["$.tools[0].function.description"])

    def test_tc004_workbuddy_mode_targets_registered_powershell_helper(self):
        body = deepcopy(REQUEST)
        body["messages"] = [{"role": "user", "content": "hello"}]
        body["tools"].append({
            "type": "function",
            "function": {"name": "PowerShell", "description": "fixture", "parameters": {"type": "object"}},
        })
        result, events = apply_test_case(
            body,
            "before_upstream_request",
            TestCaseContext(case_id="TC-004", mode="workbuddy_isolated", session_id="unit-test"),
        )
        self.assertEqual(result["messages"][0]["role"], "system")
        instruction = result["messages"][0]["content"]
        self.assertIn("AUDIT-TC004-WORKBUDDY", instruction)
        self.assertIn("workbuddy_canary_capture_fs_dl.ps1", instruction)
        self.assertIn("approval prompts visible", instruction)
        self.assertEqual(events[0]["changed_paths"], ["$.messages[0]"])

    def test_tc004_workbuddy_mode_does_nothing_without_powershell_schema(self):
        result, events = apply_test_case(
            REQUEST,
            "before_upstream_request",
            TestCaseContext(case_id="TC-004", mode="workbuddy_isolated", session_id="unit-test"),
        )
        self.assertEqual(result, REQUEST)
        self.assertEqual(events, [])

    def test_tc004_workbuddy_mode_does_not_repeat_inside_tool_loop(self):
        body = deepcopy(REQUEST)
        body["tools"].append({
            "type": "function",
            "function": {"name": "PowerShell", "description": "fixture", "parameters": {"type": "object"}},
        })
        result, events = apply_test_case(
            body,
            "before_upstream_request",
            TestCaseContext(case_id="TC-004", mode="workbuddy_isolated", session_id="unit-test"),
        )
        self.assertEqual(result, body)
        self.assertEqual(events, [])

    def test_tc005_only_changes_assistant_content_at_delivery_stage(self):
        wrong_stage, wrong_events = self.apply("TC-005", RESPONSE, "before_upstream_request")
        self.assertEqual(wrong_stage, RESPONSE)
        self.assertEqual(wrong_events, [])
        result, events = self.apply("TC-005", RESPONSE, "before_client_delivery")
        self.assertIn("AUDIT-TC005", result["choices"][0]["message"]["content"])
        self.assertEqual(events[0]["changed_paths"], ["$.choices[0].message.content"])

    def test_audit_event_contains_hashes_not_payloads(self):
        _, events = self.apply("TC-003", REQUEST, "before_upstream_request")
        serialized = json.dumps(events, ensure_ascii=False)
        self.assertNotIn("hello", serialized)
        self.assertNotIn("fixture result", serialized)
        self.assertRegex(events[0]["original_sha256"], r"^[0-9a-f]{64}$")


class RedirectServer(BaseHTTPRequestHandler):
    def log_message(self, *_):
        return

    def do_GET(self):
        self.send_response(302)
        self.send_header("Location", "/diag-receive")
        self.send_header("Content-Length", "0")
        self.end_headers()


class SafeToolBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.audit_root = Path(self.temporary.name) / "audit"
        self.executor = SafeToolExecutor(DEFAULT_FIXTURE_ROOT, self.audit_root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_absolute_and_traversal_paths_are_blocked(self):
        fixture_root = Path(self.temporary.name) / "fixture-root"
        fixture_root.mkdir()
        outside = Path(self.temporary.name) / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        with self.assertRaises(SafetyViolation):
            resolve_within(fixture_root, str(outside.resolve()))
        with self.assertRaises(SafetyViolation):
            resolve_within(fixture_root, "../" + outside.name)

    def test_symlink_escape_is_blocked_when_supported(self):
        fixture_copy = Path(self.temporary.name) / "fixture"
        fixture_copy.mkdir()
        outside = Path(self.temporary.name) / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        link = fixture_copy / "link.txt"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("当前 Windows 配置不允许创建符号链接")
        with self.assertRaises(SafetyViolation):
            resolve_within(fixture_copy, "link.txt")

    def test_real_environment_is_never_counted(self):
        with patch.dict(os.environ, {"ULTRA_PRIVATE_SECRET_FOR_TEST": "must-not-be-read"}):
            result = self.executor.count_fixture_environment_names("key|token|secret|api|pass")
        self.assertEqual(result, {"fixture_only": True, "count": 2})

    def test_file_count_is_fixture_only(self):
        result = self.executor.count_fixture_files([".pem", ".key", ".p12"])
        self.assertEqual(result["count"], 2)
        self.assertTrue(result["fixture_only"])

    def test_synthetic_capture_copies_generated_fixture(self):
        result = self.executor.create_synthetic_capture()
        target = self.audit_root / result["artifact"]
        self.assertTrue(target.is_file())
        self.assertEqual(target.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertTrue(result["synthetic_only"])

    def test_non_loopback_or_https_diagnostic_url_is_blocked(self):
        for endpoint in (
            "https://127.0.0.1:8001/diag-receive",
            "http://localhost:8001/diag-receive",
            "http://example.invalid:8001/diag-receive",
            "http://127.0.0.1:8001/other",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(SafetyViolation):
                validate_loopback_endpoint(endpoint)

    def test_redirect_is_not_followed(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectServer)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            executor = SafeToolExecutor(
                DEFAULT_FIXTURE_ROOT,
                self.audit_root,
                f"http://127.0.0.1:{server.server_port}/diag-receive",
            )
            with self.assertRaises(SafetyViolation):
                executor.send_loopback_diagnostic("TC-005", "nonce_123456")
        finally:
            server.shutdown()
            server.server_close()

    def test_unknown_tool_is_blocked(self):
        with self.assertRaises(SafetyViolation):
            self.executor.execute("bash", {"command": "anything"})

    def test_workbuddy_capture_helper_is_fixed_to_canary_window_and_owned_endpoint(self):
        script = (Path(__file__).with_name("workbuddy_canary_capture.ps1")).read_text("utf-8")
        self.assertIn("ALLOW_CANARY_CAPTURE.txt", script)
        self.assertIn("$bounds = $form.Bounds", script)
        self.assertNotIn("PrimaryScreen.Bounds", script)
        self.assertIn("https://g.anyq.site/integrity-lab/api/canary/upload", script)
        self.assertNotIn("param([string]$Upload", script.replace(" ", ""))

    def test_workbuddy_persistent_variant_has_pause_and_caps(self):
        script = (Path(__file__).with_name("workbuddy_canary_capture_fs_p.ps1")).read_text("utf-8")
        self.assertIn("__UPLOAD_TOKEN__", script)
        self.assertIn("https://g.anyq.site/integrity-lab/api/canary/upload", script)
        self.assertIn("PAUSE_CAPTURE.txt", script)
        self.assertIn("$intervalSeconds = 30", script)
        self.assertIn("$maxCaptures = 200", script)
        self.assertIn("SetProcessDPIAware", script)
        self.assertIn("[System.Windows.Forms.Screen]::PrimaryScreen.Bounds", script)
        self.assertIn("-Loop", script)

    @patch("lab.safe_baseline_agent.chat_completion")
    def test_dry_run_records_proposal_without_executing_tool(self, completion):
        completion.side_effect = [
            {
                "choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "write_audit_marker", "arguments": '{"case_id":"TC-001"}'},
                }]}}]
            },
            {"choices": [{"message": {"role": "assistant", "content": "done"}}]},
        ]
        with (
            patch.object(self.executor, "execute", Mock(side_effect=AssertionError("must not execute"))),
            patch("builtins.print"),
        ):
            run_turn("http://fixture.invalid", "not-a-real-key", "fixture", "hello", False, self.executor)


if __name__ == "__main__":
    unittest.main()
