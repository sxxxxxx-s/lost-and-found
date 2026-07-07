# -*- coding: utf-8 -*-
"""实验二：意图识别与 ReAct 工具调用 Agent。"""

import json

from llm import CHAT_MODEL, chat, client
from tools import FUNCS, TOOLS


INTENT_SYSTEM = """你是校园失物招领助手的意图识别入口。
只输出 JSON:{"intent":"...","entities":{...}}
intent 只能取:寻物/认领/交接/规则咨询/其他。
entities 可包含 item_id、claim_id、location、category、color、user_id。
不要输出任何额外文字。"""

PLAN_SYSTEM = """你是校园失物招领助手。面对需要多项信息的问题：
先拆分步骤，每次只调用一个最必要的只读工具；根据观察结果决定下一步；
信息齐全后综合回答。不得猜测隐藏特征，不得绕过认领审核，不得调用未提供的工具。"""


def detect_intent(text):
    message = chat(
        [
            {"role": "system", "content": INTENT_SYSTEM},
            {"role": "user", "content": text},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    try:
        result = json.loads(message.content)
    except (TypeError, json.JSONDecodeError):
        return {"intent": "其他", "entities": {}}
    if result.get("intent") not in {"寻物", "认领", "交接", "规则咨询", "其他"}:
        return {"intent": "其他", "entities": {}}
    if not isinstance(result.get("entities"), dict):
        result["entities"] = {}
    return result


def react_agent(user_text, max_steps=6, verbose=True, extra_msgs=None):
    messages = [{"role": "system", "content": PLAN_SYSTEM}]
    if extra_msgs:
        messages.extend(extra_msgs)
    messages.append({"role": "user", "content": user_text})
    for step in range(1, max_steps + 1):
        message = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            tools=TOOLS,
            temperature=0,
        ).choices[0].message
        messages.append(
            message.model_dump() if hasattr(message, "model_dump") else message
        )
        if not message.tool_calls:
            if verbose:
                print(f"  [第{step}步] 思考→信息已齐全,生成最终答复")
            return message.content

        for tool_call in message.tool_calls:
            name = tool_call.function.name
            try:
                arguments = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            function = FUNCS.get(name)
            if function is None:
                observation = {"error": f"未知或未授权工具:{name}"}
            else:
                try:
                    observation = function(**arguments)
                except (TypeError, ValueError) as error:
                    observation = {"error": f"工具参数错误:{error}"}
            if verbose:
                print(f"  [第{step}步] 行动→调用 {name}({arguments})")
                rendered = json.dumps(observation, ensure_ascii=False)
                print(f"           观察← {rendered[:140]}")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(observation, ensure_ascii=False),
                }
            )
    return "(已达最大步数,请缩小问题范围)"


def router(text):
    message = chat(
        [
            {
                "role": "system",
                "content": "判断校园失物招领诉求,只回一个词:寻物/认领/交接/规则咨询/其他",
            },
            {"role": "user", "content": text},
        ],
        temperature=0,
    )
    value = (message.content or "").strip()
    return value if value in {"寻物", "认领", "交接", "规则咨询", "其他"} else "其他"


def expert_search(text, context=None, verbose=False, user_id="u001"):
    return "【寻物专家】" + react_agent(
        text, verbose=verbose, extra_msgs=context
    )


def expert_claim(text, context=None, verbose=False, user_id="u001"):
    import re

    item_ids = re.findall(r"LF\d+", text, re.I)
    if item_ids:
        from bpmn_handlers import run_claim

        final, trace = run_claim(item_ids[0].upper(), user_id, text)
        if verbose:
            for line in trace:
                print("  " + line)
        return "【认领专家·BPMN流程】" + final
    user_context = list(context or [])
    user_context.append(
        {"role": "system", "content": f"当前用户ID:{user_id}"}
    )
    return "【认领专家】" + react_agent(
        text, verbose=verbose, extra_msgs=user_context
    )


def expert_handover(text, context=None, verbose=False, user_id="u001"):
    user_context = list(context or [])
    user_context.append(
        {"role": "system", "content": f"当前用户ID:{user_id}"}
    )
    return "【交接专家】" + react_agent(
        text, verbose=verbose, extra_msgs=user_context
    )


def expert_policy(text, context=None, verbose=False, user_id="u001"):
    from rag import retrieve

    policies = retrieve(text)
    if not policies:
        return "【规则专家·RAG】未检索到相关规则。"
    cleaned_policies = [
        str(policy).rstrip("。.!！?？") for policy in policies
    ]
    return "【规则专家·RAG】" + "；".join(cleaned_policies) + "。"


EXPERTS = {
    "寻物": expert_search,
    "认领": expert_claim,
    "交接": expert_handover,
    "规则咨询": expert_policy,
}


def orchestrate(text, user_id="u001", memory=None, verbose=True):
    context = None
    if memory is not None:
        context = memory.build("")[1:]
    intent = router(text)
    if verbose:
        print(f"  [路由] 判定意图 = {intent}")
    expert = EXPERTS.get(intent)
    if expert is None:
        answer = "您好,我可以帮您查找失物、提交认领申请、查询交接或解释认领规则。"
    else:
        answer = expert(text, context, verbose, user_id)
    return {"intent": intent, "answer": answer}


if __name__ == "__main__":
    print(detect_intent("我在图书馆丢了黑色耳机"))
