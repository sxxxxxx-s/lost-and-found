# -*- coding: utf-8 -*-
"""面向课程流程子集的极简 BPMN 2.0 解析与执行引擎。"""

import operator
import re
import xml.etree.ElementTree as ET


class BpmnExecutionError(RuntimeError):
    pass


def _local_name(tag):
    return tag.split("}")[-1]


def load_bpmn(path):
    root = ET.parse(path).getroot()
    process = next(
        (element for element in root.iter() if _local_name(element.tag) == "process"),
        None,
    )
    if process is None:
        raise BpmnExecutionError("BPMN文件缺少process")

    nodes = {}
    flows = []
    starts = []
    supported = {
        "startEvent",
        "endEvent",
        "task",
        "serviceTask",
        "userTask",
        "exclusiveGateway",
    }
    for element in process:
        element_type = _local_name(element.tag)
        if element_type == "sequenceFlow":
            condition = next(
                (
                    (child.text or "").strip()
                    for child in element
                    if _local_name(child.tag) == "conditionExpression"
                ),
                None,
            )
            flows.append(
                {
                    "id": element.get("id"),
                    "src": element.get("sourceRef"),
                    "tgt": element.get("targetRef"),
                    "name": element.get("name"),
                    "cond": condition,
                }
            )
            continue
        if element_type not in supported:
            continue

        implementation = None
        for attribute, value in element.attrib.items():
            if _local_name(attribute) in {"delegateExpression", "class", "expression"}:
                implementation = value.strip().strip("${} ")
                break
        node_id = element.get("id")
        nodes[node_id] = {
            "type": element_type,
            "name": element.get("name") or node_id,
            "impl": implementation,
            "default": element.get("default"),
        }
        if element_type == "startEvent":
            starts.append(node_id)

    if len(starts) != 1:
        raise BpmnExecutionError(f"BPMN必须且只能有一个开始事件,实际为{len(starts)}个")
    for flow in flows:
        if flow["src"] not in nodes or flow["tgt"] not in nodes:
            raise BpmnExecutionError(f"顺序流{flow['id']}引用了不存在的节点")
    return nodes, flows, starts[0]


def _outgoing(flows, node_id):
    return [flow for flow in flows if flow["src"] == node_id]


_CONDITION = re.compile(
    r"^([A-Za-z_]\w*)\s*(==|!=|>=|<=|>|<)\s*(True|False|-?\d+(?:\.\d+)?)$"
)
_OPERATORS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
}


def _evaluate_condition(expression, context):
    normalized = expression.strip()
    if normalized.startswith("${") and normalized.endswith("}"):
        normalized = normalized[2:-1].strip()
    match = _CONDITION.fullmatch(normalized)
    if match is None:
        raise BpmnExecutionError(f"不支持的条件表达式:{expression}")
    variable, symbol, raw_expected = match.groups()
    if variable not in context:
        raise BpmnExecutionError(f"条件变量不存在:{variable}")
    if raw_expected == "True":
        expected = True
    elif raw_expected == "False":
        expected = False
    elif "." in raw_expected:
        expected = float(raw_expected)
    else:
        expected = int(raw_expected)
    try:
        return bool(_OPERATORS[symbol](context[variable], expected))
    except TypeError as error:
        raise BpmnExecutionError(f"条件变量类型错误:{variable}") from error


def _single_outgoing(flows, node_id):
    outgoing = _outgoing(flows, node_id)
    if len(outgoing) != 1:
        raise BpmnExecutionError(
            f"节点{node_id}应有且仅有一条出线,实际为{len(outgoing)}条"
        )
    return outgoing[0]


def run_bpmn(path, handlers, context, log=print, max_steps=50):
    nodes, flows, current = load_bpmn(path)
    log(f"▶ 开始:{nodes[current]['name']}")
    current = _single_outgoing(flows, current)["tgt"]

    for _step in range(max_steps):
        node = nodes[current]
        node_type = node["type"]
        if node_type == "endEvent":
            log(f"■ 结束:{node['name']}")
            return context

        if node_type in {"task", "serviceTask", "userTask"}:
            implementation = node.get("impl")
            handler = (
                handlers.get(implementation) if implementation else None
            ) or handlers.get(current) or handlers.get(node["name"])
            if handler is None:
                raise BpmnExecutionError(
                    f"任务{current}({node['name']})未配置处理器"
                )
            message = handler(context)
            tag = f"〔impl={implementation}〕" if implementation else ""
            log(f"任务「{node['name']}」{tag}→ {message}")
            current = _single_outgoing(flows, current)["tgt"]
            continue

        if node_type == "exclusiveGateway":
            outgoing = _outgoing(flows, current)
            if not outgoing:
                raise BpmnExecutionError(f"网关{current}没有出线")
            selected = None
            for flow in outgoing:
                if flow["cond"] and _evaluate_condition(flow["cond"], context):
                    selected = flow
                    break
            if selected is None:
                default_id = node.get("default")
                selected = next(
                    (flow for flow in outgoing if flow["id"] == default_id), None
                ) or next((flow for flow in outgoing if not flow["cond"]), None)
            if selected is None:
                raise BpmnExecutionError(f"网关{current}没有条件命中且未配置默认流")
            log(
                f"网关「{node['name']}」→ 选择分支「{selected.get('name') or '默认'}」"
            )
            current = selected["tgt"]
            continue

        raise BpmnExecutionError(f"不支持的节点类型:{node_type}")

    raise BpmnExecutionError(f"流程超过最大步数:{max_steps}")
