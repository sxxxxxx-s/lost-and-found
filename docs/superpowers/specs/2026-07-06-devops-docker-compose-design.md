# Windows 11 Docker Compose DevOps 自动化设计

## 1. 目标

为“寻迹校园”Agent 失物招领系统建立可重复、可验证、可回滚的 DevOps 流程，覆盖代码拉取、自动测试、项目构建、Docker Compose 部署和部署后验证。

目标环境是一台 Windows 11 本地机器。该机器已安装 Docker Desktop 29.4.0 和 Docker Compose 5.1.1，使用 GitHub 托管 runner 完成 CI，并使用同一台 Windows 机器上的 GitHub Actions self-hosted runner 自动部署到 Docker Desktop。

## 2. 当前状态与范围

当前仓库是 Python 单仓库，包含 Web/Agent 入口和三个通过 HTTP/JSON 通信的业务服务。`server.py` 会在同一 Python 进程中启动 Web 服务和三个业务服务线程，尚无 Dockerfile、Compose 文件或 GitHub Actions 工作流。

设计检查时 Docker Desktop 客户端与 Compose 插件已安装，但 Docker daemon 未启动。实施和容器验证前必须由 Windows 用户启动 Docker Desktop，并确认其处于 Linux containers 模式。

三个业务服务使用 Python 进程内字典保存状态。本次每个业务服务只运行一个容器，容器重建后数据恢复为仓库内的初始数据。本次不引入 PostgreSQL、本地文件持久化、Prometheus、Grafana、ELK 或容器镜像仓库。

## 3. Compose 运行架构

Docker Compose 使用固定项目名 `lost-found`，管理四个独立服务：

| Compose 服务 | 职责 | 容器端口 | 宿主机端口 |
|---|---|---:|---:|
| `web-agent` | 静态页面、聊天 API、Agent 与 BPMN 编排 | 8000 | 8000 |
| `item-service` | 失物查询与证据匹配 | 8001 | 不发布 |
| `claim-service` | 认领单创建、查询与状态管理 | 8002 | 不发布 |
| `handover-service` | 交接时段及预约管理 | 8003 | 不发布 |

服务通过 Compose 默认网络和服务名通信：

```text
ITEM_URL=http://item-service:8001
CLAIM_URL=http://claim-service:8002
HANDOVER_URL=http://handover-service:8003
```

`handover-service` 依赖健康的 `claim-service`；`web-agent` 依赖三个健康的业务服务。只有 `web-agent` 发布宿主机端口，浏览器通过 `http://localhost:8000` 访问系统。

## 4. 应用进程边界

新增 Web-only 生产入口，只启动 Web 页面和聊天 API，不在容器中创建业务服务线程。现有 `server.py` 保留为非容器开发入口，继续支持一次启动全部服务。

四个 HTTP 服务都提供 `GET /healthz`，返回 `{"status":"ok"}`。健康端点只检查当前进程，不调用下游服务或读取可变业务数据，避免依赖故障造成级联不健康。跨服务通信由部署后的端到端测试验证。

## 5. 容器构建

仓库根目录使用一个多阶段 Dockerfile，包含以下目标：

- `base`：固定的 Python 3.12 slim 基础镜像、依赖和非 root 用户
- `web-agent`
- `item-service`
- `claim-service`
- `handover-service`

每个 Compose 服务选择对应 target，并生成独立本地镜像：

```text
lost-found/web-agent:${IMAGE_TAG}
lost-found/item-service:${IMAGE_TAG}
lost-found/claim-service:${IMAGE_TAG}
lost-found/handover-service:${IMAGE_TAG}
```

手动开发默认 `IMAGE_TAG=dev`；CI/CD 部署使用完整的 40 位 Git commit SHA。基础镜像在 Dockerfile 中记录不可变 digest。

容器统一使用 UID/GID 10001，禁止提权，移除 Linux capabilities，根文件系统只读，并将 `/tmp` 挂载为 tmpfs。每个服务设置健康检查、CPU/内存限制和 `restart: unless-stopped`。

`.dockerignore` 排除 `.git`、`.env`、测试缓存、Python 缓存、报告和不参与运行的文档，避免密钥及无关内容进入构建上下文。

## 6. Compose 配置与密钥

`compose.yaml` 定义服务、网络、构建目标、健康检查、资源限制和启动依赖。普通配置通过 Compose environment 注入，包括服务 URL、`OPENAI_BASE_URL`、`CHAT_MODEL` 和 `POLICY_K`。

`OPENAI_API_KEY` 有两种来源：

- 本地手动部署：仓库中已忽略的 `.env`
- GitHub Actions 自动部署：在名为 `compose-local` 的 GitHub Environment 中创建 `OPENAI_API_KEY` Secret，并将其作为部署步骤环境变量传给 Compose

未配置 API Key 时继续使用现有 `mock-llm`。真实密钥不得写入 Compose 文件、Dockerfile、镜像层、测试输出或日志。部署脚本只执行 `docker compose config --quiet`，不打印解析后的完整配置。

## 7. GitHub Actions 流水线

