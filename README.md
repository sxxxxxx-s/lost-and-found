# “寻迹校园”失物招领可信归还 Agent

本目录是“基于 Agent 的服务工程应用实践”课程的个性化实验工程。系统面向校园失物招领场景，用 Agent 处理自然语言，用 BPMN 固化可信认领流程，并由微服务提供失物、认领和交接能力。

当前完成范围：

- **实验一——业务流程建模（BPMN）与开发环境搭建**；
- **实验二——微服务搭建与 Agent 工具调用（含 ReAct）**；
- **实验三——RAG、会话记忆、多 Agent 编排与 BPMN 流程集成**；
- **实验四——护栏、自动评测、Web API 与前端轨迹可视化**。

按课程安排不实现实验五。

## 1. 实验一目标

- 理解“业务流程 → 微服务 → Agent 编排”三层架构。
- 使用 BPMN 2.0 建模可信认领流程。
- 为任务配置稳定节点 ID 和 Delegate Expression。
- 配置并运行统一 LLM 客户端；无 API Key 时使用离线教学桩。
- 使用自动化测试校验 BPMN 结构和 LLM 基础行为。

## 2. 环境要求

- Python 3.8 或更高版本。
- 实验一离线运行只使用 Python 标准库。
- `numpy`、`requests` 供后续实验使用。
- 使用真实 OpenAI 兼容模型时，需要额外安装 `openai`。

安装课程基础依赖：

```powershell
python -m pip install -r requirements.txt
```

## 3. 配置大模型

复制安全配置模板：

```powershell
Copy-Item .env.example .env
```

离线教学桩保持：

```dotenv
OPENAI_API_KEY=
CHAT_MODEL=mock-llm
```

使用真实 OpenAI 兼容模型时：

```powershell
python -m pip install openai
```

然后在本地 `.env` 中填写：

```dotenv
OPENAI_API_KEY=你的密钥
OPENAI_BASE_URL=服务商的兼容接口地址
CHAT_MODEL=服务商支持的模型名
```

`.env` 已被 `.gitignore` 排除，不应提交真实密钥。

## 4. 运行 LLM 客户端

```powershell
python -B llm.py
```

未配置 API Key 时，预期输出：

```text
当前后端: mock-llm(教学桩,离线可复现)
您好,我可以帮您查找失物、提交认领申请或安排交接,请问需要什么?
```

## 5. 项目结构

```text
lost-and-found/
├─ flows/
│  └─ claim_return.bpmn       # 实验一：可信认领流程
├─ services/                  # 实验二：三个微服务
│  ├─ item_service.py
│  ├─ claim_service.py
│  └─ handover_service.py
├─ web/
│  └─ index.html             # 实验四：对话与轨迹双栏页面
├─ tests/
│  ├─ test_services.py        # 实验二 HTTP 契约检查
│  ├─ test_tools_agent.py     # 实验二工具和 Agent 检查
│  ├─ test_experiment3.py     # 实验三 RAG/BPMN/多 Agent 检查
│  ├─ test_experiment4.py     # 实验四护栏、评测与 Web 检查
│  └─ test_experiment1.py     # 实验一自动化检查
├─ docs/superpowers/
│  ├─ specs/                  # 已批准的系统设计
│  └─ plans/                  # 实验一实施计划
├─ .env.example               # 安全配置模板
├─ .gitignore                 # 密钥与缓存排除规则
├─ requirements.txt           # 课程基础依赖
├─ data.py                    # 失物、认领、交接演示数据
├─ rag.py                     # 字符 n-gram 政策向量检索
├─ memory.py                  # 滑动窗口、摘要和长期画像
├─ bpmn_engine.py             # BPMN 解析与确定性执行
├─ bpmn_handlers.py           # BPMN 节点与微服务接线
├─ guardrails.py              # 输入、授权与输出护栏
├─ app.py                     # 护栏到 Agent 的统一调用入口
├─ server.py                  # Web API 与微服务统一启动器
├─ evaluate.py                # LLM-as-judge 离线评测
├─ llm.py                     # 统一 LLM 客户端
├─ tools.py                   # 微服务工具包装及工具契约
├─ agent.py                   # 意图识别和 ReAct Agent
└─ README.md                  # 本说明
```

