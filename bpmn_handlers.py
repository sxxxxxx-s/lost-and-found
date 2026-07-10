# -*- coding: utf-8 -*-
"""claim_return.bpmn 的节点处理器与微服务接线。"""

import os

from bpmn_engine import BpmnExecutionError, run_bpmn
from rag import retrieve
from tools import (
    approve_claim,
    create_appointment,
    create_claim,
    list_handover_slots,
    mark_manual_review,
    query_item,
    request_more_evidence,
    verify_evidence,
)


BPMN_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "flows", "claim_return.bpmn"
)


def _raise_on_error(result, action):
    if isinstance(result, dict) and result.get("error"):
        raise BpmnExecutionError(f"{action}失败:{result['error']}")
    return result


def h_query_item(context):
    item = query_item(context["item_id"])
    if item.get("error"):
        context["error"] = item["error"]
        context["item"] = {}
        context["item_status"] = "不存在"
        context["high_value"] = False
        return item["error"]
    context["item"] = item
    context["item_status"] = item.get("status")
    context["high_value"] = bool(item.get("high_value"))
    return (
        f"失物服务→ {item['item_id']} {item['color']}{item['category']} "
        f"(高价值={context['high_value']})"
    )


def h_verify_evidence(context):
    if context.get("error"):
        context["match_score"] = 0
        context["matched_features"] = 0
        return "跳过核验:失物不存在"
    matched = _raise_on_error(
        verify_evidence(context["item_id"], context["evidence"]), "证据核验"
    )
    context["match_score"] = int(matched["match_score"])
    context["matched_features"] = int(matched["matched_features"])
    claim = create_claim(
        context["item_id"], context["user_id"], context["match_score"]
    )
    if claim.get("error") == "重复认领申请" and claim.get("claim_id"):
        context["claim_id"] = claim["claim_id"]
        context["reused_claim"] = True
        return (
            f"失物服务核验→ 匹配度={context['match_score']};"
            f"认领服务→ 复用已有认领单 {context['claim_id']}"
        )
    claim = _raise_on_error(claim, "创建认领单")
    context["claim_id"] = claim["claim_id"]
    return (
        f"失物服务核验→ 匹配度={context['match_score']};"
        f"认领服务→ {context['claim_id']}"
    )


def h_request_evidence(context):
    if not context.get("claim_id"):
        context["result"] = context.get("error", "待补充证据")
        return context["result"]
    claim = _raise_on_error(
        request_more_evidence(context["claim_id"]), "更新认领状态"
    )
    context["result"] = claim["status"]
    return f"认领服务→ {context['result']}"


def h_manual_review(context):
    claim = _raise_on_error(
        mark_manual_review(context["claim_id"]), "转人工复核"
    )
    context["result"] = claim["status"]
    return f"认领服务→ {context['result']}"


def h_auto_approve(context):
    claim = _raise_on_error(approve_claim(context["claim_id"]), "自动审批")
    context["result"] = claim["status"]
    return f"认领服务→ {context['result']}"


def h_create_handover(context):
    slots = _raise_on_error(
        list_handover_slots(context["item_id"]), "查询交接时段"
    )
    if not slots:
        raise BpmnExecutionError("没有可用交接时段")
    appointment = _raise_on_error(
        create_appointment(
            context["claim_id"],
            context["item_id"],
            context["user_id"],
            slots[0],
        ),
        "创建交接预约",
    )
    context["appointment"] = appointment
    return f"交接服务→ {appointment['appointment_id']} {appointment['slot']}"


def h_notify(context):
    result = context.get("result", context.get("error", "处理完成"))
    if result == "待人工复核":
        policy_query = "高价值电脑人工复核"
    elif result == "待补充证据":
        policy_query = "普通物品认领证据匹配"
    else:
        policy_query = "认领通过交接时限"
    policies = retrieve(policy_query, k=1)
    context["policy"] = policies

    segments = [f"失物{context['item_id']}认领处理结果:{result}"]
    appointment = context.get("appointment")
    if appointment:
        segments.append(f"交接预约:{appointment['slot']}")
    if policies:
        policy_text = policies[0].rstrip("。.!！?？")
        segments.append(f"相关政策:{policy_text}")
    context["final"] = "。".join(segments) + "。"
    return "已生成申请人通知"


HANDLERS = {
    "h_query_item": h_query_item,
    "h_verify_evidence": h_verify_evidence,
    "h_request_evidence": h_request_evidence,
    "Task_ManualReview": h_manual_review,
    "h_auto_approve": h_auto_approve,
    "h_create_handover": h_create_handover,
    "h_notify": h_notify,
}


def run_claim(item_id, user_id, evidence):
    trace = []
    context = {"item_id": item_id, "user_id": user_id, "evidence": evidence}
    run_bpmn(
        BPMN_FILE,
        HANDLERS,
        context,
        log=lambda message: trace.append("[BPMN] " + message),
    )
    return context.get("final", "(流程未产生结果)"), trace
