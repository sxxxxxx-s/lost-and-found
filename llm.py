# -*- coding: utf-8 -*-
"""
统一的大模型客户端。

设计要点(重要):
- 对外暴露与 OpenAI 完全一致的接口:client.chat.completions.create(model, messages, tools, ...)
  返回对象 .choices[0].message,message 有 .content 与 .tool_calls。
- 若环境变量里配置了 OPENAI_API_KEY,则使用真实的 OpenAI 兼容大模型(openai SDK)。
- 否则回退到 MockLLM —— 一个确定性的"教学桩",用规则模拟大模型的"意图判断/工具选择/
  生成回复",让整套系统在【无密钥、无网络】的情况下也能完整跑通、输出可复现。
  学生在自己电脑上 `export OPENAI_API_KEY=...` 后,同一套代码即调用真实模型,无需改动。

这正是工程上的"接口隔离":上层 Agent/编排逻辑只依赖接口,不关心背后是真模型还是桩。
"""
import os, re, json, uuid

def _load_dotenv():
    """无依赖加载同目录下的 .env(每行 KEY=VALUE),已存在的环境变量不覆盖。
    这就是配置大模型 API Key 的地方:把 .env.example 复制成 .env 并填入 key。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            if v:                   # 空值不设置,避免空字符串误判为"已配置"
                os.environ.setdefault(k.strip(), v)

_load_dotenv()

CHAT_MODEL = os.getenv("CHAT_MODEL", "mock-llm")

# ----------------------------------------------------------------------
# 模拟 OpenAI 返回对象的最小数据结构
# ----------------------------------------------------------------------
class _Fn:
    def __init__(self, name, arguments): self.name = name; self.arguments = arguments
class _ToolCall:
    def __init__(self, name, args):
        self.id = "call_" + uuid.uuid4().hex[:8]; self.type = "function"
        self.function = _Fn(name, json.dumps(args, ensure_ascii=False))
class _Msg:
    def __init__(self, content=None, tool_calls=None, role="assistant"):
        self.content = content; self.tool_calls = tool_calls or None; self.role = role
    def model_dump(self):
        d = {"role": self.role, "content": self.content or ""}
        if self.tool_calls:
            d["tool_calls"] = [{"id": tc.id, "type": "function",
                                "function": {"name": tc.function.name,
                                             "arguments": tc.function.arguments}}
                               for tc in self.tool_calls]
        return d
class _Choice:
    def __init__(self, m): self.message = m
class _Resp:
    def __init__(self, m): self.choices = [_Choice(m)]


def _norm(messages):
    """把 messages 里可能混入的对象统一成 dict,便于桩解析。"""
    out = []
    for m in messages:
        if isinstance(m, dict): out.append(m)
        elif hasattr(m, "model_dump"): out.append(m.model_dump())
        else: out.append({"role": getattr(m, "role", "assistant"),
                          "content": getattr(m, "content", "")})
    return out


# ----------------------------------------------------------------------
# MockLLM:确定性教学桩
# ----------------------------------------------------------------------
class _MockCompletions:
    def create(self, model=None, messages=None, tools=None,
               temperature=0, response_format=None, **kw):
        msgs = _norm(messages)
        sys_txt = " ".join(m.get("content", "") or "" for m in msgs if m.get("role") == "system")
        user_txt = " ".join(m.get("content", "") or "" for m in msgs if m.get("role") == "user")

        # 1) 路由:system 要求"只回一个词"
        if "只回一个词" in sys_txt or "只回复一个词" in sys_txt:
            return _Resp(_Msg(content=self._route(user_txt)))

        # 2) 摘要压缩:system/user 要求"压缩成要点"
        if "压缩成要点" in sys_txt + user_txt or "压缩成" in user_txt:
            return _Resp(_Msg(content=self._summarize(user_txt)))

        # 3) 评测打分:judge,要求输出 {"pass": ...}
        if response_format and '"pass"' in (sys_txt + user_txt):
            return _Resp(_Msg(content=self._judge(user_txt)))

        # 4) 意图识别:要求输出 {"intent": ...}
        if response_format and ("意图" in sys_txt or '"intent"' in sys_txt):
            return _Resp(_Msg(content=self._intent(user_txt)))

        # 5) 工具调用 / ReAct:提供了 tools。决策以"当前(最后一条)用户消息"为准,
        #    历史仅作背景,避免把上一轮诉求误带入本轮。
        if tools:
            last_user = next((m.get("content", "") for m in reversed(msgs)
                              if m.get("role") == "user"), user_txt)
            return self._tool_step(msgs, tools, last_user)

        # 6) 兜底:普通生成
        return _Resp(_Msg(content=self._final_answer(msgs, user_txt)))

    # ---- 子能力 ----
    def _route(self, t):
        if re.search(r"交接|预约|时段|领取|取回", t): return "交接"
        if re.search(r"认领|证据|证明|失主", t): return "认领"
        if re.search(r"丢|遗失|找|失物|捡到", t): return "寻物"
        if re.search(r"规则|规定|政策|流程", t): return "规则咨询"
        return "其他"

    def _summarize(self, t):
        item_ids = "、".join(sorted(set(re.findall(r"LF\d+", t, re.I))))
        claim_ids = "、".join(sorted(set(re.findall(r"CL\d+", t, re.I))))
        keywords = [
            key
            for key in ["寻物", "认领", "证据", "人工复核", "交接", "预约"]
            if key in t
        ]
        parts = []
        if item_ids: parts.append(f"涉及失物 {item_ids.upper()}")
        if claim_ids: parts.append(f"涉及认领单 {claim_ids.upper()}")
        if keywords: parts.append("诉求关键词:" + "/".join(keywords))
        return ";".join(parts) if parts else "用户进行了若干轮咨询。"

    def _judge(self, t):
        # 从 "要点:[...]" 与 "回答:..." 中判断要点是否被覆盖
        m_must = re.search(r"要点[:：]\s*(\[[^\]]*\])", t)
        m_ans = re.search(r"回答[:：]\s*(.+)", t, re.S)
        must, ans = [], ""
        if m_must:
            try: must = json.loads(m_must.group(1).replace("'", '"'))
            except Exception: must = re.findall(r"[\"']([^\"']+)[\"']", m_must.group(1))
        if m_ans: ans = m_ans.group(1)
        ok = all(str(x) in ans for x in must) if must else True
        return json.dumps({"pass": bool(ok)}, ensure_ascii=False)

    def _intent(self, t):
        if re.search(r"交接|预约|时段|领取|取回", t): intent = "交接"
        elif re.search(r"认领|证据|证明|失主", t): intent = "认领"
        elif re.search(r"丢|遗失|找|失物|捡到", t): intent = "寻物"
        elif re.search(r"规则|规定|政策|流程", t): intent = "规则咨询"
        else: intent = "其他"
        ent = {}
        item_ids = re.findall(r"LF\d+", t, re.I)
        claim_ids = re.findall(r"CL\d+", t, re.I)
        user_ids = re.findall(r"u\d+", t, re.I)
        if item_ids: ent["item_id"] = item_ids[0].upper()
        if claim_ids: ent["claim_id"] = claim_ids[0].upper()
        if user_ids: ent["user_id"] = user_ids[0].lower()
        for location in ["图书馆", "教学楼", "食堂", "操场", "宿舍"]:
            if location in t:
                ent["location"] = location
                break
        for color in ["黑色", "银色", "蓝色", "白色", "红色"]:
            if color in t:
                ent["color"] = color
                break
        categories = [
            ("耳机", "耳机"),
            ("电脑", "笔记本电脑"),
            ("校园卡", "校园卡"),
            ("手机", "手机"),
            ("钥匙", "钥匙"),
        ]
        for keyword, category in categories:
            if keyword in t:
                ent["category"] = category
                break
        return json.dumps({"intent": intent, "entities": ent}, ensure_ascii=False)

    def _called_tools(self, msgs):
        names = []
        for m in msgs:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                names += [tc["function"]["name"] for tc in m["tool_calls"]]
        return names

    def _observations(self, msgs):
        obs = []
        for m in msgs:
            if m.get("role") == "tool":
                try: obs.append(json.loads(m["content"]))
                except Exception: obs.append(m["content"])
        return obs

    def _tool_step(self, msgs, tools, user_txt):
        """ReAct 决策:已有观察则决定下一步,信息齐全则给最终答案。"""
        avail = {t["function"]["name"] for t in tools}
        called = self._called_tools(msgs)
        observations = self._observations(msgs)
        item_ids = re.findall(r"LF\d+", user_txt, re.I)
        claim_ids = re.findall(r"CL\d+", user_txt, re.I)
        item_id = item_ids[0].upper() if item_ids else None
        if item_id is None:
            for observation in observations:
                if isinstance(observation, dict) and observation.get("item_id"):
                    item_id = observation["item_id"]
                    break
                if isinstance(observation, list) and observation and isinstance(observation[0], dict):
                    item_id = observation[0].get("item_id")
                    if item_id:
                        break

        wants_handover = bool(re.search(r"交接|预约|时段|哪里领|取回", user_txt))
        wants_search = bool(re.search(r"丢|遗失|找|失物|捡到", user_txt))
        wants_policy = bool(re.search(r"规则|规定|政策|为什么|隐私|人工复核", user_txt))

        if item_id and "query_item" in avail and "query_item" not in called:
            return _Resp(_Msg(tool_calls=[_ToolCall("query_item", {"item_id": item_id})]))

        if not item_id and wants_search and "search_items" in avail \
           and "search_items" not in called:
            keyword = next(
                (value for value in ["耳机", "电脑", "校园卡", "手机", "钥匙"] if value in user_txt),
                "",
            )
            location = next(
                (value for value in ["图书馆", "教学楼", "食堂", "操场", "宿舍"] if value in user_txt),
                "",
            )
            return _Resp(_Msg(tool_calls=[_ToolCall(
                "search_items", {"keyword": keyword, "location": location}
            )]))

        if item_id and wants_handover and "list_handover_slots" in avail \
           and "list_handover_slots" not in called:
            return _Resp(_Msg(tool_calls=[_ToolCall(
                "list_handover_slots", {"item_id": item_id}
            )]))

        if claim_ids and "query_claim" in avail and "query_claim" not in called:
            context_text = " ".join(
                str(message.get("content", "") or "") for message in msgs
            )
            users = re.findall(r"u\d+", context_text, re.I)
            if users:
                return _Resp(_Msg(tool_calls=[_ToolCall(
                    "query_claim",
                    {"claim_id": claim_ids[0].upper(), "user_id": users[-1].lower()},
                )]))
        if wants_policy and "search_policy" in avail and "search_policy" not in called:
            return _Resp(_Msg(tool_calls=[_ToolCall("search_policy", {"q": user_txt})]))
        # 信息齐全 → 终态回复
        return _Resp(_Msg(content=self._final_answer(msgs, user_txt)))

    def _final_answer(self, msgs, user_txt):
        obs = self._observations(msgs)
        item = next(
            (value for value in obs if isinstance(value, dict) and "item_id" in value and "category" in value),
            None,
        )
        claim = next(
            (value for value in obs if isinstance(value, dict) and "claim_id" in value),
            None,
        )
        search_results = next(
            (
                value
                for value in obs
                if isinstance(value, list) and (not value or isinstance(value[0], dict))
            ),
            None,
        )
        called = self._called_tools(msgs)
        policy_results = next(
            (
                value
                for value in obs
                if "search_policy" in called
                and isinstance(value, list)
                and (not value or isinstance(value[0], str))
            ),
            None,
        )
        slots = next(
            (
                value
                for value in obs
                if "list_handover_slots" in called
                and isinstance(value, list)
                and value
                and isinstance(value[0], str)
            ),
            None,
        )
        parts = []
        if search_results is not None:
            if search_results:
                summary = "；".join(
                    f"{value['item_id']} {value['color']}{value['category']}({value['found_location']})"
                    for value in search_results
                )
                parts.append("找到以下候选失物:" + summary + "。")
            else:
                parts.append("暂未找到符合描述的失物。")
        if item and "error" not in item:
            parts.append(
                f"失物{item['item_id']}是{item['color']}{item['category']},"
                f"于{item['found_location']}发现,当前状态:{item['status']}。"
            )
        if claim and "error" not in claim:
            parts.append(f"认领单{claim['claim_id']}当前状态:{claim['status']}。")
        if slots:
            parts.append("可选交接时段:" + "；".join(slots) + "。")
        if policy_results:
            cleaned_policies = [
                str(policy).rstrip("。.!！?？") for policy in policy_results
            ]
            parts.append("相关规则:" + "；".join(cleaned_policies) + "。")
        if any(isinstance(o, dict) and o.get("error") for o in obs):
            parts.append("抱歉,未能查询到对应信息,请核对后再试。")
        if not parts:
            parts.append("您好,我可以帮您查找失物、提交认领申请或安排交接,请问需要什么?")
        return "".join(parts)


class _MockChat:
    def __init__(self): self.completions = _MockCompletions()
class MockLLM:
    def __init__(self): self.chat = _MockChat()


# ----------------------------------------------------------------------
# 对外:client + chat() 便捷函数(真实/桩 自动切换)
# ----------------------------------------------------------------------
if os.getenv("OPENAI_API_KEY"):
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"),
                    base_url=os.getenv("OPENAI_BASE_URL"))
    BACKEND = "real:" + CHAT_MODEL
else:
    client = MockLLM()
    BACKEND = "mock-llm(教学桩,离线可复现)"


def chat(messages, **kw):
    """无工具的便捷调用,返回 message 对象。"""
    return client.chat.completions.create(model=CHAT_MODEL, messages=messages, **kw).choices[0].message


if __name__ == "__main__":
    print("当前后端:", BACKEND)
    print(chat([{"role": "user", "content": "你好"}]).content)