## 6. 三层架构与本实验边界

| 层次 | 本系统职责 | 实验一状态 |
|---|---|---|
| 业务流程层 | 认领证据核验、自动/人工分支、交接预约 | 已完成 BPMN 图、引擎和处理器接线 |
| 服务能力层 | 失物服务、认领服务、交接服务 | 已完成三个独立 REST 服务 |
| 智能编排层 | 意图识别、ReAct、多 Agent、RAG、记忆、护栏 | 已完成 |
| 前后端 | 对话 API 与轨迹可视化 | 已完成 |

## 7. BPMN 流程

文件：`flows/claim_return.bpmn`

```text
收到认领申请
  → 查询失物信息
  → 核验认领证据
  → ◇证据匹配度≥80？
      ├─否→ 通知补充证据 ───────────────────┐
      └─是→ ◇是否高价值物品？              │
               ├─是→ 人工复核 ─────────────┤
               └─否→ 自动通过认领→创建交接预约
                                             ↓
                                        通知申请人
                                             ↓
                                        认领处理完成
```

流程包含：

- 1 个开始事件；
- 1 个结束事件；
- 7 个任务，其中 6 个 Service Task、1 个 User Task；
- 2 个排他网关；
- 12 条顺序流。

满足指导书“开始事件、结束事件、至少 2 个排他网关、至少 4 个任务”的要求。

## 8. BPMN 节点与未来实现映射

| 显示名称 | 类型 | 节点 ID | Delegate Expression | 后续承担者 |
|---|---|---|---|---|
| 收到认领申请 | Start Event | `Start_Claim` | — | BPMN 引擎 |
| 查询失物信息 | Service Task | `Task_QueryItem` | `${h_query_item}` | 失物微服务 |
| 核验认领证据 | Service Task | `Task_VerifyEvidence` | `${h_verify_evidence}` | 失物微服务 + 认领微服务 |
| 证据匹配度≥80？ | Exclusive Gateway | `Gateway_Match` | — | BPMN 流程变量 |
| 通知补充证据 | Service Task | `Task_RequestEvidence` | `${h_request_evidence}` | 认领微服务 |
| 是否高价值物品？ | Exclusive Gateway | `Gateway_HighValue` | — | BPMN 流程变量 |
| 人工复核 | User Task | `Task_ManualReview` | — | 人工管理员 |
| 自动通过认领 | Service Task | `Task_AutoApprove` | `${h_auto_approve}` | 认领微服务 |
| 创建交接预约 | Service Task | `Task_CreateHandover` | `${h_create_handover}` | 交接微服务 |
| 通知申请人 | Service Task | `Task_Notify` | `${h_notify}` | Agent/LLM 生成回复 |
| 认领处理完成 | End Event | `End_Claim` | — | BPMN 引擎 |

## 9. 网关条件

| 网关 | “是”分支 | “否”分支 |
|---|---|---|
| 证据匹配度≥80？ | `${match_score >= 80}` | 无条件表达式，显式默认流 `Flow_1oi5m9v` |
| 是否高价值物品？ | `${high_value == True}` | 无条件表达式，显式默认流 `Flow_0x0ttpa` |

流程 ID 为 `Process_ClaimReturn`，并设置 `isExecutable="true"`。

## 10. 三条预期业务路径

1. 普通物品且证据充分：匹配“是” → 高价值“否” → 自动通过 → 创建预约 → 通知。
2. 高价值物品且证据充分：匹配“是” → 高价值“是” → 人工复核 → 通知，不自动预约。
3. 证据不足：匹配“否” → 通知补充证据 → 通知，不审批、不预约。

## 11. 自动化验证

在本目录执行：

```powershell
python -B -m unittest discover -s tests -v
```

测试覆盖：

- BPMN XML 可解析；
- 节点、任务、网关和顺序流数量；
- 所有节点 ID；
- Service Task 的 Delegate Expression；
- 网关条件和显式默认分支；
- 顺序流引用完整性；
- 离线 LLM 问候语已个性化；
- `.env` 加载后文件句柄被关闭。

## 12. 实验一验收清单

