# Experiment Two Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build three independently runnable lost-and-found microservices, expose them as Agent tools, and implement personalized intent detection plus a two-step ReAct Agent.

**Architecture:** Keep business data in one in-memory `data.py` module, expose three REST boundaries through Python `http.server`, and wrap those boundaries with `requests` functions in `tools.py`. `agent.py` depends only on LLM-compatible tool schemas and tool functions; the offline `MockLLM` is personalized so every experiment-two behavior is reproducible without a key or network.

**Tech Stack:** Python 3.8+ standard library, `http.server`, `urllib.request`, `unittest`, OpenAI-compatible tool schema.

---

## File Structure

- Create `lost-and-found/data.py`: seeded items, mutable claims, handover slots, appointments, and policy text.
- Create `lost-and-found/services/item_service.py`: item search, public detail, and server-side evidence matching on port 8001.
- Create `lost-and-found/services/claim_service.py`: claim creation, owner-authorized query, and status transitions on port 8002.
- Create `lost-and-found/services/handover_service.py`: slot query and owner-authorized appointment operations on port 8003.
- Create `lost-and-found/tools.py`: HTTP wrappers, function registry, and safe Agent tool schemas.
- Create `lost-and-found/agent.py`: structured intent detection and ReAct loop.
- Modify `lost-and-found/llm.py`: replace the remaining e-commerce mock intent, tool planning, and result generation rules.
- Create `lost-and-found/tests/test_services.py`: real HTTP contract tests using ephemeral local ports.
- Create `lost-and-found/tests/test_tools_agent.py`: tool wrapper, intent, and two-step ReAct integration tests.
- Modify `lost-and-found/README.md`: add experiment-two startup, curl, Agent, and acceptance instructions.

### Task 1: Item data and item microservice

**Files:**
- Create: `lost-and-found/data.py`
- Create: `lost-and-found/services/item_service.py`
- Create: `lost-and-found/tests/test_services.py`

- [ ] **Step 1: Write failing HTTP contract tests**

Use `HTTPServer(("127.0.0.1", 0), ItemHandler)` in a background thread and assert:

```python
status, item = request_json("GET", f"{base}/items/LF2026001")
self.assertEqual(status, 200)
self.assertNotIn("secret_features", item)

status, missing = request_json("GET", f"{base}/items/UNKNOWN")
self.assertEqual(status, 404)

status, result = request_json(
    "POST",
    f"{base}/items/LF2026001/match",
    {"evidence": "蓝牙耳机 图书馆 2026-06-28 盒内刻有ZL"},
)
self.assertEqual(result["match_score"], 100)
```

Also assert search by `keyword=耳机&location=图书馆` returns exactly `LF2026001` and never exposes hidden fields.

- [ ] **Step 2: Run the item tests and verify RED**

```powershell
python -B -m unittest tests.test_services.ItemServiceTests -v
```

Expected: import failure because `data.py` and `services/item_service.py` do not exist.

- [ ] **Step 3: Implement seeded data and item endpoints**

Seed `LF2026001`, `LF2026002`, and `LF2026003` according to the approved design. Implement:

```text
GET  /items?keyword={keyword}&location={location}
GET  /items/{item_id}
POST /items/{item_id}/match
```

The public serializer must remove `secret_features` and `secret_keywords`. Matching awards 20 points each for category, location, date, and 40 points when any configured hidden keyword group matches; maximum score is 100.

- [ ] **Step 4: Run item tests and verify GREEN**

```powershell
python -B -m unittest tests.test_services.ItemServiceTests -v
```

Expected: all item service tests pass.

- [ ] **Step 5: Commit the item service slice**

```powershell
git add lost-and-found/data.py lost-and-found/services/item_service.py lost-and-found/tests/test_services.py
git commit -m "feat: add lost item microservice"
```

### Task 2: Claim and handover microservices

**Files:**
- Modify: `lost-and-found/data.py`
- Create: `lost-and-found/services/claim_service.py`
- Create: `lost-and-found/services/handover_service.py`
- Modify: `lost-and-found/tests/test_services.py`

