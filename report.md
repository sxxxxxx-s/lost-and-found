# “寻迹校园”失物招领可信归还 Agent 系统设计与实现报告

# 第1部分 服务创新设计

## 1.1 用户需求调研

本项目采用角色分析、典型场景走查和现有流程对比的方式进行需求调研。由于本课程项目未开展大规模问卷调查，本报告不虚构调查人数和统计比例，而是依据高校常见的失物招领处、班级群、校园墙和线下服务台流程归纳需求。

### 1.1.1 对标服务的实际运行流程

传统校园失物招领通常按以下方式运行：

1. 拾得者将物品交到服务台，或在班级群、校园墙发布信息。
2. 管理人员手工登记物品类别、颜色、发现地点和时间。
3. 失主需要反复浏览群消息，或前往多个服务台询问。
4. 申请认领时，工作人员通过口头描述判断申请人是否为失主。
5. 普通物品和贵重物品通常使用相似的人工审核方式。
6. 审核通过后，双方再通过电话或即时通信工具协商领取时间。

该模式可以完成基本归还，但存在以下问题：

- 信息入口分散，失主难以统一查询。
- 群消息时效性差，历史失物容易被新消息淹没。
- 如果公开过多物品特征，可能被冒领者利用。
- 证据核验依赖工作人员经验，缺少统一标准。
- 普通物品也需要人工逐项处理，管理成本较高。
- 高价值物品缺少明确的人审兜底流程。
- 认领、审核和交接信息分散，难以追踪完整过程。

### 1.1.2 目标用户和需求

| 用户角色 | 核心需求 | 系统对应功能 |
|---|---|---|
| 失主 | 快速查找候选失物，使用自然语言提交认领证据 | 寻物 Agent、失物搜索工具、认领 BPMN 流程 |
| 拾得者/服务台人员 | 规范登记失物，避免公开隐藏特征 | 失物微服务区分公开字段与服务端隐藏字段 |
| 审核人员 | 对高价值物品保留人工判断权 | 高价值网关和“人工复核”用户任务 |
| 交接人员 | 查看审核状态并安排领取时段 | 交接微服务、交接预约 |
| 学校管理者 | 降低重复工作，获得可追踪、可测试的服务流程 | BPMN 轨迹、Web trace、自动化测试与评测 |

据此，系统形成以下关键需求：

1. 支持自然语言寻物、认领、交接和规则咨询。
2. 公开查询不得返回物品隐藏特征。
3. 认领证据必须由服务端核验，用户不能直接指定匹配分。
4. 普通物品证据充分时允许自动通过，高价值物品必须人工复核。
5. 审核通过后自动创建交接预约。
6. 查询认领单和预约时必须校验当前用户身份。
7. 系统需要输出 Agent、工具调用和 BPMN 执行轨迹。
8. 在未配置真实大模型时，系统仍应能够离线运行和复现实验。

## 1.2 服务蓝图设计

系统服务蓝图将用户接触过程、前台交互、后台编排和微服务能力分开，以保证每一层职责清晰。

| 阶段 | 用户行为 | 前台接触点 | 后台 Agent/BPMN 行为 | 微服务与数据 | 异常及控制措施 |
|---|---|---|---|---|---|
| 寻物 | 描述物品、颜色和可能地点 | Web 对话区、快捷按钮 | 路由到寻物专家，ReAct 选择搜索工具 | 失物服务查询公开字段 | 服务不可用时返回结构化错误，不泄露隐藏特征 |
| 规则咨询 | 询问审核、隐私或交接政策 | Web 对话区 | 路由到规则专家，通过 RAG 检索政策 | `POLICIES` 知识库 | 未召回内容时明确提示，不编造规则 |
| 提交认领 | 输入失物编号和个人证据 | Web 对话区 | 路由到认领专家并启动 BPMN | 失物服务核验证据，认领服务创建认领单 | 空证据或分数不足进入补充证据分支 |
| 自动/人工审核 | 等待处理结果 | 回复区、右侧 trace | 匹配分网关和高价值网关选择路径 | 认领服务更新状态 | 高价值物品强制进入人工复核 |
| 创建交接 | 查看领取时间与地点 | 回复区 | 自动通过后执行创建预约任务 | 交接服务校验认领单并创建预约 | 未通过、重复预约或时段无效时拒绝 |
| 查询进度 | 输入 `CL...` 或 `AP...` 编号 | 用户选择器、对话区 | 应用层授权护栏后调用查询工具 | 认领/交接服务再次进行用户校验 | 越权返回拒绝信息，不返回业务数据 |
| 安全输出 | 查看最终回复 | Web 回复区 | 输入防注入、输出 PII 脱敏 | 会话记忆按用户隔离 | 手机号、完整学号脱敏，敏感请求被拦截 |

系统前后台分界如下：

```text
用户 / Web 页面
    ↓
server.py：HTTP API、用户会话
    ↓
app.py：输入护栏 → 授权护栏 → Agent/BPMN → 输出脱敏
    ↓
agent.py / bpmn_engine.py：智能编排与确定性业务流程
    ↓
tools.py：服务适配层
    ↓
失物服务(8001) / 认领服务(8002) / 交接服务(8003)
```

## 1.3 系统开发环境搭建

### 1.3.1 开发工具

| 工具 | 用途 |
|---|---|
| Python 3.8 及以上 | Agent、BPMN 引擎、微服务和 Web 后端开发 |
| VS Code 或其他 Python IDE | 源码编辑、终端运行和调试 |
| Git | 实验分支和版本管理 |
| demo.bpmn.io / Camunda Modeler | 绘制和检查 BPMN 2.0 流程 |
| PowerShell | 安装依赖、启动服务和运行测试 |
| 浏览器 | 使用系统前端并查看 Agent/BPMN trace |

项目的 Web 后端和三个微服务均使用 Python 标准库 `http.server`，不依赖 Flask、FastAPI、Vue 或 React。`numpy` 用于加速 RAG 向量运算；未安装时，`rag.py` 会自动使用标准库计算。

### 1.3.2 环境配置