- [x] 已建立 `flows/`、`services/`、`web/` 和 `tests/` 目录。
- [x] 已提交 `flows/claim_return.bpmn`。
- [x] BPMN 包含开始、结束、2 个排他网关和 7 个任务。
- [x] 网关分支命名为“是/否”并设置条件。
- [x] 任务 ID 和 Delegate Expression 已配置。
- [x] 已说明各节点未来由微服务、Agent 还是人工承担。
- [x] 已放置并个性化 `llm.py`。
- [x] `.env` 支持离线/真实模型切换且不会进入版本库。
- [x] 离线 LLM 可运行并返回失物招领领域问候语。
- [x] 自动化测试可验证实验一交付物。

## 13. 实验二：三个微服务

### 13.1 独立启动

分别打开三个 PowerShell 终端，在 `lost-and-found` 目录执行：

```powershell
python -B services/item_service.py
python -B services/claim_service.py
python -B services/handover_service.py
```

默认端口：

| 服务 | 端口 | 职责 |
|---|---:|---|
| 失物服务 | 8001 | 搜索失物、查询公开详情、服务端核验证据 |
| 认领服务 | 8002 | 创建认领单、查询进度、更新审核状态 |
| 交接服务 | 8003 | 查询交接时段、创建及查询预约 |

交接服务创建预约时会通过 `CLAIM_URL` 调用认领服务，确认认领单属于当前用户且状态为“已通过”。因此创建预约时必须同时启动认领服务；服务之间只通过 HTTP/JSON 通信，不共享进程内字典。

### 13.2 失物服务契约

```text
GET  /items?keyword={keyword}&location={location}
GET  /items/{item_id}
POST /items/{item_id}/match
```

验证成功响应和 404：

```powershell
curl.exe -i "http://localhost:8001/items/LF2026001"
curl.exe -i "http://localhost:8001/items/UNKNOWN"
curl.exe -i "http://localhost:8001/items?keyword=耳机&location=图书馆"
```

公开查询不会返回 `secret_features` 或 `secret_keywords`。隐藏特征只在 `POST /match` 内部参与确定性评分。

### 13.3 认领服务契约

```text
POST /claims
GET  /claims/{claim_id}?user_id={user_id}
POST /claims/{claim_id}/approve
POST /claims/{claim_id}/manual-review
POST /claims/{claim_id}/request-evidence
```

状态为：`待核验`、`待补充证据`、`待人工复核`、`已通过`。重复认领返回 409，越权查询返回 403，不存在的认领单返回 404。

### 13.4 交接服务契约

```text
GET  /slots?item_id={item_id}
POST /appointments
GET  /appointments/{claim_id}?user_id={user_id}
```

只有状态为“已通过”的认领单可以创建预约。重复预约返回 409，越权查询返回 403。

## 14. 实验二：Agent 工具层

`tools.py` 中实现了全部微服务包装：

```text
search_items / query_item / verify_evidence
create_claim / query_claim / approve_claim
mark_manual_review / request_more_evidence
list_handover_slots / create_appointment / query_appointment
```

模型只能直接调用以下只读工具：

```text
search_items
query_item
query_claim
list_handover_slots
```

证据核验、审批和预约等状态变更函数保留在 `FUNCS` 中，供实验三的 BPMN 处理器调用，不直接暴露给普通寻物 Agent。

工具层使用标准库 `urllib.request`，即使尚未安装第三方 HTTP 客户端，也可以完成实验二。所有网络异常均转换为包含 `error` 的结构化结果。

## 15. 实验二：意图识别

```powershell
python -B -c "from agent import detect_intent; print(detect_intent('我在图书馆丢了黑色耳机'))"
```

离线预期输出：

```text
{'intent': '寻物', 'entities': {'location': '图书馆', 'color': '黑色', 'category': '耳机'}}
```

支持的意图：

```text
寻物 / 认领 / 交接 / 规则咨询 / 其他
```

## 16. 实验二：ReAct 多步调用

确保失物服务和交接服务已经启动，然后执行：

```powershell
python -B -c "from agent import react_agent; print(react_agent('查一下 LF2026001 是什么，并看看有哪些交接时段'))"
```

离线教学桩的预期轨迹：

