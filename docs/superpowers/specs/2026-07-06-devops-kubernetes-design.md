# 基于 GitHub Actions 与 Kubernetes 的 DevOps 自动化设计

## 1. 目标

为现有“寻迹校园”Agent 失物招领系统建立可重复、可验证、可回滚的 DevOps 流程，覆盖代码拉取、自动测试、容器构建、镜像发布、Kubernetes 部署和部署后验证。

目标环境是本地 Minikube 集群。CI/CD 使用 GitHub Actions，镜像存储在 GitHub Container Registry（GHCR），部署任务由 Minikube 所在机器上的 GitHub Actions self-hosted runner 执行。

## 2. 当前状态与边界

当前仓库是 Python 单仓库，包含 Web/Agent 入口和三个通过 HTTP/JSON 通信的业务服务。`server.py` 会在同一进程内启动 Web 服务及三个业务服务线程，不适合 Kubernetes 的独立工作负载模型。仓库目前没有 Dockerfile、Kubernetes 清单或 CI/CD 工作流。

三个业务服务使用 Python 进程内字典保存状态。本次工作保持该实现并将每个服务限制为单副本；Pod 重启后业务状态恢复为初始数据。这是演示环境的明确限制，不在本次范围内引入数据库。

本次不引入 Prometheus、Grafana、ELK、Argo CD、云端集群自动创建或数据库持久化。

## 3. 运行架构

系统部署为四个独立的 Kubernetes Deployment：

所有资源位于 `lost-found` Namespace。非敏感配置存放在 `lost-found-config` ConfigMap，应用密钥存放在 `lost-found-secrets` Secret，GHCR 拉取凭据存放在 `ghcr-pull` Secret。

| 工作负载 | 职责 | 端口 | 访问方式 |
|---|---|---:|---|
| `web-agent` | 静态页面、聊天 API、Agent 与 BPMN 编排 | 8000 | Ingress 对外暴露 |
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

Minikube 启用 ingress addon，通过 Ingress 将 Web 服务暴露为 `lost-found.local`。三个业务 Service 不创建 NodePort 或外部入口。

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
│   ├── ingress.yaml
│   ├── web-agent/
│   ├── item-service/
│   ├── claim-service/
│   ├── handover-service/
│   └── kustomization.yaml
└── overlays/minikube/
    └── kustomization.yaml
```

每个组件包含 Deployment 和 Service。所有 Deployment 使用单副本、RollingUpdate、资源 requests/limits、Pod 和容器级 securityContext，并设置 startup、readiness 与 liveness probes。

四个 HTTP 服务提供 `GET /healthz`。该端点只检查当前进程是否可服务，不依赖下游服务，避免级联故障导致所有 Pod 同时失去就绪状态。端到端依赖关系由部署后冒烟测试验证。

## 6. 配置与密钥

普通配置通过 ConfigMap 注入，包括服务 URL、模型名、基础 URL 和 RAG 检索条数。`OPENAI_API_KEY` 使用 Kubernetes Secret 注入；未配置时继续使用现有离线 mock 模型。

GHCR 默认按私有仓库处理。Minikube 中预先创建 imagePullSecret，并由 Deployment 的 `imagePullSecrets` 引用。仓库只记录创建命令和 Secret 名称，不保存 API Key、GitHub PAT、kubeconfig 或 `.env` 内容。

self-hosted runner 直接使用所在机器的 Minikube kubeconfig。PR 代码不在该 runner 上运行。

## 7. GitHub Actions 流水线

工作流在 pull request 和 `main` 分支推送时触发：

1. GitHub 托管 runner 拉取代码并安装固定 Python 版本。
2. 安装依赖，执行全部 unittest 和 `compileall`。
3. 渲染 Kustomize 清单并执行客户端 dry-run。
4. 对 `main` 推送，在 GitHub 托管 runner 上并行构建四个镜像。
5. 使用 `GITHUB_TOKEN` 登录 GHCR，并以 commit SHA 标签推送镜像。
6. 测试和全部镜像构建成功后，将部署任务交给带 `minikube` 标签的 self-hosted runner。
7. 部署任务写入四个不可变镜像引用并执行 `kubectl apply -k deploy/k8s/overlays/minikube`。
8. 等待四个 Deployment 完成滚动更新，随后执行健康检查和端到端冒烟测试。

部署 job 设置 concurrency group，同一环境只运行一个部署；新提交不会与旧提交并发修改集群。

## 8. 失败处理与回滚

部署开始前，脚本读取并保存当前四个 Deployment 的镜像引用。

若 `kubectl apply`、滚动更新或冒烟测试失败：

- 对已有环境，将四个 Deployment 全部恢复为部署前记录的镜像，并等待回滚完成；
- 对首次部署，因为没有旧版本可恢复，保留失败资源用于诊断；
- 两种情况都输出 Pod 列表、Deployment 状态、相关事件和失败容器日志，并让工作流以失败状态结束。

回滚仅恢复应用镜像。Kustomize 基础资源和 ConfigMap 的不兼容变更必须在 PR 审查和清单验证阶段发现；本次不设计数据库迁移。

## 9. 测试与验收

验证分为四层：

1. **代码层**：运行现有 unittest、健康端点测试和 `compileall`。
2. **容器层**：构建并临时运行四个镜像，验证预期入口、非 root 用户及健康响应。
3. **清单层**：运行 `kubectl kustomize` 和 `kubectl apply --dry-run=client`。
4. **部署层**：等待四个 rollout 成功，通过一次性集群内探针检查四个 `/healthz`，再通过 `lost-found.local` Ingress 调用 `/api/chat`，使用离线 mock 模型完成端到端请求。

完成标准：

- PR 自动执行测试且不能触发本地集群部署；
- `main` 推送可自动生成四个 SHA 标签镜像并发布到 GHCR；
- self-hosted runner 可自动部署到 Minikube；
- Web 页面可访问，Agent 能通过集群内 Service 调用业务服务；
- 部署失败时能恢复旧镜像或输出首次部署诊断信息；
- 仓库中不包含真实密钥。

## 10. 日志与运维文档

应用日志输出到 stdout/stderr，由 Kubernetes 原生日志机制读取。本阶段不部署集中日志和指标平台。

运维手册覆盖：

- Minikube、kubectl 和 ingress addon 初始化；
- GitHub Actions self-hosted runner 注册及 `minikube` 标签配置；
- GHCR imagePullSecret 和可选 LLM Secret 创建；
- 首次部署及 Ingress 本地域名配置；
- 查看 Pod、Deployment、事件和日志；
- 手动执行冒烟测试和镜像回滚；
- 进程内数据在 Pod 重启后丢失的限制。

## 11. 交付物

- 四个组件的容器构建文件及 `.dockerignore`
- Web/Agent 独立生产入口和四个健康端点
- Kustomize base 与 Minikube overlay
- GitHub Actions CI/CD 工作流
- 部署、冒烟测试和回滚脚本
- 自动化测试与运维文档
