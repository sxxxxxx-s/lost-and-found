# Natural Language Demo Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the offline demo handle user-written Chinese natural language instead of relying on fixed shortcut scenarios.

**Architecture:** Add one shared parser inside `llm.py` and make MockLLM routing, intent JSON, and tool selection reuse it. Keep the existing microservice, BPMN, guardrail, Web API, and OpenAI-compatible interfaces unchanged.

**Tech Stack:** Python standard library `unittest`, existing OpenAI-compatible mock client, native HTML/CSS/JavaScript frontend.

---

## File Structure

- Modify `llm.py`: add `_parse_user_text()` plus small constants, then update `_route()`, `_intent()`, and `_tool_step()` to use parsed fields.
- Modify `tests/test_tools_agent.py`: add failing tests for colloquial search, claim status, handover, and policy wording.
- Modify `tests/test_experiment4.py`: add an application-level claim status test and frontend copy assertions.
- Modify `web/index.html`: change welcome copy, placeholder, and shortcut section wording so free input is the primary path.
- Modify `README.md`: document free natural language examples under the Web demo/API section.

---

### Task 1: Add Agent Natural Language Failing Tests

**Files:**
- Modify: `tests/test_tools_agent.py`

- [ ] **Step 1: Write failing intent tests**

Add `orchestrate` to the existing import:

```python
from agent import detect_intent, orchestrate, react_agent
```

Add these methods to `IntentTests`:

```python
    def test_detects_colloquial_lost_item_request(self):
        result = detect_intent("我在图书馆遗落了一个黑色蓝牙耳机")

        self.assertEqual(result["intent"], "寻物")
        self.assertEqual(result["entities"]["location"], "图书馆")
        self.assertEqual(result["entities"]["category"], "耳机")
        self.assertEqual(result["entities"]["color"], "黑色")

    def test_detects_colloquial_claim_status_query(self):
        result = detect_intent("想查 CL0001 现在处理到哪了")

        self.assertEqual(result["intent"], "认领")
        self.assertEqual(result["entities"]["claim_id"], "CL0001")

    def test_detects_colloquial_handover_request(self):
        result = detect_intent("LF2026001 可以什么时候去取")

        self.assertEqual(result["intent"], "交接")
        self.assertEqual(result["entities"]["item_id"], "LF2026001")

    def test_detects_colloquial_policy_question(self):
        result = detect_intent("电脑这种贵重物品为啥要人工审核")

        self.assertEqual(result["intent"], "规则咨询")
        self.assertEqual(result["entities"]["category"], "笔记本电脑")
```

- [ ] **Step 2: Run intent tests and verify they fail**

Run:

```powershell
python -B -m unittest tests.test_tools_agent.IntentTests -v
```

Expected: at least the new colloquial claim status, handover, and policy tests fail because current MockLLM only recognizes narrower keywords.

- [ ] **Step 3: Write failing ReAct/orchestration tests**

Add these methods to `ReactAgentTests`:

```python
    def test_react_searches_colloquial_lost_item(self):
        with running_server(ItemHandler) as item_base:
            tools.ITEM_URL = item_base
            trace = io.StringIO()
            with contextlib.redirect_stdout(trace):
                answer = react_agent(
                    "我在图书馆遗落了一个黑色蓝牙耳机",
                    verbose=True,
                )

        output = trace.getvalue()
        self.assertIn("search_items", output)
        self.assertIn("LF2026001", answer)

    def test_react_lists_slots_for_colloquial_pickup_request(self):
        with running_server(ItemHandler) as item_base, running_server(
            HandoverHandler
        ) as handover_base:
            tools.ITEM_URL = item_base
            tools.HANDOVER_URL = handover_base
            trace = io.StringIO()
            with contextlib.redirect_stdout(trace):
                answer = react_agent(
                    "LF2026001 可以什么时候去取",
                    verbose=True,
                )

        output = trace.getvalue()
        self.assertIn("query_item", output)
        self.assertIn("list_handover_slots", output)
        self.assertIn("图书馆服务台", answer)

    def test_orchestrate_answers_colloquial_policy_question(self):
        result = orchestrate("电脑这种贵重物品为啥要人工审核", verbose=False)

        self.assertEqual(result["intent"], "规则咨询")
        self.assertIn("人工复核", result["answer"])
```

