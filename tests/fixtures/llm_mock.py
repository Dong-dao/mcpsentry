"""本地 OpenAI-compatible /chat/completions mock（语义层集成测试共享）。"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class MockLLMServer:
    """记录请求、返回固定 content 的假端点。经 DASHSCOPE_BASE_URL 指到本服务。"""

    def __init__(self, response: str):
        self.calls: list[dict] = []
        self.response = response
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                outer.calls.append(json.loads(self.rfile.read(length)))
                payload = json.dumps(
                    {"choices": [{"message": {"content": outer.response}}]},
                    ensure_ascii=False,
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args) -> None:
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self) -> "MockLLMServer":
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