```text
[第1步] 行动→调用 query_item({'item_id': 'LF2026001'})
         观察← 失物公开信息
[第2步] 行动→调用 list_handover_slots({'item_id': 'LF2026001'})
         观察← 可选时段
[第3步] 思考→信息已齐全,生成最终答复
```

这里的步骤不是业务代码写死的调用链；Agent 每一轮根据已有观察和工具契约决定下一步。真正发起 HTTP 请求的是 `tools.py`。

## 17. 实验二自动化验证

```powershell
python -B -m unittest discover -s tests -v
```

实验二测试覆盖：

- 三个服务的真实 HTTP 成功响应；
- 400、403、404、409 错误响应；
- 公开信息不泄露隐藏特征；
- 证据分数为 60/100 的确定性分支；
- 工具包装真实调用三个服务；
- 模型工具白名单不包含状态变更函数；
- 寻物、认领和交接意图识别；
- `query_item → list_handover_slots` 两步 ReAct 轨迹；
- 服务不可用时返回结构化错误。

## 18. 实验二验收清单

- [x] 三个微服务可独立启动。
- [x] 三个微服务均提供 HTTP/JSON 契约。
- [x] 正常请求与 404 响应经过真实 HTTP 测试。
- [x] 认领和预约服务包含 400、403、409 处理。
- [x] 微服务接口已包装为 Agent 工具。
- [x] 模型只能调用只读工具。
- [x] `detect_intent` 返回结构化意图和实体。
- [x] ReAct 能完成两步工具规划并打印轨迹。
- [x] 离线教学桩已完全替换电商领域规则。
- [x] 实验一回归测试保持通过。

## 19. 实验三：政策 RAG

`rag.py` 使用字符 unigram/bigram 的词频向量和余弦相似度。安装 NumPy 时使用矩阵运算；未安装时自动使用标准库实现，检索结果一致。

```powershell
python -B rag.py
```

典型输出：

```text
问:高价值电脑怎么认领
[相似度] 高价值物品: 手机、电脑和贵重首饰必须转人工复核。
```

主要接口：

```python
retrieve(query, k=2)          # 返回政策文本列表
retrieve_scored(query, k=3)   # 返回(标题, 文本, 相似度)
```

`search_policy` 已加入 Agent 工具契约，用于开放式规则问题。

## 20. 实验三：会话记忆

`Memory` 包含：

- 滑动窗口：只保留最近若干条原始消息；
- 摘要压缩：超出窗口的消息由统一 LLM 客户端压缩；
- 长期画像：保存非敏感偏好；
- 编号回忆：从历史或摘要回忆最近的 `LF...` 失物编号。

隐藏证据、秘密特征等内容禁止写入长期画像。

```python
from memory import Memory

memory = Memory(window=4)
memory.add("user", "我想找 LF2026001")
memory.remember("preferred_handover", "下午")
print(memory.recall_item())
```

## 21. 实验三：多 Agent 编排

路由与专家映射：

| 路由结果 | 专家 | 主要能力 |
|---|---|---|
| 寻物 | 寻物专家 | ReAct 搜索公开失物 |
| 认领 | 认领专家 | 有失物编号时执行 BPMN，否则 ReAct |
| 交接 | 交接专家 | 查询交接时段与预约信息 |
| 规则咨询 | 规则专家 | 直接使用 RAG 检索政策 |
| 其他 | 默认助手 | 返回能力说明 |

规则专家演示：

```powershell
python -B -c "from agent import orchestrate; print(orchestrate('高价值物品有什么规定',verbose=False))"
```

返回结果包含 `规则咨询` 路由、`【规则专家·RAG】` 前缀和“人工复核”政策。

## 22. 实验三：BPMN 引擎与处理器接线

执行链路：

```text
orchestrate
→ router=认领
→ expert_claim
→ run_claim
→ run_bpmn(claim_return.bpmn, HANDLERS, context)
→ 读取节点 camunda:delegateExpression
→ HANDLERS 查找同名函数
→ handler 通过 tools 调用微服务
→ handler 写入流程变量
→ 排他网关根据流程变量选择分支
```

Delegate Expression 对照：

