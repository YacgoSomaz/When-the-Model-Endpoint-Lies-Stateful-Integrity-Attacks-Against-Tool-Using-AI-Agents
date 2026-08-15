import importlib.util
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
        app.ACTIVE_TEST_CASE = "OFF"

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


if __name__ == "__main__":
    unittest.main()