安装基础依赖：

```powershell
python -m pip install -r requirements.txt
```

复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

离线教学模式的主要配置为：

```dotenv
OPENAI_API_KEY=
CHAT_MODEL=mock-llm
ITEM_URL=http://localhost:8001
CLAIM_URL=http://localhost:8002
HANDOVER_URL=http://localhost:8003
POLICY_K=2
```

未配置 `OPENAI_API_KEY` 时使用确定性的 MockLLM，可以离线完成意图识别、工具选择、摘要和评测。若需要接入真实 OpenAI 兼容模型，则安装 `openai` 并填写：

```dotenv
OPENAI_API_KEY=实际密钥
OPENAI_BASE_URL=兼容接口地址
CHAT_MODEL=实际模型名称
```

`.env` 已加入 `.gitignore`，避免密钥进入版本库。

### 1.3.3 启动方式

一条命令启动 Web 系统及三个后台微服务：

```powershell
python -B server.py
```

然后访问：

```text
http://localhost:8000
```

运行完整自动化测试：

```powershell
python -B -m unittest discover -s tests -v
```

## 1.4 服务模式、盈利模式创新设计与分析

当前项目是教学原型，代码中没有支付、计费或商业结算模块。以下内容属于基于现有系统能力提出的服务模式设计，而不是已经实现的收费功能。

### 1.4.1 服务模式

系统适合采用“学校统一采购、师生免费使用”的 B2B2C 服务模式：

- 学校保卫处、图书馆或后勤部门作为服务采购方。
- 学生和教职工免费使用寻物、认领和交接服务。
- 学校通过统一后台维护失物信息、规则知识库和人工复核任务。
- 系统以微服务方式接入校园统一身份认证、消息通知和现有办事大厅。

### 1.4.2 可行的盈利来源

1. **校园 SaaS 订阅**：按学校、校区或年度提供系统使用权和升级服务。
2. **私有化部署与运维**：面向对数据安全要求较高的高校提供本地部署、模型配置和运维。
3. **系统集成服务**：收费接入统一身份认证、企业微信、校园 App、短信和门禁系统。
4. **流程模板服务**：将 BPMN、Agent 和护栏框架扩展到报修、请假、场馆预约等校园服务。
5. **数据分析增值服务**：在脱敏和合规前提下，为学校提供高频遗失地点、物品类别和服务效率分析。

不建议向失主收取“赎回费”或按物品价值收费，因为这会损害公益属性，也可能诱发不良行为。商业价值应主要来自学校端的数字化服务采购、部署和运维。

# 第2部分 业务流程建模

## 2.1 业务流程建模设计

### 1 流程整体设计

业务流程文件为 `flows/claim_return.bpmn`，流程 ID 为 `Process_ClaimReturn`，并设置 `isExecutable="true"`。流程包含 1 个开始事件、1 个结束事件、7 个任务、2 个排他网关和 12 条顺序流。

整体流程为：

```text
收到认领申请
  → 查询失物信息
  → 核验认领证据
  → [证据匹配度≥80？]
      ├─ 否 → 通知补充证据 ──────────────┐
      └─ 是 → [是否高价值物品？]         │
                  ├─ 是 → 人工复核 ──────┤
                  └─ 否 → 自动通过认领   │
                           → 创建交接预约 ┤
                                         ↓
                                   通知申请人
                                         ↓
                                   认领处理完成
```

第一个网关使用 `${match_score >= 80}` 作为“是”分支条件；“否”分支设置为显式默认流。第二个网关使用 `${high_value == True}` 作为高价值分支条件；普通物品分支同样设置为默认流。显式默认流可以避免条件未命中时流程停滞。

证据匹配完全由失物服务在服务端计算。类别、发现地点、发现日期各占 20 分，匹配任意一组隐藏特征增加 40 分。只提供公开信息时通常得到 60 分；公开信息和有效隐藏特征同时匹配时得到 100 分。用户不能直接设置 `match_score` 或 `high_value`。

### 2 任务节点设计与实现

| 节点 | 类型 | 实现映射 | 主要作用 |
|---|---|---|---|
| 查询失物信息 | Service Task | `${h_query_item}` | 查询失物公开详情并写入 `high_value` |
| 核验认领证据 | Service Task | `${h_verify_evidence}` | 服务端计算匹配分并创建认领单 |
| 通知补充证据 | Service Task | `${h_request_evidence}` | 将认领单更新为“待补充证据” |
| 人工复核 | User Task | `Task_ManualReview` | 将高价值物品转入人工处理 |
| 自动通过认领 | Service Task | `${h_auto_approve}` | 将普通物品认领状态更新为“已通过” |
| 创建交接预约 | Service Task | `${h_create_handover}` | 查询时段并创建交接预约 |
| 通知申请人 | Service Task | `${h_notify}` | 汇总流程结果并附加相关政策 |

`bpmn_engine.py` 使用 XML ElementTree 解析 BPMN 文件。执行时根据 `camunda:delegateExpression` 在 `HANDLERS` 注册表中查找处理函数。条件表达式只支持布尔值和数字的简单比较，不使用任意 Python `eval`，降低了流程表达式注入风险。

### 3 微服务设计与实现

系统将业务能力拆分为三个独立 HTTP/JSON 服务：

| 微服务 | 端口 | 主要接口 | 设计职责 |
|---|---:|---|---|
| 失物服务 | 8001 | `GET /items`、`GET /items/{id}`、`POST /items/{id}/match` | 公开查询与服务端证据核验 |
| 认领服务 | 8002 | `POST /claims`、`GET /claims/{id}`、状态更新接口 | 认领单创建、授权查询和状态管理 |
| 交接服务 | 8003 | `GET /slots`、`POST /appointments`、预约查询接口 | 交接时段与预约管理 |

微服务拆分体现了单一职责原则：

- 失物服务负责“物品是什么、公开哪些信息、证据是否匹配”。
- 认领服务负责“谁提交了认领、当前审核状态是什么”。
- 交接服务负责“审核通过后在何时何地领取”。

