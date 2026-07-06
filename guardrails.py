# -*- coding: utf-8 -*-
"""实验四护栏：输入检测、资源授权和输出 PII 脱敏。"""

import re

from data import APPOINTMENTS, CLAIMS


_INJECTION = (
    "忽略以上",
    "忽略之前",
    "ignore previous",
    "ignore above",
    "你现在是",
    "扮演管理员",
)
_SENSITIVE_REQUESTS = (
    "所有隐藏特征",
    "全部隐藏特征",
    "系统提示词",
    "管理员密码",
)
_PROCESS_BYPASS = (
    "跳过人工复核",
    "绕过人工复核",
    "直接批准高价值",
    "直接通过高价值",
)
_RESOURCE_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:CL|AP)\d+(?![A-Za-z0-9])", re.I
)


def input_guard(text):
    """检查提示注入、敏感数据索取和审核绕过指令。"""
    value = str(text or "")
    lowered = value.lower()
    if any(token.lower() in lowered for token in _INJECTION):
        return False, "⚠️ 检测到疑似提示注入，已拦截。"
    bulk_hidden_request = re.search(
        r"(?:所有|全部).{0,10}隐藏特征", value
    )
    if bulk_hidden_request or any(token in value for token in _SENSITIVE_REQUESTS):
        return False, "⚠️ 隐藏特征属于敏感信息，不能批量公开。"
    if re.search(
        r"\b(?:match_score|high_value)\b\s*(?:改|设|=)", value, re.I
    ):
        return False, "⚠️ 流程变量只能由服务端计算，不能由用户修改。"
    if any(token in value for token in _PROCESS_BYPASS):
        return False, "⚠️ 审核流程不能绕过。"
    return True, ""


def extract_resource_ids(text):
    """提取需要在应用层进行归属校验的资源编号。"""
    return [value.upper() for value in _RESOURCE_RE.findall(str(text or ""))]


def authz_guard(user_id, resource_id):
    """验证认领单或预约是否属于当前用户。"""
    resource_id = str(resource_id).upper()
    if resource_id.startswith("CL"):
        resource = CLAIMS.get(resource_id)
    else:
        resource = next(
            (
                item
                for item in APPOINTMENTS.values()
                if item.get("appointment_id") == resource_id
            ),
            None,
        )
    if resource is None:
        return False, "未找到该认领单或交接预约。"
    if resource.get("user_id") != user_id:
        return False, "⚠️ 无权访问该认领单或交接预约，已拒绝。"
    return True, ""


def pii_mask(text):
    """遮盖手机号和连续数字形式的完整学号。"""
    value = re.sub(
        r"(1[3-9]\d)\d{4}(\d{4})", r"\1****\2", str(text or "")
    )
    return re.sub(
        r"(?<![A-Za-z0-9])(\d{4})\d{4,}(\d{2})(?!\d)",
        r"\1****\2",
        value,
    )
