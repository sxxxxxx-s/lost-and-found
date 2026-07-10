# -*- coding: utf-8 -*-
"""认领微服务（端口 8002）。"""

import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data import CLAIMS, ITEMS


PORT = 8002
_STATUS_BY_ACTION = {
    "approve": "已通过",
    "manual-review": "待人工复核",
    "request-evidence": "待补充证据",
}


def _next_claim_id():
    return f"CL{len(CLAIMS) + 1:04d}"


class ClaimHandler(BaseHTTPRequestHandler):
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
        match = re.fullmatch(r"/claims/([^/]+)", parsed.path)
        if not match:
            return self._send(404, {"error": "未知路径"})

        claim = CLAIMS.get(unquote(match.group(1)))
        if claim is None:
            return self._send(404, {"error": "认领单不存在"})
        user_id = parse_qs(parsed.query).get("user_id", [""])[0]
        if user_id != claim["user_id"]:
            return self._send(403, {"error": "无权查询该认领单"})
        self._send(200, claim)

    def do_POST(self):
        parsed = urlparse(self.path)
        payload = self._read_json()
        if payload is None:
            return self._send(400, {"error": "请求体必须是JSON"})

        if parsed.path == "/claims":
            required = ("item_id", "user_id", "match_score")
            missing = [key for key in required if payload.get(key) in (None, "")]
            if missing:
                return self._send(400, {"error": "缺少字段:" + ",".join(missing)})
            item_id = str(payload["item_id"])
            user_id = str(payload["user_id"])
            if item_id not in ITEMS:
                return self._send(404, {"error": "失物不存在"})
            try:
                match_score = int(payload["match_score"])
            except (TypeError, ValueError):
                return self._send(400, {"error": "match_score必须是整数"})
            if not 0 <= match_score <= 100:
                return self._send(400, {"error": "match_score范围必须是0到100"})
            existing = next(
                (
                    claim
                    for claim in CLAIMS.values()
                    if claim["item_id"] == item_id and claim["user_id"] == user_id
                ),
                None,
            )
            if existing:
                existing["match_score"] = max(
                    int(existing.get("match_score", 0)), match_score
                )
                return self._send(
                    409,
                    {
                        "error": "重复认领申请",
                        "claim_id": existing["claim_id"],
                        "status": existing["status"],
                        "match_score": existing["match_score"],
                    },
                )

            claim_id = _next_claim_id()
            claim = {
                "claim_id": claim_id,
                "item_id": item_id,
                "user_id": user_id,
                "match_score": match_score,
                "status": "待核验",
            }
            CLAIMS[claim_id] = claim
            return self._send(201, claim)

        match = re.fullmatch(
            r"/claims/([^/]+)/(approve|manual-review|request-evidence)",
            parsed.path,
        )
        if not match:
            return self._send(404, {"error": "未知路径"})
        claim = CLAIMS.get(unquote(match.group(1)))
        if claim is None:
            return self._send(404, {"error": "认领单不存在"})
        claim["status"] = _STATUS_BY_ACTION[match.group(2)]
        self._send(200, claim)


if __name__ == "__main__":
    print(f"[claim-service] 启动于 http://localhost:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), ClaimHandler).serve_forever()