各服务对 400、403、404 和 409 等情况返回明确的 JSON 错误。公开失物接口会过滤 `secret_features` 和 `secret_keywords`；交接服务创建预约前会调用认领服务，确认认领单属于当前用户且状态为“已通过”。

### 4 Agent 设计与实现

Agent 层采用“路由 Agent + 专家 Agent + 工具调用”的结构。

| 意图 | 专家 | 执行方式 |
|---|---|---|
| 寻物 | 寻物专家 | ReAct 调用失物搜索和公开详情工具 |
| 认领 | 认领专家 | 包含 `LF...` 时执行 BPMN，否则使用 ReAct |
| 交接 | 交接专家 | 查询交接时段或相关进度 |
| 规则咨询 | 规则专家 | 使用 RAG 检索政策 |
| 其他 | 默认助手 | 返回系统能力说明 |

模型直接可见的工具仅包括 `search_items`、`query_item`、`query_claim`、`list_handover_slots` 和 `search_policy` 等只读能力。证据核验、审批、状态修改和创建预约虽然存在于工具函数表中，但不向普通 Agent 工具白名单开放，而是由 BPMN 处理器按固定流程调用。

此外，Agent 层还实现了：

- **ReAct**：按照“思考—行动—观察”循环调用一个或多个服务。
- **RAG**：对五条认领政策构建字符 unigram/bigram 向量，并使用余弦相似度检索。
- **Memory**：采用滑动窗口、历史摘要和非敏感长期画像；隐藏证据禁止写入长期画像。
- **Guardrails**：拦截提示注入、批量隐藏特征索取、流程变量篡改和审核绕过。
- **用户授权**：查询 `CL...` 或 `AP...` 资源前校验其归属。
- **输出脱敏**：对手机号和完整学号进行掩码处理。

## 2.2 工作流运行结果

系统准备了三组演示数据，分别覆盖普通物品、高价值物品和证据不足场景。

### 场景一：普通物品证据充分

输入：

```text
我要认领 LF2026001，蓝牙耳机在图书馆遗失，
日期2026-06-28，盒内刻有ZL
```

关键流程变量为 `match_score=100`、`high_value=False`。执行路径为：

```text
匹配度网关“是” → 高价值网关“否”
→ 自动通过认领 → 创建交接预约 → 通知申请人
```

最终结果为“已通过”，并创建图书馆服务台交接预约。

### 场景二：高价值物品证据充分

输入：

```text
我要认领 LF2026002，笔记本电脑在教学楼遗失，
日期2026-06-27，序列号后四位A7C9
```

关键流程变量为 `match_score=100`、`high_value=True`。执行路径为：

```text
匹配度网关“是” → 高价值网关“是”
→ 人工复核 → 通知申请人
```

最终结果为“待人工复核”，系统不会自动创建预约。

### 场景三：证据不足

输入：

```text
我要认领 LF2026003，校园卡在食堂遗失，日期2026-06-29
```

该输入只匹配类别、地点和日期，得到 60 分。执行路径为：

```text
匹配度网关“否” → 通知补充证据 → 通知申请人
```

最终结果为“待补充证据”，不会审批或预约。

右侧 trace 会显示路由结果、任务名称、Delegate Expression、微服务返回值和网关所选“是/否”分支，因此每个业务结果都可以追溯。

## 2.3 工作流创新性分析及效果展示

本工作流的创新不在于单独使用大模型，而在于将开放式 Agent 和确定性 BPMN 组合：

1. **自然语言入口与确定性流程结合**：Agent 负责理解用户意图，BPMN 负责执行不可随意更改的认领规则。
2. **隐私保护式证据核验**：隐藏特征只保存在失物服务内部，用户提交证据后由服务端比对，系统不先向用户公开答案。
3. **风险分级处理**：普通物品可自动审批，高价值物品必须人工复核，实现效率与安全的平衡。
4. **状态变更工具隔离**：普通 Agent 只能调用只读工具，审批和预约等写操作必须经过 BPMN 节点。
5. **可解释执行**：页面展示 Agent 路由、ReAct 工具调用和 BPMN 轨迹，避免结果成为不可观察的黑盒。
6. **评测驱动改进**：当 `POLICY_K=1` 时复合政策问题评测为 7/8；调整为 `POLICY_K=2` 后达到 8/8，展示了“发现问题—修改参数—重新评测”的工程闭环。

效果展示时建议将 BPMN 图与三条路径的 trace 截图并列，从流程模型、运行轨迹和最终状态三个角度证明模型与实现一致。

# 第3部分 系统设计与实现

## 3.1 面向服务架构设计方案

系统采用分层、面向服务的体系结构：

```text
表现层
  web/index.html：对话、用户切换、执行轨迹
        ↓
接口层
  server.py：GET /、POST /api/chat、会话隔离
        ↓
应用编排层
  app.py：输入护栏、授权、Agent 调用、脱敏、trace
        ↓
智能与流程层
  agent.py / rag.py / memory.py
  bpmn_engine.py / bpmn_handlers.py
        ↓
服务适配层
  tools.py：HTTP/JSON 工具封装
        ↓
领域服务层
  item-service / claim-service / handover-service
```

该架构的主要特点如下：

- 表现层不直接访问业务数据，只调用统一的 `/api/chat`。
- Agent 不直接操作进程内字典，而是通过 `tools.py` 访问微服务。
- BPMN 处理器负责有副作用的业务操作，避免大模型直接审批。
- 三个服务具有清晰的 HTTP 契约，可以独立测试或替换实现。
- `app.py` 将护栏作为统一入口，避免不同调用端遗漏安全检查。
- `server.py` 为每个 `user_id` 保存独立 `Memory`，防止会话混用。

## 3.2 系统实现方案

### 3.2.1 项目结构

