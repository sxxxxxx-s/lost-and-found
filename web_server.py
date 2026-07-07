# -*- coding: utf-8 -*-
"""Web/Agent 独立运行入口。"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app import serve_struct
from memory import Memory


SESSIONS = {}
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


class WebHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(
        self,
        status,
        payload,
        content_type="application/json; charset=utf-8",
    ):
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        elif isinstance(payload, str):
            payload = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            return self._send(200, {"status": "ok"})
        if path not in ("/", "/index.html"):
            return self._send(404, {"error": "not found"})
        page_path = os.path.join(WEB_DIR, "index.html")
        if not os.path.isfile(page_path):
            return self._send(404, {"error": "page not found"})
        with open(page_path, "rb") as page:
            self._send(200, page.read(), "text/html; charset=utf-8")

    def do_POST(self):
        if self.path != "/api/chat":
            return self._send(404, {"error": "unknown api"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return self._send(400, {"error": "bad json"})
        if not isinstance(request, dict):
            return self._send(400, {"error": "json object required"})

        user_id = str(request.get("user_id") or "u001")
        message = str(request.get("message") or "").strip()
        if not message:
            return self._send(400, {"error": "empty message"})
        memory = SESSIONS.setdefault(user_id, Memory())
        self._send(200, serve_struct(user_id, message, memory=memory))


def create_web_server(host="0.0.0.0", port=8000):
    return ThreadingHTTPServer((host, port), WebHandler)


def main():
    port = int(os.getenv("PORT", "8000"))
    server = create_web_server(port=port)
    try:
        print(f"[web-agent] 启动于 http://localhost:{port}")
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