- [ ] **Step 1: Write failing claim and handover tests**

Assert the following real HTTP behavior:

```python
status, claim = request_json(
    "POST", f"{claim_base}/claims",
    {"item_id": "LF2026001", "user_id": "u001", "match_score": 100},
)
self.assertEqual(status, 201)

status, _ = request_json(
    "GET", f"{claim_base}/claims/{claim['claim_id']}?user_id=u002"
)
self.assertEqual(status, 403)

status, slots = request_json("GET", f"{handover_base}/slots?item_id=LF2026001")
self.assertEqual(status, 200)
self.assertGreater(len(slots), 0)
```

Also cover duplicate claims as 409, unknown claims as 404, status endpoints, appointment creation as 201, duplicate appointment as 409, and cross-user appointment query as 403.

- [ ] **Step 2: Run tests and verify RED**

```powershell
python -B -m unittest tests.test_services.ClaimServiceTests tests.test_services.HandoverServiceTests -v
```

Expected: import failures because both service modules are absent.

- [ ] **Step 3: Implement claim service**

Implement:

```text
POST /claims
GET  /claims/{claim_id}?user_id={user_id}
POST /claims/{claim_id}/approve
POST /claims/{claim_id}/manual-review
POST /claims/{claim_id}/request-evidence
```

Generate IDs as `CL0001`, enforce one active claim per item and user, and return 400/403/404/409 JSON errors as appropriate.

- [ ] **Step 4: Implement handover service**

Implement:

```text
GET  /slots?item_id={item_id}
POST /appointments
GET  /appointments/{claim_id}?user_id={user_id}
```

Generate IDs as `AP0001`, verify the requested slot exists, and enforce one appointment per claim.

- [ ] **Step 5: Run all service tests and verify GREEN**

```powershell
python -B -m unittest tests.test_services -v
```

Expected: item, claim, and handover HTTP contract tests all pass.

- [ ] **Step 6: Commit the service slice**

```powershell
git add lost-and-found/data.py lost-and-found/services/claim_service.py lost-and-found/services/handover_service.py lost-and-found/tests/test_services.py
git commit -m "feat: add claim and handover microservices"
```

### Task 3: Agent tool wrappers and schemas

**Files:**
- Create: `lost-and-found/tools.py`
- Create: `lost-and-found/tests/test_tools_agent.py`

- [ ] **Step 1: Write failing tool integration tests**

Start all three handlers on ephemeral ports, point `tools.ITEM_URL`, `tools.CLAIM_URL`, and `tools.HANDOVER_URL` to them, then assert:

```python
self.assertEqual(tools.query_item("LF2026001")["item_id"], "LF2026001")
self.assertEqual(len(tools.search_items("耳机", "图书馆")), 1)
self.assertEqual(tools.verify_evidence("LF2026001", evidence)["match_score"], 100)
self.assertIn("claim_id", tools.create_claim("LF2026001", "u001", 100))
self.assertGreater(len(tools.list_handover_slots("LF2026001")), 0)
```

Verify `TOOLS` exposes only `search_items`, `query_item`, `query_claim`, and `list_handover_slots`; state-changing functions remain available in `FUNCS` for BPMN handlers but are not model-callable.

- [ ] **Step 2: Run tests and verify RED**

```powershell
python -B -m unittest tests.test_tools_agent.ToolIntegrationTests -v
```

Expected: import failure because `tools.py` does not exist.

- [ ] **Step 3: Implement HTTP wrappers and tool contracts**

Use `urllib.request` with a 3-second timeout. Every wrapper must catch network and timeout errors and return `{"error": "...服务不可用: ..."}`. Define all functions in `FUNCS`, while keeping the public `TOOLS` list read-only.

- [ ] **Step 4: Run tests and verify GREEN**

```powershell
python -B -m unittest tests.test_tools_agent.ToolIntegrationTests -v
```

Expected: tool wrappers call real local HTTP handlers and schemas match the safe allowlist.

- [ ] **Step 5: Commit the tools slice**