```text
lost-and-found/
├─ flows/claim_return.bpmn
├─ services/
│  ├─ item_service.py
│  ├─ claim_service.py
│  └─ handover_service.py
├─ web/index.html
├─ tests/
│  ├─ test_experiment1.py
│  ├─ test_services.py
│  ├─ test_tools_agent.py
│  ├─ test_experiment3.py
│  └─ test_experiment4.py
├─ data.py
├─ llm.py
├─ tools.py
├─ agent.py
├─ rag.py
├─ memory.py
├─ bpmn_engine.py
├─ bpmn_handlers.py
├─ guardrails.py
├─ app.py
├─ server.py
└─ evaluate.py
```

### 3.2.2 关键框架和工具应用

- `llm.py` 提供与 OpenAI Chat Completions 相同风格的统一接口，在真实模型和 MockLLM 之间切换。
- `tools.py` 使用 `urllib.request` 封装 HTTP 请求，并把网络异常转换为结构化错误。
- `bpmn_engine.py` 解析 BPMN XML，执行任务、排他网关、条件和默认流。
- `bpmn_handlers.py` 将 Delegate Expression 映射到实际微服务操作。
- `rag.py` 使用字符 n-gram 词频向量和余弦相似度检索政策。
- `memory.py` 使用滑动窗口与 LLM 摘要压缩长对话。
- `guardrails.py` 实现输入、授权和输出三类护栏。
- `server.py` 使用 `ThreadingHTTPServer` 同时提供静态页面和聊天 API，并启动三个后台业务服务。
- `web/index.html` 最大程度复用示例项目双栏页面，使用原生 HTML、CSS 和 JavaScript，不需要前端构建工具。

前端通过 `textContent` 渲染回复和 trace，不直接使用 `innerHTML` 插入模型输出。页面包含 `u001/u002/u003` 用户选择器，宽度小于 820px 时双栏自动改为上下布局。

### 3.2.3 Web API

请求示例：

```http
POST /api/chat
Content-Type: application/json

{"message":"帮我找图书馆发现的黑色耳机","user_id":"u001"}
```

响应示例：

```json
{
  "reply": "找到候选失物 LF2026001……",
  "intent": "寻物",
  "trace": "[路由] 判定意图 = 寻物……",
  "latency": 0.012
}
```

空消息、非法 JSON 和非对象 JSON 返回 400；未知页面或 API 返回 404。Agent 或记忆模块发生异常时，`app.py` 返回 `ERROR` 和受控提示，避免 Web 服务直接中断。

## 3.3 系统测试验证

### 3.3.1 自动化测试结果

2026 年 7 月 4 日在项目目录执行：

```powershell
python -B -m unittest discover -s tests -q
```

实际结果为：

```text
Ran 54 tests
OK
```

54 项测试覆盖：

- BPMN 节点、顺序流、条件和默认分支。
- 三个微服务的 200、400、403、404 和 409 响应。
- 公开失物信息不包含隐藏特征。
- Agent 意图识别、ReAct 多步工具调用和工具白名单。
- RAG 排序、会话记忆和多 Agent 路由。
- BPMN 三条路径与真实 HTTP 服务集成。
- 输入注入、越权、PII 脱敏和异常降级。
- Web API、用户会话隔离和前端静态结构。

自动评测结果为：

| 配置 | 通过结果 | 说明 |
|---|---:|---|
| `POLICY_K=1` | 7/8，88% | 复合问题只能召回一条政策 |
| `POLICY_K=2` | 8/8，100% | 同时覆盖人工复核和三日交接政策 |

### 3.3.2 截图组织逻辑

以下位置由报告提交者插入实际截图：

1. **图 3-1 系统首页**：运行 `python -B server.py` 后截取双栏页面，标出用户选择器、对话区和 trace 区。
2. **图 3-2 普通认领成功**：使用 `u001` 点击“普通认领”，截图回复中的“已通过”和交接预约，以及右侧两个网关的“是→否”轨迹。
3. **图 3-3 高价值人工复核**：使用 `u002` 点击“高价值认领”，截图“待人工复核”和未创建预约的轨迹。
4. **图 3-4 证据不足**：使用 `u003` 点击“证据不足”，截图“待补充证据”和匹配网关“否”分支。
5. **图 3-5 提示注入拦截**：点击“注入测试”，截图 `BLOCKED` 和输入护栏 trace。
6. **图 3-6 越权拦截**：先由 `u001` 创建 `CL0001`，再切换到 `u002` 查询，截图授权护栏拒绝结果。
7. **图 3-7 评测驱动改进**：分别运行 `POLICY_K=1` 和 `POLICY_K=2`，截取 88% 与 100% 的终端结果。
8. **图 3-8 自动化测试**：截取 `Ran 54 tests` 和 `OK`。

建议每张截图下方用一至两句话说明“输入、关键轨迹、最终状态”，不要只放图片而不分析。

## 3.4 面向服务技术的创新应用

### 3.4.1 OpenAI 兼容 API 的接口隔离

系统上层只依赖统一的 `client.chat.completions.create()` 和 `chat()` 接口，不关心后端是真实模型还是 MockLLM。该设计使课程演示可离线复现，同时保留接入真实大模型的能力。

### 3.4.2 Agent 与微服务工具化

传统系统通常由界面直接调用固定接口。本系统将微服务接口包装成带 JSON Schema 的 Agent 工具，使大模型可以根据自然语言和已有观察选择只读服务。工具层仍保持明确的服务边界和错误结构，不把网络调用细节暴露给 Agent。

### 3.4.3 Agent 与 BPMN 双重编排

开放式问题由 ReAct Agent 规划，认领等高风险写操作由 BPMN 固化。该方案发挥了大模型理解自然语言的优势，同时利用流程模型保证审核规则、人工复核和状态变化不可被随意绕过。

### 3.4.4 RAG 与评测驱动服务改进

系统没有把政策全部写入提示词，而是通过 RAG 按需检索。`POLICY_K` 可以控制检索深度，并由固定评测集验证改动效果。项目实际展示了通过率从 88% 提升到 100% 的过程，使模型参数调整有可重复的证据。

### 3.4.5 面向 Agent 的服务安全

系统在传统接口鉴权之外增加了 Agent 场景安全措施：

