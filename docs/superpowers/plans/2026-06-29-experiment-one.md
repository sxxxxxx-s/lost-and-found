# Experiment One Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete experiment one for the personalized lost-and-found Agent system with an executable BPMN model, a verified LLM client, safe environment configuration, automated checks, and experiment documentation.

**Architecture:** Keep experiment one limited to the business-process layer and LLM infrastructure. Validate the BPMN XML independently of later microservices, personalize only the mock LLM greeting, and document how every BPMN node will connect to later service or human capabilities.

**Tech Stack:** Python 3.8+ standard library, `unittest`, BPMN 2.0 XML, Camunda delegate expressions, Git.

---

## File Structure

- Modify `lost-and-found/flows/claim_return.bpmn`: make the process executable and declare explicit default gateway flows.
- Modify `lost-and-found/llm.py`: personalize the offline fallback greeting.
- Create `lost-and-found/tests/test_experiment1.py`: validate BPMN structure, expressions, graph paths, and mock LLM output.
- Create `lost-and-found/.gitignore`: exclude secrets and Python caches.
- Create `lost-and-found/.env.example`: document safe configuration without a key.
- Create `lost-and-found/services/.gitkeep`: preserve the future microservice directory.
- Create `lost-and-found/web/.gitkeep`: preserve the future Web directory.
- Create `lost-and-found/README.md`: record experiment-one setup, BPMN mapping, commands, and acceptance evidence.

### Task 1: Standardize and validate the BPMN model

**Files:**
- Create: `lost-and-found/tests/test_experiment1.py`
- Modify: `lost-and-found/flows/claim_return.bpmn`

- [ ] **Step 1: Write the failing BPMN test**

Create a `unittest` case that parses `claim_return.bpmn` and asserts:

```python
self.assertEqual(process.get("id"), "Process_ClaimReturn")
self.assertEqual(process.get("isExecutable"), "true")
self.assertEqual(gateway_match.get("default"), "Flow_1oi5m9v")
self.assertEqual(gateway_high.get("default"), "Flow_0x0ttpa")
```

The same test must verify 1 start event, 1 end event, 7 tasks, 2 gateways, 12 flows, the six delegate expressions, and one conditioned plus one fallback branch per gateway.

- [ ] **Step 2: Run the test and verify RED**

Run from `lost-and-found/`:

```powershell
python -B -m unittest tests.test_experiment1.ExperimentOneBpmnTests -v
```

Expected: FAIL because the current process uses `Process_1`, `isExecutable="false"`, and has no explicit gateway defaults.

- [ ] **Step 3: Apply the minimal BPMN changes**

Change:

```xml
<process id="Process_ClaimReturn" isExecutable="true">
<exclusiveGateway id="Gateway_Match" ... default="Flow_1oi5m9v">
<exclusiveGateway id="Gateway_HighValue" ... default="Flow_0x0ttpa">
<bpmndi:BPMNPlane ... bpmnElement="Process_ClaimReturn">
```

Do not alter task IDs, delegate expressions, conditions, sequence-flow IDs, or diagram coordinates.

- [ ] **Step 4: Run the test and verify GREEN**

```powershell
python -B -m unittest tests.test_experiment1.ExperimentOneBpmnTests -v
```

Expected: all BPMN tests pass.

- [ ] **Step 5: Commit the BPMN slice**

```powershell
git add lost-and-found/tests/test_experiment1.py lost-and-found/flows/claim_return.bpmn
git commit -m "test: validate experiment one BPMN"
```

### Task 2: Personalize and test the offline LLM greeting

**Files:**
- Modify: `lost-and-found/tests/test_experiment1.py`
- Modify: `lost-and-found/llm.py`

- [ ] **Step 1: Write the failing greeting test**

Add:

```python
def test_mock_greeting_matches_lost_and_found_domain(self):
    client = llm.MockLLM()
    message = client.chat.completions.create(
        messages=[{"role": "user", "content": "你好"}]
    ).choices[0].message.content
    self.assertIn("失物", message)
    self.assertIn("认领", message)
    self.assertNotIn("订单", message)
```

- [ ] **Step 2: Run the test and verify RED**

```powershell
python -B -m unittest tests.test_experiment1.ExperimentOneLlmTests -v
```

Expected: FAIL because the copied mock client still returns the e-commerce greeting.

- [ ] **Step 3: Implement the minimal personalized fallback**

Replace only the no-observation fallback text with:

```python
"您好,我可以帮您查找失物、提交认领申请或安排交接,请问需要什么?"
```

- [ ] **Step 4: Run the LLM and full tests**

```powershell
python -B -m unittest discover -s tests -v
python -B llm.py
```

Expected: tests pass; the program prints `mock-llm` and a lost-and-found greeting when `OPENAI_API_KEY` is empty.

- [ ] **Step 5: Commit the LLM slice**

```powershell
git add lost-and-found/tests/test_experiment1.py lost-and-found/llm.py
git commit -m "feat: personalize experiment one LLM greeting"
```

### Task 3: Add safe configuration and experiment documentation

**Files:**
- Create: `lost-and-found/.gitignore`
- Create: `lost-and-found/.env.example`
- Create: `lost-and-found/services/.gitkeep`
- Create: `lost-and-found/web/.gitkeep`
- Create: `lost-and-found/README.md`

- [ ] **Step 1: Add safe local configuration rules**

Use:

```gitignore
.env
__pycache__/
*.py[cod]
.pytest_cache/
```

Create `.env.example` with empty `OPENAI_API_KEY`, the OpenAI-compatible base URL, `CHAT_MODEL=mock-llm`, and future `ITEM_URL`, `CLAIM_URL`, and `HANDOVER_URL` values.

- [ ] **Step 2: Preserve required project directories**

Create empty `.gitkeep` files under `services/` and `web/` so the experiment-one directory structure is committed.

- [ ] **Step 3: Write the experiment README**

Document:

- system objective and three-layer architecture;
- Python 3.8+ prerequisite;
- `.env.example` to `.env` workflow;
- exact LLM and test commands;
- BPMN node IDs, types, delegate expressions, conditions, and future owners;
- the three expected BPMN paths;
- an experiment-one acceptance checklist;
- explicit statement that microservices and Agent orchestration belong to experiments two and three.

- [ ] **Step 4: Validate documentation and secret handling**

```powershell
git check-ignore lost-and-found/.env
git status --short
```

Expected: `.env` is ignored; only intended experiment-one files are shown.

- [ ] **Step 5: Commit configuration and documentation**

```powershell
git add lost-and-found/.gitignore lost-and-found/.env.example lost-and-found/README.md lost-and-found/services/.gitkeep lost-and-found/web/.gitkeep
git commit -m "docs: complete experiment one setup"
```

### Task 4: Final experiment-one verification

**Files:**
- Verify: `lost-and-found/`

- [ ] **Step 1: Run the full automated suite**

```powershell
python -B -m unittest discover -s tests -v
```

Expected: all tests pass with zero failures.

- [ ] **Step 2: Run the offline LLM smoke test**

```powershell
python -B llm.py
```

Expected: backend is `mock-llm`; output contains “失物” and “认领”.

- [ ] **Step 3: Check repository scope**

```powershell
git status --short
git log --oneline -5
```

Expected: no tracked experiment-one changes remain uncommitted; `.env` does not appear; commits are limited to the plan and experiment-one deliverables.