- [ ] **Step 4: Run ReAct/orchestration tests and verify they fail**

Run:

```powershell
python -B -m unittest tests.test_tools_agent.ReactAgentTests -v
```

Expected: the new lost-item and pickup tests fail because `_tool_step()` does not recognize `遗落` or `什么时候去取`; the policy test fails because routing does not recognize `为啥` or `人工审核`.

- [ ] **Step 5: Commit failing tests**

```bash
git add tests/test_tools_agent.py
git commit -m "test: cover free-form lost-and-found requests"
```

---

### Task 2: Implement Shared MockLLM Natural Language Parser

**Files:**
- Modify: `llm.py`
- Test: `tests/test_tools_agent.py`

- [ ] **Step 1: Add parser helpers after `_norm()`**

Add this code after `_norm()`:

```python
_LOCATIONS = ("图书馆", "教学楼", "食堂", "操场", "宿舍")
_COLORS = ("黑色", "银色", "蓝色", "白色", "红色")
_CATEGORY_ALIASES = (
    ("airpods", "耳机"),
    ("蓝牙耳机", "耳机"),
    ("耳麦", "耳机"),
    ("耳机", "耳机"),
    ("笔记本电脑", "笔记本电脑"),
    ("笔记本", "笔记本电脑"),
    ("电脑", "笔记本电脑"),
    ("校园卡", "校园卡"),
    ("饭卡", "校园卡"),
    ("手机", "手机"),
    ("钥匙", "钥匙"),
)


def _contains(text, pattern):
    return bool(re.search(pattern, text, re.I))


def _parse_user_text(text):
    raw = str(text or "")
    lowered = raw.lower()
    item_ids = re.findall(r"LF\d+", raw, re.I)
    claim_ids = re.findall(r"CL\d+", raw, re.I)
    user_ids = re.findall(r"u\d+", raw, re.I)
    location = next((value for value in _LOCATIONS if value in raw), None)
    color = next((value for value in _COLORS if value in raw), None)
    category = next(
        (
            normalized
            for keyword, normalized in _CATEGORY_ALIASES
            if keyword.lower() in lowered
        ),
        None,
    )

    item_id = item_ids[0].upper() if item_ids else None
    claim_id = claim_ids[0].upper() if claim_ids else None
    wants_handover = _contains(
        raw,
        r"交接|预约|时段|领取|取回|去取|拿回|领回|什么时候|何时|哪里领|哪儿领|在哪里领|哪里取|在哪取",
    )
    wants_status = bool(claim_id) and _contains(
        raw,
        r"进度|状态|处理到哪|审核|结果|查|查询|看看|出来了吗|怎么样|到哪",
    )
    wants_policy = _contains(
        raw,
        r"规则|规定|政策|流程|为什么|为啥|为何|原因|人工复核|人工审核|高价值|贵重|隐私|泄露",
    )
    wants_claim = _contains(raw, r"认领|证据|证明|失主|我的|申请") or wants_status
    wants_search = _contains(
        raw,
        r"丢|遗失|遗落|落下|掉了|寻找|找|失物|捡到|捡了|拾到|有没有|看到",
    ) or bool(category and location and not item_id and not claim_id)

    if claim_id and (wants_status or wants_claim):
        intent = "认领"
    elif item_id and wants_handover:
        intent = "交接"
    elif wants_policy and not item_id and not claim_id:
        intent = "规则咨询"
    elif wants_claim:
        intent = "认领"
    elif wants_handover and item_id:
        intent = "交接"
    elif wants_search:
        intent = "寻物"
    elif wants_policy:
        intent = "规则咨询"
    else:
        intent = "其他"

    return {
        "intent": intent,
        "item_id": item_id,
        "claim_id": claim_id,
        "user_id": user_ids[0].lower() if user_ids else None,
        "location": location,
        "color": color,
        "category": category,
        "wants_handover": wants_handover,
        "wants_status": wants_status,
        "wants_policy": wants_policy,
        "wants_claim": wants_claim,
        "wants_search": wants_search,
    }
```