- 提示注入和批量敏感数据索取在进入 Agent 前被拦截。
- `match_score` 和 `high_value` 只能由服务端产生。
- 高价值物品必须进入人工复核。
- 状态变更函数不直接暴露给普通 Agent。
- 应用层和微服务层同时校验资源归属。
- 输出中的手机号和完整学号自动脱敏。

因此，本项目不是简单地“给微服务增加聊天界面”，而是将大模型 API、ReAct、RAG、会话记忆、BPMN、微服务、护栏和自动评测组合为一个可运行、可解释、可验证的面向服务系统。

# 第4部分 服务监控与质量评价

## 4.1 服务监控对象

本系统采用微服务架构，服务监控对象既包括系统内部软件服务，也包括 Agent 使用的 API 服务接口。由于系统当前是课程原型，运行期数据主要保存在进程内存中，因此本次评价重点监控服务接口、容器运行状态、资源消耗、调用结果、响应时间和异常处理能力。

| 服务 | 部署形态 | 主要接口 | 监控重点 |
|---|---|---|---|
| Web/Agent 服务 `web-agent` | Docker Compose 服务，对宿主机发布 `127.0.0.1:8000` | `GET /`、`GET /healthz`、`POST /api/chat` | 对外可用性、Agent 编排耗时、返回正确性、异常输入处理 |
| 失物服务 `item-service` | Docker Compose 内部服务，端口 `8001` 仅内部暴露 | `GET /healthz`、`GET /items`、`GET /items/{item_id}`、`POST /items/{item_id}/match` | 公开查询、证据核验、404 控制、隐藏特征保护 |
| 认领服务 `claim-service` | Docker Compose 内部服务，端口 `8002` 仅内部暴露 | `GET /healthz`、`POST /claims`、`GET /claims/{claim_id}`、`POST /approve`、`POST /manual-review`、`POST /request-evidence` | 认领单创建、状态变更、越权拒绝、重复认领处理 |
| 交接服务 `handover-service` | Docker Compose 内部服务，端口 `8003` 仅内部暴露 | `GET /healthz`、`GET /slots`、`POST /appointments`、`GET /appointments/{claim_id}` | 时段查询、预约创建、未审核拒绝、重复预约处理 |
| OpenAI 兼容大模型 API | 外部 API 或本地 MockLLM | `chat.completions.create()` 兼容接口 | 意图识别、RAG 问答、摘要和评测稳定性；离线模式下监控 MockLLM |
| RAG 政策检索接口 | 本地模块/API 工具 | `search_policy`、`retrieve`、`retrieve_scored` | 政策召回率、复合问题覆盖率、检索耗时 |

## 4.2 监控工具及应用方法

原始监控方式主要依赖人工执行命令和截图，能够证明系统可运行，但不利于连续比较不同版本的服务质量。优化后采用“分层采集、统一记录、按 SLA 指标评价”的方式，把监控过程拆成资源层、健康层、接口层、业务层和外部依赖层五类数据。

优化后的监控闭环如下：

```text
启动部署
  → 容器资源监控：CPU、内存、网络 I/O、重启状态
  → 健康检查监控：/healthz、Compose healthy、端口暴露
  → 接口性能监控：响应时间、状态码、成功率、错误率
  → 业务质量监控：Agent 评测通过率、BPMN 分支正确性、护栏拦截
  → 外部依赖监控：OpenAI 兼容 API 或 MockLLM 的延迟、失败率
  → 汇总 SLA 指标：效率、可用性、健壮性、吞吐率
```

这种方式比单纯截图更完整：资源数据说明服务是否稳定运行，健康检查说明服务是否可访问，接口数据说明请求是否及时完成，业务评测说明 Agent 和流程是否正确，外部依赖监控说明大模型 API 是否影响整体质量。

### 4.2.1 优化后的分层监控方案

| 监控层次 | 监控对象 | 关键指标 | 工具或命令 | 截图位置 |
|---|---|---|---|---|
| 资源层 | 四个 Docker 容器 | CPU、内存、网络 I/O、块 I/O、容器重启 | `docker stats --no-stream`、Docker Desktop | Docker Desktop 资源界面或终端输出 |
| 健康层 | `web-agent`、三个内部微服务 | `healthy` 状态、`/healthz` 成功率、端口暴露情况 | `docker compose ps`、`scripts/Test-Compose.ps1` | Compose 服务列表和烟测结果 |
| 接口层 | `/api/chat`、`/items`、`/claims`、`/slots` 等接口 | HTTP 状态码、平均响应时间、最大响应时间、错误率 | `curl.exe -w`、PowerShell 连续调用脚本 | 单接口响应时间和吞吐率结果 |
| 业务层 | Agent、BPMN、RAG、护栏 | 评测通过率、BPMN 路径正确率、越权/注入拦截率 | `python -X utf8 -B evaluate.py`、`unittest` | 评测通过率和测试结果 |
| 依赖层 | OpenAI 兼容 API 或 MockLLM | LLM 请求耗时、超时次数、失败率、回退状态 | `/api/chat` latency、模型调用日志 | 真实 API 模式下的调用日志或控制台输出 |

监控数据建议按一次评价周期统一记录，周期可以是“每次部署后”或“每次实验演示前”。每次记录至少包含：

| 记录项 | 建议内容 |
|---|---|
| 版本信息 | Git commit SHA、镜像 tag、`IMAGE_TAG` |
| 部署状态 | 四个容器是否 healthy，是否只有 `web-agent` 暴露宿主机端口 |
| 资源数据 | 每个容器 CPU、内存、网络 I/O |
| 接口数据 | 核心接口响应时间、成功数、失败数、TPS |
| 业务数据 | `evaluate.py` 通过率、单元测试通过数 |
| 异常数据 | 404、403、409、非法 JSON、提示注入、越权访问的处理结果 |

为了减少人工复制命令造成的数据遗漏，项目新增轻量监控采集脚本 `scripts/Monitor-Services.ps1`。该脚本会统一采集 Web 健康检查、Compose 容器健康、`/api/chat` 多次调用延迟、吞吐率，并可选采集 Docker 资源数据，最后输出 JSON 文件。

