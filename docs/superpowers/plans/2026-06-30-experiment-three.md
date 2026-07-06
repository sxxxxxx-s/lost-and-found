# Experiment Three Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add policy RAG, conversation memory, multi-Agent routing, and executable BPMN-to-microservice integration to the personalized lost-and-found system.

**Architecture:** A small character n-gram vector store retrieves policy text with similarity scores, while `Memory` provides a sliding window, summary, and profile. A router dispatches to search, claim, handover, and policy experts; deterministic claim requests execute `claim_return.bpmn`, whose delegate expressions resolve to handlers that call the three REST services.

**Tech Stack:** Python 3.8+, optional NumPy with standard-library fallback, XML ElementTree, OpenAI-compatible chat/tool API, `unittest`.

---

## File Structure

- Create `lost-and-found/rag.py`: character n-gram vector store and policy retrieval.
- Create `lost-and-found/memory.py`: sliding-window history, summary, profile, and recent item recall.
- Create `lost-and-found/bpmn_engine.py`: BPMN parser and deterministic executor.
- Create `lost-and-found/bpmn_handlers.py`: delegate-expression registry and claim workflow handlers.
- Modify `lost-and-found/tools.py`: add policy retrieval as an Agent tool.
- Modify `lost-and-found/llm.py`: add policy tool planning and domain routing behavior.
- Modify `lost-and-found/agent.py`: add memory-aware ReAct, router, experts, and orchestration.
- Create `lost-and-found/tests/test_experiment3.py`: RAG, memory, engine, handlers, and orchestration tests.
- Modify `lost-and-found/tests/test_tools_agent.py`: update the model tool allowlist for policy retrieval.
- Modify `lost-and-found/README.md`: document experiment-three architecture and commands.

### Task 1: Policy RAG and conversation memory

**Files:**
- Create: `lost-and-found/rag.py`
- Create: `lost-and-found/memory.py`
- Create: `lost-and-found/tests/test_experiment3.py`

- [x] **Step 1: Write failing RAG tests**

Assert `retrieve_scored("高价值电脑认领")` ranks `高价值物品` first with a positive float score, `retrieve("隐藏特征能公开吗")` contains the privacy policy, and unknown text returns a list without raising.

- [x] **Step 2: Write failing memory tests**

Create `Memory(window=2)`, add four messages containing `LF2026001`, and assert history is limited to two entries, summary retains the item ID, profile data appears in `build()`, and `recall_item()` returns `LF2026001`.

- [x] **Step 3: Run tests and verify RED**

```powershell
python -B -m unittest tests.test_experiment3.RagTests tests.test_experiment3.MemoryTests -v
```

Expected: imports fail because `rag.py` and `memory.py` are absent.

- [x] **Step 4: Implement RAG**

Build unigram/bigram term-frequency vectors from `data.POLICIES`, calculate cosine similarity, and expose:

```python
retrieve(query, k=2) -> list[str]
retrieve_scored(query, k=3) -> list[tuple[str, str, float]]
```

Use NumPy when importable and a mathematically equivalent list-based fallback otherwise.

- [x] **Step 5: Implement memory**

Implement `add`, `_summarize`, `remember`, `build`, and `recall_item`. Summaries must preserve `LF...`/`CL...` identifiers; full hidden-evidence text must not be copied into the long-term profile.

- [x] **Step 6: Run tests and verify GREEN**

```powershell
python -B -m unittest tests.test_experiment3.RagTests tests.test_experiment3.MemoryTests -v
```

Expected: all RAG and memory tests pass.

### Task 2: BPMN parser and engine

**Files:**
- Create: `lost-and-found/bpmn_engine.py`
- Modify: `lost-and-found/tests/test_experiment3.py`

- [x] **Step 1: Write failing engine tests**

Load `flows/claim_return.bpmn` and assert `Task_QueryItem` resolves to `h_query_item`. Execute it with fake handlers for these contexts:

```python
{"match_score": 100, "high_value": False}  # auto approval and appointment
{"match_score": 100, "high_value": True}   # manual review
{"match_score": 60, "high_value": False}   # request evidence
```

Assert trace branch names and terminal notification for all three.

- [x] **Step 2: Run tests and verify RED**

```powershell
python -B -m unittest tests.test_experiment3.BpmnEngineTests -v
```

Expected: import failure because `bpmn_engine.py` is absent.

- [x] **Step 3: Implement parser and executor**

Parse start/end events, tasks, user tasks, exclusive gateways, sequence flows, conditions, defaults, and delegate expressions. Evaluate only simple comparisons over context variables; do not expose Python builtins or arbitrary `eval`. Raise `BpmnExecutionError` for a missing start, missing outgoing flow, invalid condition, or step-limit exhaustion.

