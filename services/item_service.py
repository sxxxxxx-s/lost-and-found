# -*- coding: utf-8 -*-
"""失物微服务（端口 8001）。

契约：
  GET  /items?keyword={keyword}&location={location}
  GET  /items/{item_id}
  POST /items/{item_id}/match
"""

import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data import ITEMS


PORT = 8001
_PRIVATE_FIELDS = {"secret_features", "secret_keywords"}


def public_item(item):
    """返回不含认领答案的公开失物信息。"""
    return {key: value for key, value in item.items() if key not in _PRIVATE_FIELDS}


def search_items(keyword="", location=""):
    keyword = unquote(keyword).strip().lower()
    location = unquote(location).strip().lower()
    results = []
    for item in ITEMS.values():
        searchable = " ".join(
            [item["category"], item["color"], item["public_description"]]
        ).lower()
        if keyword and keyword not in searchable:
            continue
        if location and location not in item["found_location"].lower():
            continue
        results.append(public_item(item))
    return results


def match_evidence(item, evidence):
    normalized = re.sub(r"\s+", "", str(evidence)).lower()
    score = 0
    matched = 0
    checks = [
        item["category"].lower() in normalized,
        item["found_location"].lower() in normalized,
        item["found_date"].lower() in normalized,
    ]
    for check in checks:
        if check:
            score += 20
            matched += 1

    hidden_match = any(
        all(str(keyword).lower() in normalized for keyword in keyword_group)
        for keyword_group in item["secret_keywords"]
    )
    if hidden_match:
        score += 40
        matched += 1

    return {
        "item_id": item["item_id"],
        "match_score": min(score, 100),
        "matched_features": matched,
        "high_value": bool(item["high_value"]),
    }


class ItemHandler(BaseHTTPRequestHandler):
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
        if parsed.path == "/items":
            query = parse_qs(parsed.query)
            items = search_items(
                query.get("keyword", [""])[0], query.get("location", [""])[0]
            )
            return self._send(200, items)

        match = re.fullmatch(r"/items/([^/]+)", parsed.path)
        if match:
            item = ITEMS.get(unquote(match.group(1)))
            if item is None:
                return self._send(404, {"error": "失物不存在"})
            return self._send(200, public_item(item))

        self._send(404, {"error": "未知路径"})

    def do_POST(self):
        parsed = urlparse(self.path)
        match = re.fullmatch(r"/items/([^/]+)/match", parsed.path)
        if not match:
            return self._send(404, {"error": "未知路径"})

        item = ITEMS.get(unquote(match.group(1)))
        if item is None:
            return self._send(404, {"error": "失物不存在"})
        payload = self._read_json()
        if payload is None or not str(payload.get("evidence", "")).strip():
            return self._send(400, {"error": "认领证据不能为空"})
        self._send(200, match_evidence(item, payload["evidence"]))


if __name__ == "__main__":
    print(f"[item-service] 启动于 http://localhost:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), ItemHandler).serve_forever()