```powershell
pwsh -NoProfile -File scripts/Monitor-Services.ps1 `
    -SampleCount 50 `
    -IncludeDockerStats `
    -OutputPath metrics/service-monitoring.json
```

输出文件包含以下主要字段：

| 字段 | 含义 |
|---|---|
| `HealthChecks` | `web-agent` 的 `/healthz` 状态、HTTP 状态码和响应时间 |
| `ComposeHealth` | 四个 Compose 服务的容器 ID 和 health 状态 |
| `ChatSamples` | 多次 `/api/chat` 请求的状态码、成功标记和 `LatencyMs` |
| `Throughput` | 总请求数、成功数、失败数、总耗时、每秒请求数和成功率 |
| `DockerStats` | 启用 `-IncludeDockerStats` 后记录的 CPU、内存、网络 I/O 等容器资源数据 |

截图建议增加一张“图 4-0 统一监控采集结果”，内容为 `metrics/service-monitoring.json` 或脚本终端输出中的 `Throughput`、`ComposeHealth` 和 `DockerStats`。后续服务质量评价表优先引用该 JSON 数据；Docker Desktop 和浏览器截图作为可视化补充证据。

### 4.2.2 容器与资源监控

Docker Compose 用于部署四个服务。`compose.yaml` 中为每个服务设置了资源上限：

```yaml
cpus: 0.50
mem_limit: 512m
```

启动服务后使用以下命令查看容器状态和资源消耗：

```powershell
$env:IMAGE_TAG = 'dev'
docker compose -p lost-found -f compose.yaml up -d --build --wait
docker compose -p lost-found -f compose.yaml ps
docker stats --no-stream
docker compose -p lost-found -f compose.yaml logs --tail 200
```

截图建议：

- 图 4-1：`docker compose ps`，展示四个服务均为 `healthy`。
- 图 4-2：`docker stats --no-stream`，展示 CPU、内存、网络 I/O 和块 I/O。
- 图 4-3：Docker Desktop 容器列表或资源曲线界面。

资源参数记录表如下：

| 指标 | 获取方式 | 说明 |
|---|---|---|
| CPU 使用率 | `docker stats --no-stream` 的 `CPU %` | 判断服务是否存在异常高负载 |
| 内存占用 | `docker stats --no-stream` 的 `MEM USAGE / LIMIT` | 对比 `512m` 容器限制，判断是否接近资源上限 |
| 网络 I/O | `docker stats --no-stream` 的 `NET I/O` | 反映服务间调用和 Web 请求流量 |
| 进程健康状态 | `docker compose ps`、容器 healthcheck | 判断服务是否持续存活 |
| 日志错误 | `docker compose logs --tail 200` | 观察异常栈、HTTP 错误和重启情况 |

### 4.2.3 健康检查与接口烟测

四个服务均提供 `/healthz`。Compose 健康检查配置为每 10 秒检查一次，超时 3 秒，最多重试 6 次。对外服务 `web-agent` 的健康检查地址为：

```text
http://localhost:8000/healthz
```

项目已有烟测脚本：

```powershell
pwsh -NoProfile -File scripts/Test-Compose.ps1
```

该脚本会自动检查：

1. 四个 Compose 服务都有运行中的容器。
2. 四个容器健康状态均为 `healthy`。
3. `item-service`、`claim-service`、`handover-service` 未暴露宿主机端口。
4. `GET /healthz` 返回 `status=ok`。
5. 首页包含“寻迹校园”。
6. `POST /api/chat` 能返回候选失物 `LF2026001`。

截图建议：

- 图 4-4：`scripts/Test-Compose.ps1` 输出 `Compose smoke tests: PASS`。
- 图 4-5：浏览器访问 `http://localhost:8000/healthz` 返回 `{"status":"ok"}`。

### 4.2.4 调用参数和时间参数监控

`/api/chat` 的响应中包含应用层 `latency` 字段，来源于 `app.py` 中的 `time.perf_counter()`，用于记录一次用户请求从进入护栏到完成 Agent/BPMN 编排的耗时。

离线评测命令：

```powershell
python -X utf8 -B evaluate.py
```

结构化提取延迟：

```powershell
python -X utf8 -B -c "from evaluate import run_eval; rows, rate = run_eval(verbose=False); print('pass_rate', rate); print('avg_latency', round(sum(r['latency'] for r in rows)/len(rows), 3)); print('max_latency', max(r['latency'] for r in rows)); [print(r['name'], r['latency'], r['pass']) for r in rows]"
```

本次本地离线监控结果如下：

| 场景 | latency/s | 是否通过 |
|---|---:|---|
| 寻物 | 0.054 | 是 |
| 复合政策 | 0.000 | 是 |
| 普通认领 | 0.106 | 是 |
| 高价值认领 | 0.046 | 是 |
| 证据不足 | 0.066 | 是 |
| 提示注入 | 0.000 | 是 |
| 越权 | 0.000 | 是 |
| PII 脱敏 | 0.000 | 是 |
| 平均值 | 0.034 | 8/8 |
| 最大值 | 0.106 | 8/8 |

普通认领场景耗时最高，原因是该请求会触发 BPMN 流程，并依次调用失物、认领和交接三个微服务；提示注入、越权和 PII 脱敏在护栏层短路处理，因此耗时接近 0。

### 4.2.5 吞吐率测试

吞吐率使用单位时间内成功完成的请求数量评价：

```text
吞吐率 TPS = 成功请求数 / 测试总耗时
成功率 = 成功请求数 / 总请求数 × 100%
错误率 = 失败请求数 / 总请求数 × 100%
```

对 `web-agent` 可使用 PowerShell 连续调用 `/api/chat`：