- [x] **Step 4: Run tests and verify GREEN**

```powershell
python -B -m unittest tests.test_experiment3.BpmnEngineTests -v
```

Expected: all three paths execute and trace the correct branches.

### Task 3: BPMN handlers and real service integration

**Files:**
- Create: `lost-and-found/bpmn_handlers.py`
- Modify: `lost-and-found/tests/test_experiment3.py`

- [x] **Step 1: Write failing handler integration tests**

Run all three service handlers on ephemeral ports and configure `tools` plus `handover_service.CLAIM_URL`. Assert:

```text
LF2026001 + full evidence → 已通过 + AP0001
LF2026002 + full evidence → 待人工复核 + no appointment
LF2026003 + public-only evidence → 待补充证据 + no appointment
```

Each returned trace must contain the expected “是/否” branches and delegate names.

- [x] **Step 2: Run tests and verify RED**

```powershell
python -B -m unittest tests.test_experiment3.BpmnHandlerTests -v
```

Expected: import failure because `bpmn_handlers.py` is absent.

- [x] **Step 3: Implement handlers**

Map six delegate names plus `Task_ManualReview` to functions. `h_verify_evidence` creates a claim after matching; missing items set `match_score=0` without creating a claim. Auto approval selects the first available slot and creates the appointment. Notification adds a relevant RAG policy and returns a final text without hidden features.

- [x] **Step 4: Run tests and verify GREEN**

```powershell
python -B -m unittest tests.test_experiment3.BpmnHandlerTests -v
```

Expected: all three real HTTP-backed BPMN paths pass.

### Task 4: RAG tool and multi-Agent orchestration

**Files:**
- Modify: `lost-and-found/tools.py`
- Modify: `lost-and-found/llm.py`
- Modify: `lost-and-found/agent.py`
- Modify: `lost-and-found/tests/test_tools_agent.py`
- Modify: `lost-and-found/tests/test_experiment3.py`

- [x] **Step 1: Write failing policy-tool and routing tests**

Require `search_policy` in `FUNCS` and `TOOLS`. Assert router values for search, claim, handover, and policy queries, and assert the policy expert cites the high-value policy.

- [x] **Step 2: Write failing BPMN orchestration test**

With all services running, call:

```python
orchestrate(
    "我要认领 LF2026001，蓝牙耳机在图书馆遗失，日期2026-06-28，盒内刻有ZL",
    user_id="u001",
    verbose=True,
)
```

Assert route `认领`, answer prefix `【认领专家·BPMN流程】`, and a trace containing automatic approval plus appointment creation.

- [x] **Step 3: Run tests and verify RED**

```powershell
python -B -m unittest tests.test_experiment3.MultiAgentTests -v
```

Expected: routing/orchestration functions and policy tool are absent.

- [x] **Step 4: Add policy tool and mock planning**

Wrap `rag.retrieve` as `search_policy`, expose it in `FUNCS` and `TOOLS`, and update the offline LLM to call it for rule/policy questions and label policy results correctly.

- [x] **Step 5: Add router and experts**

Add `router`, search/claim/handover/policy experts, `EXPERTS`, and `orchestrate`. Claim requests containing an item ID execute `run_claim`; other requests use ReAct. Extend `react_agent` with optional memory context messages.

- [x] **Step 6: Run tests and verify GREEN**

```powershell
python -B -m unittest tests.test_experiment3.MultiAgentTests tests.test_tools_agent -v
```

Expected: policy retrieval, routing, BPMN claim orchestration, and experiment-two regressions pass.

### Task 5: Documentation and final verification

**Files:**
- Modify: `lost-and-found/README.md`

- [x] **Step 1: Document experiment three**

Add RAG, memory, expert routing, BPMN delegate mapping, three workflow paths, startup order, commands, expected traces, and acceptance checklist. State that guards, evaluation, Web API, and UI belong to experiment four.

- [x] **Step 2: Run the full test suite**

```powershell
python -B -m unittest discover -s tests -v
```

Expected: all experiment-one through experiment-three tests pass without warnings.

- [x] **Step 3: Run command-line demonstrations**

Start the three services, run `rag.py`, run a policy orchestration query, and run all three `run_claim` paths. Verify route, delegate-expression, gateway, service, and final-answer traces.

- [x] **Step 4: Check repository scope**

```powershell
git diff --check
git status --short
```

Expected: only experiment-three files are changed and `.env` remains ignored.
