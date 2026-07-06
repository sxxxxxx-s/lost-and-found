# 基于 GitHub Actions 与 Kubernetes 的 DevOps 自动化设计

## 1. 目标

为现有“寻迹校园”Agent 失物招领系统建立可重复、可验证、可回滚的 DevOps 流程，覆盖代码拉取、自动测试、容器构建、镜像发布、Kubernetes 部署和部署后验证。

目标环境是一台 Windows 10/11 x64 本地机器，其上运行 Docker Desktop（Linux 容器模式）、Minikube 和 GitHub Actions self-hosted runner。CI/CD 使用 GitHub Actions，镜像存储在 GitHub Container Registry（GHCR）；GitHub 托管的 Linux runner 负责测试和镜像构建，本机 Windows runner 只负责部署到本机 Minikube。

## 2. 当前状态与边界

当前仓库是 Python 单仓库，包含 Web/Agent 入口和三个通过 HTTP/JSON 通信的业务服务。`server.py` 会在同一进程内启动 Web 服务及三个业务服务线程，不适合 Kubernetes 的独立工作负载模型。仓库目前没有 Dockerfile、Kubernetes 清单或 CI/CD 工作流。

设计时检测到本机已安装 Docker Desktop 29.4.0 和 kubectl 1.34.1，但 Docker Desktop daemon 未启动，Minikube 尚未安装。实施前必须启动 Docker Desktop、确认 `docker info` 返回 `OSType=linux`，并安装 Minikube。该前置步骤记录在运维手册中，不由 CI 工作流静默安装系统软件。

三个业务服务使用 Python 进程内字典保存状态。本次工作保持该实现并将每个服务限制为单副本；Pod 重启后业务状态恢复为初始数据。这是演示环境的明确限制，不在本次范围内引入数据库。

本次不引入 Prometheus、Grafana、ELK、Argo CD、云端集群自动创建或数据库持久化。

## 3. 运行架构

系统部署为四个独立的 Kubernetes Deployment：

所有资源位于 `lost-found` Namespace。非敏感配置存放在 `lost-found-config` ConfigMap，应用密钥存放在 `lost-found-secrets` Secret，GHCR 拉取凭据存放在 `ghcr-pull` Secret。

| 工作负载 | 职责 | 端口 | 访问方式 |
|---|---|---:|---|
| `web-agent` | 静态页面、聊天 API、Agent 与 BPMN 编排 | 8000 | Windows Minikube overlay 使用 NodePort |
| `item-service` | 失物查询与证据匹配 | 8001 | ClusterIP，仅集群内部 |
| `claim-service` | 认领单创建、查询与状态管理 | 8002 | ClusterIP，仅集群内部 |
| `handover-service` | 交接时段及预约管理 | 8003 | ClusterIP，仅集群内部 |

`web-agent` 通过 Kubernetes Service DNS 调用三个业务服务；`handover-service` 通过 Service DNS 调用 `claim-service`。非敏感地址由 ConfigMap 注入：

```text
ITEM_URL=http://item-service:8001
CLAIM_URL=http://claim-service:8002
HANDOVER_URL=http://handover-service:8003
```

`server.py` 的职责将被拆分：保留本地一键启动能力，同时增加只启动 Web/Agent 的生产入口，避免网关 Pod 在内部创建业务服务线程。

Windows 上的 Minikube 使用 Docker driver。Minikube 官方说明 Docker driver 的 ingress addon 只支持 Linux，因此本设计不创建 Ingress。`overlays/minikube-windows` 将 `web-agent` Service 改为 NodePort；三个业务 Service 保持 ClusterIP，不创建外部入口。

浏览器访问时在独立 PowerShell 窗口运行以下命令，并在使用期间保持该窗口打开：

```powershell
minikube service web-agent --namespace lost-found --url
```

Windows 上 Docker driver 的节点 IP 可能无法从宿主机直接访问，该命令会建立本地隧道并输出实际 URL。自动化部署验证不依赖这个长驻隧道，而是在集群内运行一次性探针。

## 4. 容器设计

四个组件分别构建镜像：