| BPMN 节点 | 实现引用/处理器键 | Python 处理器 | 调用能力 |
|---|---|---|---|
| 查询失物信息 | `${h_query_item}` | `h_query_item` | 失物服务公开详情 |
| 核验认领证据 | `${h_verify_evidence}` | `h_verify_evidence` | 证据匹配 + 创建认领单 |
| 通知补充证据 | `${h_request_evidence}` | `h_request_evidence` | 认领状态更新 |
| 人工复核 | `Task_ManualReview` | `h_manual_review` | 标记待人工复核 |
| 自动通过认领 | `${h_auto_approve}` | `h_auto_approve` | 自动审批 |
| 创建交接预约 | `${h_create_handover}` | `h_create_handover` | 时段查询 + 创建预约 |
| 通知申请人 | `${h_notify}` | `h_notify` | 汇总结果 + RAG 政策 |

引擎只允许流程中使用的简单比较表达式，例如：

```text
${match_score >= 80}
${high_value == True}
```

不使用任意 Python `eval`，缺少节点、处理器、变量或默认流时会抛出 `BpmnExecutionError`。

## 23. 实验三：三条 BPMN 路径演示

先启动三个微服务：

```powershell
python -B services/item_service.py
python -B services/claim_service.py
python -B services/handover_service.py
```

分别使用不同用户执行三条路径：

```powershell
python -B -c "from bpmn_handlers import run_claim; print(run_claim('LF2026001','u001','蓝牙耳机 图书馆 2026-06-28 盒内刻有ZL'))"
python -B -c "from bpmn_handlers import run_claim; print(run_claim('LF2026002','u002','笔记本电脑 教学楼 2026-06-27 序列号后四位A7C9'))"
python -B -c "from bpmn_handlers import run_claim; print(run_claim('LF2026003','u003','校园卡 食堂 2026-06-29'))"
```

预期结果：

| 失物 | 匹配度/价值 | 网关路径 | 结果 |
|---|---|---|---|
| `LF2026001` | 100/普通 | 是 → 否 | 已通过并创建交接预约 |
| `LF2026002` | 100/高价值 | 是 → 是 | 待人工复核，无预约 |
| `LF2026003` | 60/普通 | 否 | 待补充证据，无预约 |

通过多 Agent 触发普通认领流程：

```powershell
python -B -c "from agent import orchestrate; print(orchestrate('我要认领 LF2026001，蓝牙耳机在图书馆遗失，日期2026-06-28，盒内刻有ZL',user_id='u004'))"
```

## 24. 实验三自动化验证

```powershell
python -B -m unittest discover -s tests -v
```

实验三测试覆盖：

- RAG 相似度、排序和隐私政策召回；
- 滑动窗口、摘要、画像和最近失物编号；
- BPMN 节点、顺序流、默认流和实现引用解析；
- 普通、高价值、证据不足三条引擎路径；
- BPMN 处理器真实调用三个 HTTP 服务；
- 路由 Agent 和四类专家；
- 认领专家触发 BPMN 并输出执行轨迹；
- 实验一、实验二完整回归。

## 25. 实验三验收清单

- [x] RAG 返回带相似度的排序结果。
- [x] RAG 可召回高价值、隐私和交接政策。
- [x] 会话记忆支持窗口、摘要和长期画像。
- [x] 多 Agent 能正确分派寻物、认领、交接和规则咨询。
- [x] BPMN 引擎真实解析 `claim_return.bpmn`。
- [x] Delegate Expression 与处理器注册表一致。
- [x] 处理器通过 HTTP 调用微服务并写入流程变量。
- [x] 不同数据能够走出三条不同分支。
- [x] 认领专家能够触发 BPMN 流程并输出轨迹。
- [x] 自动化测试覆盖实验一至实验三。

## 26. 实验四：护栏调用链

统一入口 `app.py` 按固定顺序处理请求：

```text
输入护栏 → 认领单/预约授权护栏 → 多 Agent 或 BPMN
         → 手机号/学号脱敏 → 结构化 trace
```

护栏覆盖：

- 拦截“忽略以上指令”等提示注入；
- 拦截批量索取隐藏特征、修改 `match_score/high_value` 和绕过人工复核；
- 查询 `CL...` 或 `AP...` 前校验当前 `user_id`；
- 手机号 `13812345678` 输出为 `138****5678`；
- 完整学号 `2026062901` 输出为 `2026****01`。

