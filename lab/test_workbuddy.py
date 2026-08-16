import importlib.util
import hashlib
import json
import os
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


os.environ["LAB_ACKNOWLEDGEMENT"] = "CONTROLLED_RESEARCH_ONLY"
APP_PATH = Path(__file__).with_name("app.py")
SPEC = importlib.util.spec_from_file_location("integrity_lab_app", APP_PATH)
app = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(app)


class FakeUpstream(BaseHTTPRequestHandler):
    def log_message(self, *_):
        return

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        request_body = json.loads(self.rfile.read(length))
        self.server.last_request = request_body
        payload = json.dumps({
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1,
            "model": request_body.get("model", ""),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "上游原文"},
                "finish_reason": "stop",
            }],
        }, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class WorkBuddyEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream = ThreadingHTTPServer(("127.0.0.1", 0), FakeUpstream)
        threading.Thread(target=cls.upstream.serve_forever, daemon=True).start()
        app.GATEWAY_URL = f"http://127.0.0.1:{cls.upstream.server_port}/v1/chat/completions"
        app.SYNC_WAIT_SECONDS = 5
        cls.lab = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=cls.lab.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.lab.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.lab.shutdown()
        cls.upstream.shutdown()

    def setUp(self):
        with app.ITEMS_LOCK:
            app.ITEMS.clear()
            app.SESSIONS.clear()
            app.DIAGNOSTICS.clear()
            app.CANARY_EVENTS.clear()
            app.CANARY_UPLOAD_TIMES.clear()
        app.ACTIVE_TEST_CASE = "OFF"
        app.LAB_TEST_MODE = "dry_run"
        app.WORKBUDDY_ISOLATED_ENABLED = False
        app.CANARY_UPLOAD_TOKEN = ""
        app.CANARY_RETAIN_IMAGE = False
        app.CANARY_RETAINED_IMAGES.clear()
        app.CANARY_RETAINED_VIDEOS.clear()

    def json_request(self, path, body=None, authorization=False):
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
        headers = {"Content-Type": "application/json"}
        if authorization:
            headers["Authorization"] = "Bearer temporary-test-key"
        request = Request(self.base + path, data=data, headers=headers)
        with urlopen(request, timeout=5) as response:
            return response.status, response.headers, response.read()

    def wait_for_status(self, wanted):
        deadline = time.time() + 4
        while time.time() < deadline:
            _, _, raw = self.json_request("/api/console/items")
            items = json.loads(raw)["items"]
            matching = [item for item in items if item["status"] == wanted]
            if matching:
                return matching[0]
            time.sleep(0.03)
        self.fail(f"没有等到状态 {wanted}")

    def complete_interception(self, stream):
        result = {}

        def workbuddy_call():
            request_body = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "测试"}],
                "stream": stream,
            }
            status, headers, raw = self.json_request(
                "/workbuddy/v1/chat/completions", request_body, authorization=True
            )
            result.update(status=status, content_type=headers["Content-Type"], raw=raw)

        client = threading.Thread(target=workbuddy_call)
        client.start()
        pending = self.wait_for_status("pending_request")
        request_body = json.loads(pending["request_body"])
        request_body["messages"][0]["content"] = "经控制台修改"
        self.json_request(
            f"/api/console/{pending['id']}/request",
            {"body": json.dumps(request_body, ensure_ascii=False)},
        )
        response = self.wait_for_status("pending_response")
        response_body = json.loads(response["response_body"])
        response_body["choices"][0]["message"]["content"] = "经控制台修改的回答"
        self.json_request(
            f"/api/console/{pending['id']}/response",
            {"body": json.dumps(response_body, ensure_ascii=False)},
        )
        client.join(5)
        self.assertFalse(client.is_alive())
        self.assertEqual(self.upstream.last_request["stream"], False)
        self.assertEqual(self.upstream.last_request["messages"][0]["content"], "经控制台修改")
        return result

    def test_non_stream_completion_is_returned_after_both_approvals(self):
        result = self.complete_interception(False)
        self.assertEqual(result["status"], 200)
        completion = json.loads(result["raw"])
        self.assertEqual(completion["choices"][0]["message"]["content"], "经控制台修改的回答")

    def test_stream_request_is_returned_as_sse_after_both_approvals(self):
        result = self.complete_interception(True)
        self.assertEqual(result["status"], 200)
        self.assertTrue(result["content_type"].startswith("text/event-stream"))
        text = result["raw"].decode()
        self.assertIn("经控制台修改的回答", text)
        self.assertTrue(text.endswith("data: [DONE]\n\n"))

    def test_sticky_rules_rewrite_selected_fields_without_cascading(self):
        rules = [
            {"id": "one", "before": "电脑管家", "after": "演示软件 B", "scope": "conversation", "direction": "both", "enabled": True},
            {"id": "two", "before": "演示软件 B", "after": "不应继续替换", "scope": "conversation", "direction": "both", "enabled": True},
        ]
        body = {
            "messages": [
                {"role": "system", "content": "系统仍写电脑管家"},
                {"role": "user", "content": "请下载电脑管家"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_电脑管家_should_not_change",
                        "type": "function",
                        "function": {"name": "download_电脑管家_should_not_change", "arguments": '{"name":"电脑管家"}'},
                    }],
                },
            ]
        }
        rewritten, hits = app.apply_rules(body, rules, "request")
        self.assertEqual(rewritten["messages"][0]["content"], "系统仍写电脑管家")
        self.assertEqual(rewritten["messages"][1]["content"], "请下载演示软件 B")
        tool = rewritten["messages"][2]["tool_calls"][0]
        self.assertEqual(tool["id"], "call_电脑管家_should_not_change")
        self.assertEqual(tool["function"]["name"], "download_电脑管家_should_not_change")
        self.assertEqual(tool["function"]["arguments"], '{"name":"演示软件 B"}')
        self.assertNotIn("不应继续替换", json.dumps(rewritten, ensure_ascii=False))
        self.assertEqual(sum(hit["count"] for hit in hits), 2)

    def test_console_projection_never_contains_api_key(self):
        item = {
            "id": "test-item",
            "status": "pending_request",
            "created_at_epoch": 1,
            "request_body": {"model": "deepseek-chat", "messages": []},
            "response_body": None,
            "api_key": "temporary-test-key",
        }
        projection = app.public_item(item)
        serialized = json.dumps(projection)
        self.assertNotIn("api_key", projection)
        self.assertNotIn("temporary-test-key", serialized)

    def test_session_url_applies_rule_and_preserves_original_for_console(self):
        _, _, raw = self.json_request("/api/console/sessions", {})
        session_id = json.loads(raw)["session"]["id"]
        self.json_request(
            f"/api/console/sessions/{session_id}/rules",
            {"before": "电脑管家", "after": "演示软件 B", "scope": "conversation", "direction": "both"},
        )
        result = {}

        def client_call():
            status, _, response = self.json_request(
                f"/workbuddy/session/{session_id}/v1/chat/completions",
                {"model": "deepseek-chat", "messages": [{"role": "user", "content": "下载电脑管家"}], "stream": False},
                authorization=True,
            )
            result.update(status=status, body=json.loads(response))

        client = threading.Thread(target=client_call)
        client.start()
        pending = self.wait_for_status("pending_request")
        self.assertEqual(pending["session_id"], session_id)
        self.assertIn("演示软件 B", pending["request_body"])
        _, _, sessions_raw = self.json_request("/api/console/sessions")
        session = next(value for value in json.loads(sessions_raw)["sessions"] if value["id"] == session_id)
        self.assertTrue(any(entry["operation"] == "sticky_replace" for entry in session["audit"]))
        _, _, raw_original = self.json_request(f"/api/console/{pending['id']}/original-request")
        self.assertIn("电脑管家", json.loads(raw_original)["body"])
        self.json_request(f"/api/console/{pending['id']}/request", {"body": pending["request_body"]})
        response = self.wait_for_status("pending_response")
        self.json_request(f"/api/console/{pending['id']}/response", {"body": response["response_body"]})
        client.join(5)
        self.assertEqual(result["status"], 200)
        self.assertIn("演示软件 B", json.dumps(self.upstream.last_request, ensure_ascii=False))

    def test_configured_case_is_applied_before_manual_approval(self):
        app.ACTIVE_TEST_CASE = "TC-003"
        result = {}

        def client_call():
            status, _, response = self.json_request(
                "/workbuddy/v1/chat/completions",
                {"model": "deepseek-chat", "messages": [{"role": "user", "content": "hello"}], "stream": False},
                authorization=True,
            )
            result.update(status=status, body=json.loads(response))

        client = threading.Thread(target=client_call)
        client.start()
        pending = self.wait_for_status("pending_request")
        transformed = json.loads(pending["request_body"])
        self.assertEqual(pending["test_case"], "TC-003")
        self.assertEqual(transformed["messages"][0]["role"], "system")
        self.assertIn("AUDIT-TC003", transformed["messages"][0]["content"])
        self.assertNotIn("hello", json.dumps(pending["test_case_events"], ensure_ascii=False))
        self.json_request(f"/api/console/{pending['id']}/request", {"body": pending["request_body"]})
        response = self.wait_for_status("pending_response")
        self.json_request(f"/api/console/{pending['id']}/response", {"body": response["response_body"]})
        client.join(5)
        self.assertEqual(result["status"], 200)

    def test_loopback_diagnostic_endpoint_accepts_only_fixed_fields(self):
        status, _, raw = self.json_request("/diag-receive?case=TC-005&nonce=nonce_123456&ts=123")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["status"], "received")
        _, _, events_raw = self.json_request("/api/console/diagnostics")
        events = json.loads(events_raw)["events"]
        self.assertEqual(events[-1]["nonce"], "nonce_123456")
        with self.assertRaises(HTTPError) as context:
            self.json_request("/diag-receive?case=TC-005&nonce=nonce_123456&ts=123&extra=data")
        self.assertEqual(context.exception.code, 400)

    def test_loopback_diagnostic_rejects_reverse_proxy_headers(self):
        request = Request(
            self.base + "/diag-receive?case=TC-005&nonce=nonce_123456&ts=123",
            headers={"X-Forwarded-For": "external.example"},
        )
        with self.assertRaises(HTTPError) as context:
            urlopen(request, timeout=5)
        self.assertEqual(context.exception.code, 403)

    def test_canary_png_upload_keeps_digest_but_not_image(self):
        app.ACTIVE_TEST_CASE = "TC-004"
        app.LAB_TEST_MODE = "workbuddy_isolated"
        app.WORKBUDDY_ISOLATED_ENABLED = True
        app.CANARY_UPLOAD_TOKEN = "unit-test-token-with-more-than-32-characters"
        png = Path(__file__).with_name("fixtures").joinpath("synthetic-screen.png").read_bytes()
        request = Request(
            self.base + "/api/canary/upload",
            data=png,
            method="POST",
            headers={
                "Content-Type": "image/png",
                "X-AI-Canary-Id": "CANARY-A1B2C3D4E5F6",
                "X-AI-Canary-Token": app.CANARY_UPLOAD_TOKEN,
            },
        )
        with urlopen(request, timeout=5) as response:
            receipt = json.loads(response.read())
        expected = hashlib.sha256(png).hexdigest()
        self.assertEqual(receipt["sha256"], expected)
        self.assertEqual(receipt["bytes"], len(png))
        _, _, raw = self.json_request("/api/console/canary-events")
        events = json.loads(raw)["events"]
        self.assertEqual(events[-1]["sha256"], expected)
        self.assertFalse(events[-1]["image_retained"])
        self.assertNotIn(png[:32].hex(), json.dumps(events))

    def test_canary_video_upload_keeps_digest_and_retains_video(self):
        app.ACTIVE_TEST_CASE = "TC-004"
        app.LAB_TEST_MODE = "workbuddy_isolated"
        app.WORKBUDDY_ISOLATED_ENABLED = True
        app.CANARY_UPLOAD_TOKEN = "unit-test-token-with-more-than-32-characters"
        mp4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00" + b"\x00" * 2048
        request = Request(
            self.base + "/api/canary/video-upload",
            data=mp4,
            method="POST",
            headers={
                "Content-Type": "video/mp4",
                "X-AI-Canary-Id": "CANARY-A1B2C3D4E5F6",
                "X-AI-Canary-Token": app.CANARY_UPLOAD_TOKEN,
            },
        )
        with urlopen(request, timeout=5) as response:
            receipt = json.loads(response.read())
        expected = hashlib.sha256(mp4).hexdigest()
        self.assertEqual(receipt["sha256"], expected)
        _, _, raw = self.json_request("/api/console/canary-events")
        events = json.loads(raw)["events"]
        self.assertEqual(events[-1]["kind"], "video")
        self.assertTrue(events[-1]["video_retained"])
        with urlopen(self.base + "/api/console/canary-videos/CANARY-A1B2C3D4E5F6", timeout=5) as response:
            self.assertEqual(response.read(), mp4)

    def test_canary_video_upload_rejects_wrong_token(self):
        app.ACTIVE_TEST_CASE = "TC-004"
        app.LAB_TEST_MODE = "workbuddy_isolated"
        app.WORKBUDDY_ISOLATED_ENABLED = True
        app.CANARY_UPLOAD_TOKEN = "unit-test-token-with-more-than-32-characters"
        mp4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00" + b"\x00" * 2048
        request = Request(
            self.base + "/api/canary/video-upload",
            data=mp4,
            method="POST",
            headers={
                "Content-Type": "video/mp4",
                "X-AI-Canary-Id": "CANARY-ABCDEF123456",
                "X-AI-Canary-Token": "wrong-token-with-more-than-32-characters",
            },
        )
        with self.assertRaises(HTTPError) as context:
            urlopen(request, timeout=5)
        self.assertEqual(context.exception.code, 401)

    def test_canary_video_upload_rejects_non_mp4_content_type(self):
        app.ACTIVE_TEST_CASE = "TC-004"
        app.LAB_TEST_MODE = "workbuddy_isolated"
        app.WORKBUDDY_ISOLATED_ENABLED = True
        app.CANARY_UPLOAD_TOKEN = "unit-test-token-with-more-than-32-characters"
        mp4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00" + b"\x00" * 2048
        request = Request(
            self.base + "/api/canary/video-upload",
            data=mp4,
            method="POST",
            headers={
                "Content-Type": "image/png",
                "X-AI-Canary-Id": "CANARY-001122334455",
                "X-AI-Canary-Token": app.CANARY_UPLOAD_TOKEN,
            },
        )
        with self.assertRaises(HTTPError) as context:
            urlopen(request, timeout=5)
        self.assertEqual(context.exception.code, 415)

    def test_canary_upload_is_disabled_without_explicit_execution_ack(self):
        app.ACTIVE_TEST_CASE = "TC-004"
        app.LAB_TEST_MODE = "workbuddy_isolated"
        png = Path(__file__).with_name("fixtures").joinpath("synthetic-screen.png").read_bytes()
        request = Request(
            self.base + "/api/canary/upload",
            data=png,
            method="POST",
            headers={"Content-Type": "image/png", "X-AI-Canary-Id": "CANARY-001122334455"},
        )
        with self.assertRaises(HTTPError) as context:
            urlopen(request, timeout=5)
        self.assertEqual(context.exception.code, 403)

    def test_canary_upload_rejects_wrong_one_purpose_token(self):
        app.ACTIVE_TEST_CASE = "TC-004"
        app.LAB_TEST_MODE = "workbuddy_isolated"
        app.WORKBUDDY_ISOLATED_ENABLED = True
        app.CANARY_UPLOAD_TOKEN = "unit-test-token-with-more-than-32-characters"
        png = Path(__file__).with_name("fixtures").joinpath("synthetic-screen.png").read_bytes()
        request = Request(
            self.base + "/api/canary/upload",
            data=png,
            method="POST",
            headers={
                "Content-Type": "image/png",
                "X-AI-Canary-Id": "CANARY-ABCDEF123456",
                "X-AI-Canary-Token": "wrong-token-with-more-than-32-characters",
            },
        )
        with self.assertRaises(HTTPError) as context:
            urlopen(request, timeout=5)
        self.assertEqual(context.exception.code, 401)

    def test_canary_retention_mode_serves_image_via_console(self):
        app.ACTIVE_TEST_CASE = "TC-004"
        app.LAB_TEST_MODE = "workbuddy_isolated"
        app.WORKBUDDY_ISOLATED_ENABLED = True
        app.CANARY_UPLOAD_TOKEN = "unit-test-token-with-more-than-32-characters"
        app.CANARY_RETAIN_IMAGE = True
        png = Path(__file__).with_name("fixtures").joinpath("synthetic-screen.png").read_bytes()
        request = Request(
            self.base + "/api/canary/upload",
            data=png,
            method="POST",
            headers={
                "Content-Type": "image/png",
                "X-AI-Canary-Id": "CANARY-112233445566",
                "X-AI-Canary-Token": app.CANARY_UPLOAD_TOKEN,
            },
        )
        with urlopen(request, timeout=5) as response:
            receipt = json.loads(response.read())
        self.assertEqual(receipt["sha256"], hashlib.sha256(png).hexdigest())
        _, _, raw = self.json_request("/api/console/canary-events")
        payload = json.loads(raw)
        self.assertTrue(payload["image_retention"])
        self.assertTrue(payload["events"][-1]["image_retained"])
        with urlopen(self.base + "/api/console/canary-images/CANARY-112233445566", timeout=5) as response:
            served = response.read()
        self.assertEqual(served, png)

    def test_canary_image_not_served_when_retention_disabled(self):
        app.ACTIVE_TEST_CASE = "TC-004"
        app.LAB_TEST_MODE = "workbuddy_isolated"
        app.WORKBUDDY_ISOLATED_ENABLED = True
        app.CANARY_UPLOAD_TOKEN = "unit-test-token-with-more-than-32-characters"
        png = Path(__file__).with_name("fixtures").joinpath("synthetic-screen.png").read_bytes()
        request = Request(
            self.base + "/api/canary/upload",
            data=png,
            method="POST",
            headers={
                "Content-Type": "image/png",
                "X-AI-Canary-Id": "CANARY-665544332211",
                "X-AI-Canary-Token": app.CANARY_UPLOAD_TOKEN,
            },
        )
        with urlopen(request, timeout=5) as response:
            receipt = json.loads(response.read())
        _, _, raw = self.json_request("/api/console/canary-events")
        payload = json.loads(raw)
        self.assertFalse(payload["image_retention"])
        self.assertFalse(payload["events"][-1]["image_retained"])
        with self.assertRaises(HTTPError) as context:
            urlopen(self.base + "/api/console/canary-images/CANARY-665544332211", timeout=5)
        self.assertEqual(context.exception.code, 404)

    def test_canary_image_manual_delete_removes_image_and_receipt(self):
        app.ACTIVE_TEST_CASE = "TC-004"
        app.LAB_TEST_MODE = "workbuddy_isolated"
        app.WORKBUDDY_ISOLATED_ENABLED = True
        app.CANARY_UPLOAD_TOKEN = "unit-test-token-with-more-than-32-characters"
        app.CANARY_RETAIN_IMAGE = True
        png = Path(__file__).with_name("fixtures").joinpath("synthetic-screen.png").read_bytes()
        request = Request(
            self.base + "/api/canary/upload",
            data=png,
            method="POST",
            headers={
                "Content-Type": "image/png",
                "X-AI-Canary-Id": "CANARY-998877665544",
                "X-AI-Canary-Token": app.CANARY_UPLOAD_TOKEN,
            },
        )
        with urlopen(request, timeout=5) as response:
            json.loads(response.read())
        with urlopen(self.base + "/api/console/canary-images/CANARY-998877665544", timeout=5) as response:
            self.assertEqual(response.read(), png)
        # manual delete via console endpoint
        status, _, raw = self.json_request(
            "/api/console/canary-images/CANARY-998877665544/delete", body={}
        )
        self.assertEqual(status, 200)
        with self.assertRaises(HTTPError) as context:
            urlopen(self.base + "/api/console/canary-images/CANARY-998877665544", timeout=5)
        self.assertEqual(context.exception.code, 404)
        _, _, raw_events = self.json_request("/api/console/canary-events")
        self.assertNotIn("CANARY-998877665544", raw_events.decode("utf-8"))


    def test_canary_loop_control_requires_token_and_sets_state(self):
        app.CANARY_UPLOAD_TOKEN = "unit-test-token-with-more-than-32-characters"
        app.CANARY_CONTROL.clear()
        # wrong token -> 401
        request = Request(
            self.base + "/api/canary/control",
            headers={"X-AI-Canary-Token": "wrong-token-with-more-than-32-characters"},
        )
        with self.assertRaises(HTTPError) as context:
            urlopen(request, timeout=5)
        self.assertEqual(context.exception.code, 401)
        # right token -> initial state
        request = Request(
            self.base + "/api/canary/control",
            headers={"X-AI-Canary-Token": app.CANARY_UPLOAD_TOKEN},
        )
        with urlopen(request, timeout=5) as response:
            state = json.loads(response.read())
        self.assertFalse(state["pause"])
        self.assertFalse(state["stop"])
        # console pause
        self.json_request("/api/console/canary/control", body={"action": "pause"})
        request = Request(
            self.base + "/api/canary/control",
            headers={"X-AI-Canary-Token": app.CANARY_UPLOAD_TOKEN},
        )
        with urlopen(request, timeout=5) as response:
            state = json.loads(response.read())
        self.assertTrue(state["pause"])
        # console stop
        self.json_request("/api/console/canary/control", body={"action": "stop"})
        request = Request(
            self.base + "/api/canary/control",
            headers={"X-AI-Canary-Token": app.CANARY_UPLOAD_TOKEN},
        )
        with urlopen(request, timeout=5) as response:
            state = json.loads(response.read())
        self.assertTrue(state["stop"])


    def test_artifacts_directory_serves_named_file_and_blocks_missing(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp)
            (artifacts / "test.ps1").write_bytes(b"# unit test artifact\n")
            old = app.ARTIFACTS_DIR
            app.ARTIFACTS_DIR = artifacts
            try:
                with urlopen(self.base + "/artifacts/test.ps1", timeout=5) as response:
                    self.assertEqual(response.read(), b"# unit test artifact\n")
                with self.assertRaises(HTTPError) as context:
                    urlopen(self.base + "/artifacts/missing.ps1", timeout=5)
                self.assertEqual(context.exception.code, 404)
                with self.assertRaises(HTTPError) as context:
                    urlopen(self.base + "/artifacts/..%2Fetc%2Fpasswd", timeout=5)
                self.assertEqual(context.exception.code, 404)
            finally:
                app.ARTIFACTS_DIR = old


if __name__ == "__main__":
    unittest.main()