- [ ] **Step 2: Replace `_route()` and `_intent()`**

Replace the existing `_route()` method with:

```python
    def _route(self, t):
        return _parse_user_text(t)["intent"]
```

Replace the existing `_intent()` method with:

```python
    def _intent(self, t):
        parsed = _parse_user_text(t)
        ent = {}
        for key in ("item_id", "claim_id", "user_id", "location", "color", "category"):
            if parsed.get(key):
                ent[key] = parsed[key]
        return json.dumps(
            {"intent": parsed["intent"], "entities": ent},
            ensure_ascii=False,
        )
```

- [ ] **Step 3: Update `_tool_step()` to use parsed fields**

At the start of `_tool_step()` after `observations = self._observations(msgs)`, add:

```python
        parsed = _parse_user_text(user_txt)
```

Replace the current `item_ids`, `claim_ids`, `item_id`, `wants_handover`, `wants_search`, and `wants_policy` setup with:

```python
        claim_id = parsed["claim_id"]
        item_id = parsed["item_id"]
        if item_id is None:
            for observation in observations:
                if isinstance(observation, dict) and observation.get("item_id"):
                    item_id = observation["item_id"]
                    break
                if (
                    isinstance(observation, list)
                    and observation
                    and isinstance(observation[0], dict)
                ):
                    item_id = observation[0].get("item_id")
                    if item_id:
                        break

        wants_handover = parsed["wants_handover"]
        wants_search = parsed["wants_search"] or parsed["intent"] == "寻物"
        wants_policy = parsed["wants_policy"] or parsed["intent"] == "规则咨询"
```

Replace the `search_items` argument block with:

```python
            return _Resp(_Msg(tool_calls=[_ToolCall(
                "search_items",
                {
                    "keyword": parsed["category"] or "",
                    "location": parsed["location"] or "",
                },
            )]))
```

Replace the `query_claim` block with:

```python
        if claim_id and "query_claim" in avail and "query_claim" not in called:
            context_text = " ".join(
                str(message.get("content", "") or "") for message in msgs
            )
            users = re.findall(r"u\d+", context_text, re.I)
            user_id = parsed["user_id"] or (users[-1].lower() if users else None)
            if user_id:
                return _Resp(_Msg(tool_calls=[_ToolCall(
                    "query_claim",
                    {"claim_id": claim_id, "user_id": user_id},
                )]))
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
python -B -m unittest tests.test_tools_agent.IntentTests tests.test_tools_agent.ReactAgentTests -v
```

Expected: all intent and ReAct tests pass.

- [ ] **Step 5: Commit parser implementation**

```bash
git add llm.py
git commit -m "feat: parse free-form demo language in mock llm"
```

---

### Task 3: Add Application-Level Claim Query Coverage

**Files:**
- Modify: `tests/test_experiment4.py`
- Test: `tests/test_experiment4.py`

- [ ] **Step 1: Write failing application test**

Add this method to `ApplicationTests` after `test_authorized_user_id_reaches_claim_query_tool`:

```python
    def test_colloquial_claim_status_query_reaches_claim_tool(self):
        CLAIMS["CL0001"] = {
            "claim_id": "CL0001",
            "item_id": "LF2026001",
            "user_id": "u001",
            "match_score": 100,
            "status": "已通过",
        }
        servers = start_business_services((0, 0, 0))
        try:
            result = serve_struct("u001", "想查 CL0001 现在处理到哪了")
        finally:
            stop_servers(servers)

        self.assertEqual(result["intent"], "认领")
        self.assertIn("认领单CL0001当前状态:已通过", result["reply"])
        self.assertIn("query_claim", result["trace"])
```

- [ ] **Step 2: Run the new test and verify it passes after Task 2**

Run:

```powershell
python -B -m unittest tests.test_experiment4.ApplicationTests.test_colloquial_claim_status_query_reaches_claim_tool -v
```

Expected: PASS. If it fails with intent `其他`, re-check `_parse_user_text()` claim status patterns and `_route()`.

