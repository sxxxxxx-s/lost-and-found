# -*- coding: utf-8 -*-
"""交接微服务（端口 8003）。"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlencode, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data import APPOINTMENTS, HANDOVER_SLOTS


PORT = 8003
CLAIM_URL = os.getenv("CLAIM_URL", "http://localhost:8002")


def _next_appointment_id():
    return f"AP{len(APPOINTMENTS) + 1:04d}"


def _query_claim(claim_id, user_id):
    query = urlencode({"user_id": user_id})
    url = f"{CLAIM_URL}/claims/{claim_id}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            payload = json.loads(error.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {"error": f"认领服务请求失败:HTTP {error.code}"}
        return error.code, payload
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return 503, {"error": f"认领服务不可用:{error}"}


class HandoverHandler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def log_message(self, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            return self._send(200, {"status": "ok"})
        if parsed.path == "/slots":
            item_id = parse_qs(parsed.query).get("item_id", [""])[0]
            slots = HANDOVER_SLOTS.get(item_id)
            if slots is None:
                return self._send(404, {"error": "失物不存在或无交接时段"})
            return self._send(200, slots)

        match = re.fullmatch(r"/appointments/([^/]+)", parsed.path)
        if not match:
            return self._send(404, {"error": "未知路径"})
        claim_id = unquote(match.group(1))
        appointment = APPOINTMENTS.get(claim_id)
        if appointment is None:
            return self._send(404, {"error": "交接预约不存在"})
        user_id = parse_qs(parsed.query).get("user_id", [""])[0]
        if user_id != appointment["user_id"]:
            return self._send(403, {"error": "无权查询该交接预约"})
        self._send(200, appointment)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/appointments":
            return self._send(404, {"error": "未知路径"})
        payload = self._read_json()
        if payload is None:
            return self._send(400, {"error": "请求体必须是JSON"})
        required = ("claim_id", "item_id", "user_id", "slot")
        missing = [key for key in required if payload.get(key) in (None, "")]
        if missing:
            return self._send(400, {"error": "缺少字段:" + ",".join(missing)})

        claim_id = str(payload["claim_id"])
        item_id = str(payload["item_id"])
        user_id = str(payload["user_id"])
        slot = str(payload["slot"])
        claim_status, claim = _query_claim(claim_id, user_id)
        if claim_status != 200:
            return self._send(claim_status, claim)
        if claim["item_id"] != item_id:
            return self._send(400, {"error": "认领单与失物编号不匹配"})
        if claim["status"] != "已通过":
            return self._send(409, {"error": "认领尚未通过,不能预约交接"})
        if slot not in HANDOVER_SLOTS.get(item_id, []):
            return self._send(400, {"error": "交接时段不可用"})
        if claim_id in APPOINTMENTS:
            return self._send(409, {"error": "重复交接预约"})

        appointment = {
            "appointment_id": _next_appointment_id(),
            "claim_id": claim_id,
            "item_id": item_id,
            "user_id": user_id,
            "slot": slot,
            "status": "已预约",
        }
        APPOINTMENTS[claim_id] = appointment
        self._send(201, appointment)


if __name__ == "__main__":
    print(f"[handover-service] 启动于 http://localhost:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), HandoverHandler).serve_forever()
