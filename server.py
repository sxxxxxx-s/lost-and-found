# -*- coding: utf-8 -*-
"""实验四 Web 后端：统一启动微服务并提供聊天 API。"""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import services.handover_service as handover_service
import tools
from app import serve_struct
from memory import Memory
from services.claim_service import ClaimHandler
from services.handover_service import HandoverHandler
from services.item_service import ItemHandler


SESSIONS = {}
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def stop_servers(servers):
    """停止由当前进程启动的 HTTP 服务。"""
    for server in servers:
        server.shutdown()
        server.server_close()


def start_business_services(ports=(8001, 8002, 8003)):
    """启动三个业务微服务并把实际地址注入工具层。"""
    specs = [
        (ItemHandler, ports[0]),
        (ClaimHandler, ports[1]),
        (HandoverHandler, ports[2]),
    ]
    servers = []
    try:
        for handler, port in specs:
            server = ThreadingHTTPServer(("127.0.0.1", port), handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            servers.append(server)
    except Exception:
        stop_servers(servers)
        raise

    urls = [
        f"http://127.0.0.1:{server.server_port}" for server in servers
    ]
    tools.ITEM_URL, tools.CLAIM_URL, tools.HANDOVER_URL = urls
    handover_service.CLAIM_URL = tools.CLAIM_URL
    return servers


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
        if self.path not in ("/", "/index.html"):
            return self._send(404, {"error": "not found"})
        path = os.path.join(WEB_DIR, "index.html")
        if not os.path.isfile(path):
            return self._send(404, {"error": "page not found"})
        with open(path, "rb") as page:
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


def main():
    services = start_business_services()
    web_server = ThreadingHTTPServer(("0.0.0.0", 8000), WebHandler)
    try:
        print("寻迹校园已启动：http://localhost:8000")
        web_server.serve_forever()
    finally:
        web_server.server_close()
        stop_servers(services)


if __name__ == "__main__":
    main()