- [ ] **Step 3: Commit application coverage**

```bash
git add tests/test_experiment4.py
git commit -m "test: cover colloquial claim status query"
```

---

### Task 4: Update Frontend Free-Input Experience

**Files:**
- Modify: `tests/test_experiment4.py`
- Modify: `web/index.html`

- [ ] **Step 1: Add failing frontend copy assertions**

In `FrontendTests.test_page_reuses_reference_layout_with_personalized_safe_controls`, add these markers to the tuple:

```python
            "可以直接输入",
            "例如：我昨天在图书馆二楼丢了黑色蓝牙耳机",
            "示例问题",
```

- [ ] **Step 2: Run frontend test and verify it fails**

Run:

```powershell
python -B -m unittest tests.test_experiment4.FrontendTests.test_page_reuses_reference_layout_with_personalized_safe_controls -v
```

Expected: FAIL because the current page does not contain the new free-input copy.

- [ ] **Step 3: Edit the shortcut section and input placeholder**

In `web/index.html`, replace:

```html
    <div class="quick">
```

with:

```html
    <div class="quick" aria-label="示例问题">
      <span class="quick-title">示例问题</span>
```

Add this CSS rule after `.quick { ... }`:

```css
  .quick-title {
    align-self: center; font-size: 12px; color: #5a6b82; margin-right: 2px;
  }
```

Replace the input element:

```html
      <input id="inp" aria-label="消息" placeholder="输入问题，回车发送…">
```

with:

```html
      <input id="inp" aria-label="消息" placeholder="例如：我昨天在图书馆二楼丢了黑色蓝牙耳机">
```

Replace the initial assistant message:

```javascript
addMsg('你好！我可以帮你搜索失物、提交认领、查询交接和解释认领规则。', 'bot', '助理');
```

with:

```javascript
addMsg('你好！你可以直接输入遗失物描述、失物编号、认领单编号或规则问题，我会帮你搜索失物、提交认领、查询交接和解释认领规则。', 'bot', '助理');
```

- [ ] **Step 4: Run frontend tests and verify they pass**

Run:

```powershell
python -B -m unittest tests.test_experiment4.FrontendTests -v
```

Expected: all frontend tests pass and `innerHTML` remains absent.

- [ ] **Step 5: Commit frontend update**

```bash
git add tests/test_experiment4.py web/index.html
git commit -m "feat: emphasize free-form web input"
```

---

### Task 5: Document Free Natural Language Examples

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README Web demo section**

In `README.md`, under section `## 29. Web 演示场景`, add this paragraph before the scenario table:

````markdown
页面支持直接输入自定义自然语言，不需要只点击快捷按钮。离线 MockLLM 会对校园失物招领的核心表达做确定性解析，例如：

```text
我在图书馆遗落了一个黑色蓝牙耳机
想查 CL0001 现在处理到哪了
LF2026001 可以什么时候去取
电脑这种贵重物品为啥要人工审核
```

快捷按钮保留为课程演示样例；实际交互建议直接在输入框描述诉求。
````

- [ ] **Step 2: Run documentation-adjacent checks**

Run:

```powershell
git diff --check README.md
```

Expected: no trailing whitespace or conflict markers.

- [ ] **Step 3: Commit README update**

```bash
git add README.md
git commit -m "docs: describe free-form natural language input"
```

---

### Task 6: Full Verification

**Files:**
- Verify all changed files

- [ ] **Step 1: Run complete unit test suite**

Run:

```powershell
python -B -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 2: Run compile check**

Run:

```powershell
python -B -m compileall -q .
```

Expected: command exits with code 0.

- [ ] **Step 3: Run whitespace diff check**

Run:

```powershell
git diff --check
```

Expected: no output.

- [ ] **Step 4: Inspect final diff**

Run:

```powershell
git status --short
git diff --stat HEAD~5..HEAD
```

Expected: working tree is clean after the planned commits, and the diff contains only `llm.py`, `tests/test_tools_agent.py`, `tests/test_experiment4.py`, `web/index.html`, and `README.md`.