```powershell
git add lost-and-found/tools.py lost-and-found/tests/test_tools_agent.py
git commit -m "feat: expose lost-and-found agent tools"
```

### Task 4: Intent detection and ReAct Agent

**Files:**
- Create: `lost-and-found/agent.py`
- Modify: `lost-and-found/llm.py`
- Modify: `lost-and-found/tests/test_tools_agent.py`

- [ ] **Step 1: Write failing intent tests**

Assert:

```python
self.assertEqual(detect_intent("我在图书馆丢了黑色耳机")["intent"], "寻物")
self.assertEqual(detect_intent("我要认领 LF2026001")["intent"], "认领")
self.assertEqual(detect_intent("查看 LF2026001 的交接时段")["intent"], "交接")
```

Entities must include `item_id`, `location`, `category`, and `color` when present.

- [ ] **Step 2: Write failing two-step ReAct test**

With item and handover HTTP handlers running, call:

```python
answer = react_agent("查一下 LF2026001 是什么，并看看有哪些交接时段", verbose=True)
```

Capture stdout and assert the trace calls `query_item` before `list_handover_slots`, then produces a final answer containing `LF2026001` and `图书馆服务台`.

- [ ] **Step 3: Run tests and verify RED**

```powershell
python -B -m unittest tests.test_tools_agent.IntentTests tests.test_tools_agent.ReactAgentTests -v
```

Expected: import failure because `agent.py` is absent and the mock LLM still uses e-commerce routing rules.

- [ ] **Step 4: Implement `agent.py`**

Implement `detect_intent(text)` with a JSON-only system prompt and `react_agent(user_text, max_steps=6, verbose=True)` with the same OpenAI-compatible message/tool loop used by the reference framework. Unknown tool names must return a controlled error observation rather than raising `KeyError`.

- [ ] **Step 5: Personalize the offline LLM**

Update `_route`, `_summarize`, `_intent`, `_tool_step`, and `_final_answer` to understand lost-item IDs (`LF` plus digits), claim IDs (`CL` plus digits), item descriptions, locations, claims, and handover slots. The two-step mock plan must query the item first, read its observation, then query handover slots.

- [ ] **Step 6: Run Agent tests and verify GREEN**

```powershell
python -B -m unittest tests.test_tools_agent -v
```

Expected: intent cases pass; ReAct trace shows two tool actions followed by a final response.

- [ ] **Step 7: Commit the Agent slice**

```powershell
git add lost-and-found/agent.py lost-and-found/llm.py lost-and-found/tests/test_tools_agent.py
git commit -m "feat: add lost-and-found ReAct agent"
```

### Task 5: Documentation and end-to-end verification

**Files:**
- Modify: `lost-and-found/README.md`

- [ ] **Step 1: Document experiment-two operation**

Add the three service contracts, PowerShell startup commands, curl examples, intent command, ReAct command, expected trace, file mapping, and experiment-two acceptance checklist. State that RAG, multi-Agent routing, BPMN execution, and the Web UI remain outside experiment two.

- [ ] **Step 2: Run the full automated suite**

```powershell
python -B -m unittest discover -s tests -v
```

Expected: experiment-one and experiment-two tests all pass with zero warnings.

- [ ] **Step 3: Run three independent service smoke checks**

Start each service as a separate hidden process, call one success endpoint and one missing-resource endpoint, verify JSON and HTTP status, then terminate only those three process IDs.

- [ ] **Step 4: Run Agent demonstrations**

```powershell
python -B -c "from agent import detect_intent; print(detect_intent('我在图书馆丢了黑色耳机'))"
python -B -c "from agent import react_agent; print(react_agent('查一下 LF2026001 是什么，并看看有哪些交接时段'))"
```

Expected: structured `寻物` intent and a two-action ReAct trace.

- [ ] **Step 5: Check repository scope and commit docs**

```powershell
git status --short
git diff --check
git add lost-and-found/README.md lost-and-found/docs/superpowers/plans/2026-06-29-experiment-two.md
git commit -m "docs: complete experiment two"
```