一个工作流处理 pull request 和 `main` 推送。

### 7.1 GitHub 托管 runner

GitHub 托管的 Linux runner 执行：

1. 使用 checkout 拉取准确提交。
2. 配置 Python 3.12 并安装依赖。
3. 运行全部 unittest 和 `compileall`。
4. 执行 `docker compose config --quiet`。
5. 使用 Buildx 构建四个 Docker target，但不推送镜像。

这些步骤在 PR 和 `main` 上都执行，保证代码、Dockerfile 和 Compose 配置同时经过验证。

### 7.2 Windows self-hosted runner

部署 job 只在 `main` 推送且托管 runner 全部通过后执行。它使用标签 `self-hosted`、`Windows`、`X64` 和 `compose-local`，通过 PowerShell 7：

1. checkout 已验证的同一提交。
2. 检查 Docker Desktop daemon、Linux containers 模式和 Compose 版本。
3. 使用 Git commit SHA 在本机重新构建四个镜像。
4. 执行 Compose 更新、等待健康并运行冒烟测试。

部署 job 设置固定 concurrency group，`cancel-in-progress: false`，确保同一机器上只进行一个部署。PR job 不得使用 self-hosted runner，避免未经合并的代码在本机执行。

self-hosted runner 以当前 Windows 登录用户交互运行，继承该用户的 Docker Desktop named pipe 权限。课程演示阶段不将 runner 注册成 Windows 服务。

## 8. 部署、诊断与回滚

`Deploy-Compose.ps1` 使用固定 Compose 项目名 `lost-found`，执行以下流程：

1. 验证 Docker、Compose 和仓库状态。
2. 从当前 `web-agent` 容器的镜像引用读取旧 SHA；若四个服务存在但镜像 SHA 不一致，则中止并输出诊断。
3. 以新 SHA 执行四目标构建。
4. 设置 `IMAGE_TAG` 为新 SHA，执行 `docker compose up -d --wait --remove-orphans`。
5. 检查四个容器健康状态，并通过 `localhost:8000/api/chat` 完成端到端冒烟测试。

若更新或冒烟测试失败：

- 输出 `docker compose ps`、四个服务的健康状态及有界日志；
- 已有一致旧 SHA 时，使用旧 SHA 和 `--no-build` 恢复四个容器，并再次等待健康；
- 首次部署没有旧版本时保留失败现场；
- 两种情况都让工作流以失败状态结束。

自动回滚只恢复应用镜像。Compose 结构变化由 PR 审查、配置校验和构建验证控制。需要恢复 Compose 文件本身时，运维人员回退 Git 提交后重新运行部署。

`Rollback-Compose.ps1` 接收一个已存在于本机的 40 位 commit SHA，验证四个镜像都存在后执行 `docker compose up -d --no-build --wait`。旧镜像不会在自动部署结束时立即删除，以保留至少一个可回滚版本；镜像清理由运维手册提供显式命令，不在流水线中自动执行破坏性清理。

## 9. 测试与验收

验证分为四层：

1. **代码层**：现有 unittest、健康端点测试、Web-only 进程测试和 `compileall`。
2. **构建层**：四个 Docker target 均可构建，镜像用户为 10001，容器健康检查通过。
3. **配置层**：`docker compose config --quiet` 成功；只有 `web-agent` 发布端口；内部 URL 使用 Compose 服务名。
4. **部署层**：四个容器为 healthy；三个业务端口无法从宿主机直接访问；首页、`/healthz` 和 `/api/chat` 正常；失败部署可以恢复旧 SHA。

完成标准：

- PR 自动执行代码、Compose 和镜像构建验证，不触发本机部署；
- `main` 通过后可在 Windows self-hosted runner 上自动构建并部署；
- `http://localhost:8000` 可访问，Agent 可通过内部 DNS 调用三个业务服务；
- 部署失败能恢复旧镜像或输出首次部署诊断；
- 仓库和镜像中不包含真实密钥；
- README 和运维手册明确数据随容器重建而重置。

## 10. 日志与运维

应用继续将日志输出到 stdout/stderr，通过以下方式查看：

```powershell
docker compose -p lost-found ps
docker compose -p lost-found logs --tail 200 web-agent
docker compose -p lost-found logs --tail 200 item-service claim-service handover-service
```

仓库提供三个 PowerShell 脚本：

- `Deploy-Compose.ps1`：预检、构建、部署、验证、失败回滚
- `Rollback-Compose.ps1`：按本地 Git SHA 手动回滚
- `Test-Compose.ps1`：健康和端到端冒烟测试

运维文档覆盖 Docker Desktop 启动与 Linux containers 检查、self-hosted runner 注册、`compose-local` Environment Secret、部署触发、手动启动/停止、日志、状态检查、回滚和本地镜像清理。

## 11. 交付物

- Web-only 入口及四个 `/healthz` 端点
- 单个多阶段 Dockerfile 和 `.dockerignore`
- 四服务 `compose.yaml`
- GitHub Actions CI/CD 工作流
- Windows 部署、验证和回滚脚本
- 自动化测试、README 更新和 Windows 运维手册