正常提交个人认领证据不会被输入护栏误拦截。

## 27. 实验四：启动可视化系统

在本目录执行一条命令：

```powershell
python -B server.py
```

程序会在后台启动失物、认领和交接服务，并在 `8000` 端口提供 Web 页面。浏览器打开：

```text
http://localhost:8000
```

页面最大程度复用 `service-agent-lab/web/index.html` 的双栏结构：左侧对话，右侧显示路由、工具调用和 BPMN 执行轨迹。页面增加 `u001/u002/u003` 用户选择器，并在宽度小于 820px 时改为上下布局。

## 28. Web API 契约

请求：

```http
POST /api/chat
Content-Type: application/json

{"message":"帮我找图书馆发现的黑色耳机","user_id":"u001"}
```

响应：

```json
{
  "reply": "面向用户的回答",
  "intent": "寻物",
  "trace": "[路由] ...",
  "latency": 0.012
}
```

空消息或非法 JSON 返回 HTTP 400，未知页面/API 返回 HTTP 404。每个 `user_id` 使用独立的 `Memory`。

## 29. Web 演示场景

页面快捷按钮可以直接验证：

| 场景 | 用户 | 预期 |
|---|---|---|
| 图书馆黑色耳机寻物 | `u001` | 返回 `LF2026001` 和工具轨迹 |
| 普通认领 `LF2026001` | `u001` | 自动通过、创建预约、显示 BPMN 两个网关 |
| 高价值认领 `LF2026002` | `u002` | 转人工复核，不创建预约 |
| 校园卡证据不足 `LF2026003` | `u003` | 通知补充证据 |
| 高价值规则咨询 | 任意 | RAG 返回人工复核政策 |
| 提示注入 | 任意 | `BLOCKED`，不进入 Agent |

越权演示：先用 `u001` 完成普通认领以创建 `CL0001`，再切换为 `u002`，点击“越权测试”。右侧应显示授权护栏拦截，而不是认领单内容。

## 30. 自动评测与评测驱动改进

默认检索两条政策并运行完整评测：

```powershell
python -B evaluate.py
```

比较检索深度：

```powershell
$env:POLICY_K='1'; python -B evaluate.py
$env:POLICY_K='2'; python -B evaluate.py
Remove-Item Env:POLICY_K
```

离线 MockLLM 下的可复现结果：

| `POLICY_K` | 结果 | 说明 |
|---:|---:|---|
| 1 | 7/8（88%） | 复合政策问题只召回人工复核政策 |
| 2 | 8/8（100%） | 同时覆盖人工复核与 3 日交接政策 |

评测集还覆盖寻物、三条 BPMN 路径、提示注入、越权和 PII 脱敏。配置真实 API Key 后，judge 使用同一 OpenAI 兼容接口。

## 31. 实验四自动化验证

```powershell
python -B -m unittest discover -s tests -v
python -B -m compileall -q .
git diff --check
```

实验四测试覆盖：

- 输入注入、隐藏信息索取、流程变量篡改和审核绕过；
- 认领单/预约归属校验与 PII 脱敏；
- 护栏短路、异常降级、用户记忆和 trace 捕获；
- 三个业务服务的临时端口启动与 URL 注入；
- Web API 的 200、400、404 和 UTF-8 JSON；
- 前端双栏结构、用户选择、快捷示例、安全文本渲染和响应式布局；
- `POLICY_K` 检索深度与 LLM-as-judge。

## 32. 实验四验收清单

- [x] 输入护栏在 Agent 执行前拦截提示注入。
- [x] 认领单和预约查询校验当前用户。
- [x] 回复中的手机号和完整学号会被脱敏。
- [x] 自动评测可离线运行并展示 88% → 100% 的改进。
- [x] `python server.py` 可统一启动三个微服务和 Web 页面。
- [x] 页面可发送消息并显示 Agent/BPMN 轨迹。
- [x] 页面可切换用户并演示越权拦截。
- [x] 页面复用参考项目布局且支持窄屏。
- [x] 实验一至实验三功能保持兼容。

## 33. 项目完成范围

课程实验一至实验四均已实现。实验五的 Docker、Kubernetes 和 Java 集成按已确认范围不实施。