- `lost-found-web-agent`
- `lost-found-item-service`
- `lost-found-claim-service`
- `lost-found-handover-service`

镜像基于 Python 3.12 slim 镜像，最终实现记录基础镜像 digest，按组件复制运行所需文件并安装 `requirements.txt`。容器使用非 root 用户，设置只读根文件系统，移除全部 Linux capabilities，并禁止提权。需要临时写入时只挂载内存型 `/tmp`。

镜像标签使用完整 Git commit SHA：

```text
ghcr.io/${{ github.repository_owner }}/lost-found-web-agent:${{ github.sha }}
ghcr.io/${{ github.repository_owner }}/lost-found-item-service:${{ github.sha }}
ghcr.io/${{ github.repository_owner }}/lost-found-claim-service:${{ github.sha }}
ghcr.io/${{ github.repository_owner }}/lost-found-handover-service:${{ github.sha }}
```

部署不引用 `latest`，保证运行版本可追踪并可精确回滚。

## 5. Kubernetes 配置

Kustomize 目录分为可复用基础层和 Minikube 覆盖层：

```text
deploy/k8s/
├── base/
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── web-agent/
│   ├── item-service/
│   ├── claim-service/
│   ├── handover-service/
│   └── kustomization.yaml
└── overlays/minikube-windows/
    └── kustomization.yaml
```

每个组件包含 Deployment 和 Service。所有 Deployment 使用单副本、RollingUpdate、资源 requests/limits、Pod 和容器级 securityContext，并设置 startup、readiness 与 liveness probes。

四个 HTTP 服务提供 `GET /healthz`。该端点只检查当前进程是否可服务，不依赖下游服务，避免级联故障导致所有 Pod 同时失去就绪状态。端到端依赖关系由部署后冒烟测试验证。

## 6. 配置与密钥

普通配置通过 ConfigMap 注入，包括服务 URL、模型名、基础 URL 和 RAG 检索条数。`OPENAI_API_KEY` 使用 Kubernetes Secret 注入；未配置时继续使用现有离线 mock 模型。

GHCR 默认按私有仓库处理。Minikube 中预先创建 imagePullSecret，并由 Deployment 的 `imagePullSecrets` 引用。仓库只记录创建命令和 Secret 名称，不保存 API Key、GitHub PAT、kubeconfig 或 `.env` 内容。

self-hosted runner 直接使用当前 Windows 用户的 Minikube kubeconfig，并设置 `self-hosted`、`Windows`、`X64` 和 `minikube` 标签。部署 job 使用 `runs-on: [self-hosted, Windows, X64, minikube]` 和 PowerShell 7（`pwsh`）。

课程演示阶段通过 `run.cmd` 在登录用户会话中交互运行 runner，使其继承该用户的 kubeconfig、Minikube 配置和 Docker Desktop 权限。暂不将 runner 安装成 Windows 服务，因为服务账户与交互用户的 kubeconfig、Docker named pipe 权限可能不同。PR 代码不在该 runner 上运行。

## 7. Windows 单机前置条件

本机部署按以下固定方式准备：

1. 启用 Windows 硬件虚拟化并安装 Docker Desktop，切换到 Linux containers。
2. 启动 Docker Desktop，并确认 `docker info --format '{{.OSType}}'` 输出 `linux`。
3. 安装 Minikube，并使用 `minikube start --driver=docker --container-runtime=containerd` 创建集群。
4. 使用 `kubectl cluster-info` 和 `minikube status` 验证集群可用。
5. 以当前 Windows 用户注册仓库级 GitHub Actions runner，增加 `minikube` 自定义标签，并通过 `run.cmd` 保持在线。

部署脚本首先执行 Docker、Minikube、kubectl context 和 Namespace 的预检。任一条件不满足时立即失败并输出修复提示，不尝试在流水线中启动 Docker Desktop GUI 或安装系统软件。

## 8. GitHub Actions 流水线

工作流在 pull request 和 `main` 分支推送时触发：

