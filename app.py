# -*- coding: utf-8 -*-
"""实验四统一入口：护栏、Agent 编排、脱敏和追踪。"""

import contextlib
import io
import json
import time

from agent import orchestrate
from guardrails import authz_guard, extract_resource_ids, input_guard, pii_mask


def _guard(user_id, text):
    allowed, message = input_guard(text)
    if not allowed:
        return message, "[输入护栏] 请求被拦截"
    for resource_id in extract_resource_ids(text):
        allowed, message = authz_guard(user_id, resource_id)
        if not allowed:
            return message, f"[授权护栏] {resource_id} 访问被拒绝"
    return None, None


def serve_struct(user_id, text, memory=None):
    """处理一轮请求并返回供 Web 页面展示的结构化结果。"""
    started = time.perf_counter()
    blocked, guard_trace = _guard(user_id, text)
    if blocked:
        return {
            "reply": blocked,
            "intent": "BLOCKED",
            "trace": guard_trace,
            "latency": round(time.perf_counter() - started, 3),
        }

    output = io.StringIO()
    try:
        if memory is not None:
            memory.add("user", text)
        with contextlib.redirect_stdout(output):
            result = orchestrate(
                text, user_id=user_id, memory=memory, verbose=True
            )
        answer = pii_mask(result["answer"])
        if memory is not None:
            memory.add("assistant", answer)
        return {
            "reply": answer,
            "intent": result["intent"],
            "trace": output.getvalue().strip() or "(无工具调用)",
            "latency": round(time.perf_counter() - started, 3),
        }
    except Exception as error:
        return {
            "reply": "系统暂时无法处理该请求，请稍后重试。",
            "intent": "ERROR",
            "trace": f"[系统错误] {type(error).__name__}: {error}",
            "latency": round(time.perf_counter() - started, 3),
        }


def serve(user_id, text, memory=None, verbose=True):
    """命令行入口，返回纯文本并可打印结构化追踪。"""
    result = serve_struct(user_id, text, memory=memory)
    if verbose:
        print("TRACE " + json.dumps(result, ensure_ascii=False))
    return result["reply"]