```powershell
$N = 50
$Ok = 0
$Body = @{ user_id = "u001"; message = "帮我找图书馆发现的黑色耳机" } | ConvertTo-Json -Compress
$Sw = [Diagnostics.Stopwatch]::StartNew()
1..$N | ForEach-Object {
    try {
        $R = Invoke-RestMethod -Uri "http://localhost:8000/api/chat" `
            -Method Post `
            -Body $Body `
            -ContentType "application/json; charset=utf-8" `
            -TimeoutSec 10
        if ($R.reply -like "*LF2026001*") { $Ok++ }
    } catch {
    }
}
$Sw.Stop()
[pscustomobject]@{
    Total = $N
    Success = $Ok
    Seconds = [math]::Round($Sw.Elapsed.TotalSeconds, 3)
    TPS = [math]::Round($Ok / $Sw.Elapsed.TotalSeconds, 2)
    SuccessRate = [math]::Round($Ok / $N * 100, 2)
}
```

对三个内部微服务，可在本机开发模式下分别启动服务并使用 `curl.exe` 或单元测试测量接口；在 Compose 模式下，业务服务不暴露宿主机端口，可通过 `web-agent` 间接触发，或进入容器内部访问内部 DNS 名称。

示例：

```powershell
curl.exe -w "time_total=%{time_total}`n" "http://localhost:8001/items?keyword=耳机&location=图书馆"
curl.exe -w "time_total=%{time_total}`n" "http://localhost:8002/healthz"
curl.exe -w "time_total=%{time_total}`n" "http://localhost:8003/slots?item_id=LF2026001"
```

截图建议：

- 图 4-6：PowerShell 吞吐率脚本输出。
- 图 4-7：`curl.exe -w` 输出单接口响应时间。
- 图 4-8：Web 页面一次 `/api/chat` 响应中展示的 latency。

## 4.3 服务质量评价方法

本报告参考 SLA 评价思路，将服务质量分为效率、可用性、健壮性和吞吐率四类指标。评价对象包括每个微服务和外部/API 服务接口。

| 质量指标 | 计算方法 | 数据来源 | 评价含义 |
|---|---|---|---|
| 效率 | 平均响应时间、最大响应时间、P95 响应时间 | `/api/chat` latency、`curl.exe -w`、PowerShell 计时 | 判断服务处理请求是否及时 |
| 可用性 | `可用性 = 成功健康检查次数 / 总健康检查次数 × 100%` | `/healthz`、`docker compose ps`、`Test-Compose.ps1` | 判断服务是否可访问、是否处于 healthy 状态 |
| 健壮性 | `健壮性 = 异常场景通过数 / 异常场景总数 × 100%` | 单元测试、评测集、错误请求测试 | 判断服务对非法输入、越权、重复请求和依赖异常的处理能力 |
| 吞吐率 | `TPS = 成功请求数 / 测试总耗时` | PowerShell 连续调用脚本、接口压测 | 判断服务单位时间处理能力 |
| 正确性 | `正确率 = 评测通过数 / 评测总数 × 100%` | `evaluate.py`、LLM-as-judge | 判断 Agent 回复和流程结果是否覆盖关键要点 |
| 资源稳定性 | CPU、内存是否低于资源上限 | `docker stats` | 判断服务是否在资源限制内稳定运行 |

结合课程原型特点，本项目采用以下评价等级：

| 等级 | 判定标准 |
|---|---|
| 优 | 健康检查通过率 100%，核心评测通过率 ≥ 95%，异常测试全部通过，平均响应时间低于 1 秒，资源使用未接近上限 |
| 良 | 健康检查通过率 ≥ 99%，核心评测通过率 ≥ 90%，主要异常测试通过，平均响应时间低于 3 秒 |
| 中 | 健康检查通过率 ≥ 95%，核心评测通过率 ≥ 80%，存在少量可恢复异常 |
| 差 | 健康检查、核心评测或异常处理存在明显失败，影响基本使用 |

如果接入真实大模型 API，响应时间会受到外部模型和网络影响，应单独记录 LLM API 的请求耗时、失败率和超时次数，不应与离线 MockLLM 结果混为同一组指标。

## 4.4 本次监控与测试结果

在 Windows 本地环境中顺序运行自动化测试和离线评测，得到以下结果：

| 监控/测试项目 | 命令 | 结果 |
|---|---|---|
| 自动化测试 | `python -B -m unittest discover -s tests -v` | 71 项测试全部通过，用时 18.308 秒 |
| Python 编译检查 | `python -B -m compileall -q .` | 退出码 0 |
| 离线业务评测 | `python -X utf8 -B evaluate.py` | 8/8 通过，通过率 100% |
| 应用层平均延迟 | `run_eval(verbose=False)` | 0.034 秒 |
| 应用层最大延迟 | `run_eval(verbose=False)` | 0.106 秒 |
| Compose 健康检查配置 | `compose.yaml` | 四个服务均配置 `/healthz`，间隔 10 秒、超时 3 秒、重试 6 次 |
| 容器资源限制 | `compose.yaml` | 每个服务限制 `0.50 CPU`、`512m` 内存 |

自动化测试覆盖了 200、400、403、404、409 等响应路径，包含提示注入拦截、越权拦截、PII 脱敏、服务不可用降级、BPMN 三条分支路径和三个微服务的 HTTP 契约。因此，测试结果可以作为健壮性和接口正确性的主要证据。

## 4.5 分服务质量评价

### 4.5.1 Web/Agent 服务

| 指标 | 监控或测试结果 | 评价 |
|---|---|---|
| 效率 | 离线评测平均 latency 为 0.034 秒，最大 latency 为 0.106 秒 | 离线 MockLLM 模式下效率高；普通认领链路最长但仍低于 1 秒 |
| 可用性 | `/healthz` 返回 `status=ok`，Compose healthcheck 可持续检查 | 具备基础健康检查能力 |
| 健壮性 | 空消息、非法 JSON、未知 API 返回受控错误；提示注入和越权请求被拦截 | 健壮性较好，异常不会导致服务崩溃 |
| 吞吐率 | 可通过 PowerShell 连续调用 `/api/chat` 计算 TPS | 适合轻量并发演示；真实并发能力受 Python 标准库 HTTP 服务和 LLM 后端限制 |
| 正确性 | 8 个评测场景全部通过 | Agent 路由、RAG、BPMN 和护栏输出正确 |

综合评价：Web/Agent 服务达到“优”。在离线教学模式下响应速度快、正确率高、异常输入有明确拦截。若接入真实大模型，应继续监控外部 API 延迟和超时率。

### 4.5.2 失物服务

| 指标 | 监控或测试结果 | 评价 |
|---|---|---|
| 效率 | 查询接口为内存数据检索，响应时间可用 `curl.exe -w time_total` 测量 | 结构简单，预期延迟低 |
| 可用性 | 提供 `GET /healthz`，Compose 内部健康检查覆盖 | 具备可用性监控点 |
| 健壮性 | 测试覆盖公开详情、未知失物 404、搜索过滤、证据评分 | 能处理正常查询和不存在资源 |
| 安全性 | 公开接口不返回 `secret_features` 或 `secret_keywords` | 隐私保护符合业务要求 |
| 吞吐率 | 可对 `GET /items` 连续调用测量 TPS | 读接口适合较高吞吐；写入或持久化不是当前范围 |

综合评价：失物服务达到“优”。其核心风险不是性能，而是隐藏特征泄漏；当前测试已验证公开接口不会泄漏隐藏字段。

### 4.5.3 认领服务

| 指标 | 监控或测试结果 | 评价 |
|---|---|---|
| 效率 | 认领单创建和状态更新使用内存字典，接口处理轻量 | 在原型规模下效率较高 |
| 可用性 | 提供 `GET /healthz`，被 `handover-service` 依赖 | 是交接服务的关键依赖 |
| 健壮性 | 测试覆盖创建、查询、授权、重复认领 409、状态接口非法输入 | 异常路径覆盖充分 |
| 安全性 | 查询认领单时校验 `user_id`，越权返回 403 | 权限控制有效 |
| 吞吐率 | 可通过重复创建不同用户/物品认领单或查询已有认领单测量 | 状态写入接口需注意测试数据隔离 |

综合评价：认领服务达到“优”。它承担认领状态机和授权校验，当前 403、404、409 等错误路径均有测试保障。

### 4.5.4 交接服务

| 指标 | 监控或测试结果 | 评价 |
|---|---|---|
| 效率 | 交接时段查询为内存读取，预约创建会调用认领服务校验状态 | 查询效率高，创建预约受认领服务可用性影响 |
| 可用性 | 提供 `GET /healthz`，Compose 中依赖 `claim-service` healthy 后启动 | 具备依赖顺序控制 |
| 健壮性 | 测试覆盖可用时段、重复预约、未知时段、未审批认领单、缺失预约 | 异常处理较完整 |
| 安全性 | 创建预约前检查认领单归属和审核状态 | 能防止未通过认领直接预约 |
| 吞吐率 | 可对 `GET /slots` 连续调用测量 TPS，对 `POST /appointments` 使用不同 claim 数据测量 | 读接口吞吐较高，写接口受业务约束 |

综合评价：交接服务达到“良到优”。其质量依赖认领服务，因此需要在部署监控中同时关注两个服务的健康状态和调用错误。

### 4.5.5 OpenAI 兼容大模型 API 与 RAG 接口

| 指标 | 监控或测试结果 | 评价 |
|---|---|---|
| 效率 | 本次使用 MockLLM，平均应用层延迟 0.034 秒 | 离线模式效率高；真实模型需单独监控网络耗时 |
| 可用性 | 未配置 API Key 时自动回退 MockLLM | 能保证教学演示不中断 |
| 健壮性 | Judge 解析失败时返回不通过，不会中断评测流程 | 评测流程可控 |
| 正确性 | `POLICY_K=2` 时 8/8 评测通过，复合政策问题可同时覆盖人工复核和 3 日交接 | RAG 参数设置有效 |
| 风险 | 外部模型服务可能出现限流、超时或响应格式变化 | 生产环境需增加外部 API 超时率和重试监控 |

综合评价：离线模式下该接口达到“优”。真实 API 模式下需要把外部模型可用性、平均响应时间和失败率纳入 SLA。

## 4.6 总体评价与改进建议

从本次监控和测试结果看，系统在教学原型范围内服务质量较好：

1. **效率**：离线评测平均响应时间为 0.034 秒，最大响应时间为 0.106 秒。BPMN 串联三项微服务的普通认领链路耗时最高，但仍处于较低水平。
2. **可用性**：四个服务均设计了 `/healthz`，Compose 会按健康状态控制依赖启动，`Test-Compose.ps1` 能对部署结果进行端到端烟测。
3. **健壮性**：71 项自动化测试全部通过，覆盖非法 JSON、空消息、404、403、409、越权、提示注入、服务不可用和 BPMN 异常分支。
4. **吞吐率**：当前系统适合课程演示和轻量并发访问。由于使用 Python 标准库 HTTP 服务、进程内存数据和可选外部 LLM，生产吞吐能力还需要在真实部署环境中通过持续压测确定。
5. **资源控制**：Compose 为每个容器设置了 CPU 和内存上限，并通过只读文件系统、内部网络和最小宿主机端口暴露降低运行风险。

需要改进的方面：

- 增加 Prometheus 或 OpenTelemetry 指标导出，持续记录请求数、错误数、P95/P99 延迟和依赖调用耗时。
- 将运行期业务数据迁移到数据库，避免容器重启后认领单和预约数据丢失。
- 对真实 OpenAI 兼容 API 增加超时、重试、熔断和配额监控。
- 在 GitHub Actions 部署后保存 smoke test、`docker stats` 和评测结果，形成可追溯的服务质量记录。
- 增加并发压测场景，区分读接口、写接口和完整 Agent/BPMN 链路的吞吐能力。

综上，本系统已经具备基本 SLA 监控和评价条件：通过健康检查评价可用性，通过接口和异常测试评价健壮性，通过 latency 和压测评价效率与吞吐率，通过 Docker 资源监控评价资源稳定性。当前本地离线结果表明系统核心质量指标达到课程原型的“优”等级；若用于真实校园场景，还需要补充持续监控、持久化存储和真实外部 API 的 SLA 跟踪。
