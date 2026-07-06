# -*- coding: utf-8 -*-
"""Agent 工具层：把三个 REST 微服务包装成 Python 函数和工具契约。"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from rag import retrieve

ITEM_URL = os.getenv("ITEM_URL", "http://localhost:8001")
CLAIM_URL = os.getenv("CLAIM_URL", "http://localhost:8002")
HANDOVER_URL = os.getenv("HANDOVER_URL", "http://localhost:8003")


def _request_json(method, url, service_name, params=None, payload=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            return json.loads(error.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {"error": f"{service_name}请求失败:HTTP {error.code}"}
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return {"error": f"{service_name}不可用:{error}"}


def search_items(keyword="", location=""):
    return _request_json(
        "GET",
        f"{ITEM_URL}/items",
        "失物服务",
        params={"keyword": keyword, "location": location},
    )


def query_item(item_id):
    item_id = urllib.parse.quote(str(item_id), safe="")
    return _request_json("GET", f"{ITEM_URL}/items/{item_id}", "失物服务")


def verify_evidence(item_id, evidence):
    item_id = urllib.parse.quote(str(item_id), safe="")
    return _request_json(
        "POST",
        f"{ITEM_URL}/items/{item_id}/match",
        "失物服务",
        payload={"evidence": evidence},
    )


def create_claim(item_id, user_id, match_score):
    return _request_json(
        "POST",
        f"{CLAIM_URL}/claims",
        "认领服务",
        payload={
            "item_id": item_id,
            "user_id": user_id,
            "match_score": match_score,
        },
    )


def query_claim(claim_id, user_id):
    claim_id = urllib.parse.quote(str(claim_id), safe="")
    return _request_json(
        "GET",
        f"{CLAIM_URL}/claims/{claim_id}",
        "认领服务",
        params={"user_id": user_id},
    )


def _set_claim_status(claim_id, action):
    claim_id = urllib.parse.quote(str(claim_id), safe="")
    return _request_json(
        "POST", f"{CLAIM_URL}/claims/{claim_id}/{action}", "认领服务", payload={}
    )


def approve_claim(claim_id):
    return _set_claim_status(claim_id, "approve")


def mark_manual_review(claim_id):
    return _set_claim_status(claim_id, "manual-review")


def request_more_evidence(claim_id):
    return _set_claim_status(claim_id, "request-evidence")


def list_handover_slots(item_id):
    return _request_json(
        "GET",
        f"{HANDOVER_URL}/slots",
        "交接服务",
        params={"item_id": item_id},
    )


def create_appointment(claim_id, item_id, user_id, slot):
    return _request_json(
        "POST",
        f"{HANDOVER_URL}/appointments",
        "交接服务",
        payload={
            "claim_id": claim_id,
            "item_id": item_id,
            "user_id": user_id,
            "slot": slot,
        },
    )


def query_appointment(claim_id, user_id):
    claim_id = urllib.parse.quote(str(claim_id), safe="")
    return _request_json(
        "GET",
        f"{HANDOVER_URL}/appointments/{claim_id}",
        "交接服务",
        params={"user_id": user_id},
    )


def search_policy(q, k=None):
    return retrieve(q, k=k)


FUNCS = {
    "search_items": search_items,
    "query_item": query_item,
    "verify_evidence": verify_evidence,
    "create_claim": create_claim,
    "query_claim": query_claim,
    "approve_claim": approve_claim,
    "mark_manual_review": mark_manual_review,
    "request_more_evidence": request_more_evidence,
    "list_handover_slots": list_handover_slots,
    "create_appointment": create_appointment,
    "query_appointment": query_appointment,
    "search_policy": search_policy,
}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_items",
            "description": "按物品关键词和发现地点搜索公开失物信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "物品类别、颜色或描述关键词"},
                    "location": {"type": "string", "description": "物品可能遗失或被发现的地点"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_item",
            "description": "根据失物编号查询不含隐藏特征的公开详情",
            "parameters": {
                "type": "object",
                "properties": {"item_id": {"type": "string", "description": "格式如LF2026001"}},
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_claim",
            "description": "根据认领单编号查询当前用户自己的认领进度",
            "parameters": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string", "description": "格式如CL0001"},
                    "user_id": {"type": "string", "description": "当前用户编号"},
                },
                "required": ["claim_id", "user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_handover_slots",
            "description": "根据失物编号查询可选的线下交接时段和地点",
            "parameters": {
                "type": "object",
                "properties": {"item_id": {"type": "string", "description": "格式如LF2026001"}},
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_policy",
            "description": "检索认领审核、隐私保护和交接规则",
            "parameters": {
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "需要查询的规则问题"}
                },
                "required": ["q"],
            },
        },
    },
]