1. GitHub 托管 runner 拉取代码并安装固定 Python 版本。
2. 安装依赖，执行全部 unittest 和 `compileall`。
3. 渲染 Kustomize 清单并执行客户端 dry-run。
4. 对 `main` 推送，在 GitHub 托管 runner 上并行构建四个镜像。
5. 使用 `GITHUB_TOKEN` 登录 GHCR，并以 commit SHA 标签推送镜像。
6. 测试和全部镜像构建成功后，将部署任务交给带 `Windows`、`X64` 和 `minikube` 标签的 self-hosted runner。
7. Windows 部署任务通过 `pwsh` 写入四个不可变镜像引用并执行 `kubectl apply -k deploy/k8s/overlays/minikube-windows`。
8. 等待四个 Deployment 完成滚动更新，随后执行健康检查和端到端冒烟测试。

部署 job 设置 concurrency group，同一环境只运行一个部署；新提交不会与旧提交并发修改集群。

## 9. 失败处理与回滚

部署开始前，脚本读取并保存当前四个 Deployment 的镜像引用。

若 `kubectl apply`、滚动更新或冒烟测试失败：

- 对已有环境，将四个 Deployment 全部恢复为部署前记录的镜像，并等待回滚完成；
- 对首次部署，因为没有旧版本可恢复，保留失败资源用于诊断；
- 两种情况都输出 Pod 列表、Deployment 状态、相关事件和失败容器日志，并让工作流以失败状态结束。

回滚仅恢复应用镜像。Kustomize 基础资源和 ConfigMap 的不兼容变更必须在 PR 审查和清单验证阶段发现；本次不设计数据库迁移。

## 10. 测试与验收

验证分为四层：

1. **代码层**：运行现有 unittest、健康端点测试和 `compileall`。
2. **容器层**：构建并临时运行四个镜像，验证预期入口、非 root 用户及健康响应。
3. **清单层**：运行 `kubectl kustomize` 和 `kubectl apply --dry-run=client`。
4. **部署层**：等待四个 rollout 成功，通过一次性集群内探针检查四个 `/healthz` 并调用 `/api/chat`，使用离线 mock 模型完成端到端请求。人工验收再通过 `minikube service web-agent --namespace lost-found --url` 打开页面。

完成标准：

- PR 自动执行测试且不能触发本地集群部署；
- `main` 推送可自动生成四个 SHA 标签镜像并发布到 GHCR；
- self-hosted runner 可自动部署到 Minikube；
- Windows 用户可通过 `minikube service` 输出的本地 URL 访问 Web 页面，Agent 能通过集群内 Service 调用业务服务；
- 部署失败时能恢复旧镜像或输出首次部署诊断信息；
- 仓库中不包含真实密钥。

## 11. 日志与运维文档

应用日志输出到 stdout/stderr，由 Kubernetes 原生日志机制读取。本阶段不部署集中日志和指标平台。

运维手册覆盖：

- Windows、Docker Desktop、Minikube 和 kubectl 初始化及前置检查；
- GitHub Actions Windows self-hosted runner 注册、`minikube` 标签配置及 `run.cmd` 启动；
- GHCR imagePullSecret 和可选 LLM Secret 创建；
- 首次部署及 `minikube service` 本地隧道访问；
- 查看 Pod、Deployment、事件和日志；
- 手动执行冒烟测试和镜像回滚；
- 进程内数据在 Pod 重启后丢失的限制。

## 12. 交付物

- 四个组件的容器构建文件及 `.dockerignore`
- Web/Agent 独立生产入口和四个健康端点
- Kustomize base 与 Windows Minikube overlay
- GitHub Actions CI/CD 工作流
- 部署、冒烟测试和回滚脚本
- 自动化测试与运维文档

## 13. 官方依据

- [Minikube Docker driver](https://minikube.sigs.k8s.io/docs/drivers/docker/)：Windows 使用 Linux containers；Docker driver 的 ingress addon 只支持 Linux。
- [Minikube 访问应用](https://minikube.sigs.k8s.io/docs/handbook/accessing/)：Windows Docker driver 网络受限时，通过 `minikube service --url` 建立本地隧道。
- [GitHub self-hosted runner 要求](https://docs.github.com/en/actions/reference/runners/self-hosted-runners)：支持 Windows 10/11 x64，runner 需保持运行并可通过标签路由任务。
