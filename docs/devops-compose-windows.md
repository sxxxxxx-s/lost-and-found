# Windows 11 Docker Compose 运维手册

本文档用于在一台本地 Windows 11 机器上运维本项目。部署目标不是 Kubernetes 集群，而是 Docker Desktop + Docker Compose；GitHub Actions 的部署阶段运行在同一台 Windows self-hosted runner 上。

## 1. 本机前置条件

1. 启动 Docker Desktop。
2. 确认使用 Linux containers。
3. 在 PowerShell 中验证：

```powershell
docker info --format '{{.OSType}}'
```

期望输出：

```text
linux
```

部署脚本会在开始前检查 `docker`、`docker compose`、Docker daemon 和 Linux containers 模式。未满足时会直接失败，不会继续构建或替换容器。

## 2. 本地验证与手动运行

在仓库根目录执行：

```powershell
python -B -m unittest discover -s tests -v
python -B -m compileall -q .
docker compose -f compose.yaml config --quiet
```

手动构建和启动四服务栈：

```powershell
$env:IMAGE_TAG = 'dev'
docker compose -p lost-found -f compose.yaml build
docker compose -p lost-found -f compose.yaml up -d --wait --remove-orphans
docker compose -p lost-found -f compose.yaml ps
```

只应发布一个宿主机端口：

```text
127.0.0.1:8000 -> web-agent:8000
```

业务服务 `item-service`、`claim-service`、`handover-service` 只通过 Compose 内部 DNS 访问，不发布到宿主机。

查看 bounded logs：

```powershell
docker compose -p lost-found -f compose.yaml logs --tail 200
```

运行 smoke test：

```powershell
pwsh -NoProfile -File scripts/Test-Compose.ps1
```

停止并删除本地容器：

```powershell
docker compose -p lost-found -f compose.yaml down
```

注意：当前业务数据是进程内存数据。执行 `docker compose down` 删除容器后，下次启动会重置认领单、交接预约等运行期状态。

## 3. GitHub self-hosted runner

在 GitHub 仓库中进入 Settings -> Actions -> Runners：

1. 添加 Windows x64 repository runner。
2. 在 runner labels 中添加自定义标签 `compose-local`。
3. 使用同一个 Windows 用户启动 Docker Desktop 和 runner。
4. 保持 runner 的 `run.cmd` 窗口打开；关闭窗口会停止接收部署任务。

推荐把 runner 目录放在仓库外，或使用已忽略的 `actions-runner/` 目录。不要提交 runner token、`.env`、`*.secret.env` 或任何本地部署密钥。

## 4. GitHub Environment 和主分支保护

在 Settings -> Environments 中创建：

```text
compose-local
```

可选添加 secret：

```text
OPENAI_API_KEY
```

该 secret 只注入 deploy step，不注入 PR 测试和镜像构建 job。

建议保护 `main` 分支，要求以下 GitHub-hosted job 通过后才能合并：

- `test`
- `build`

PR 不会运行 self-hosted Windows runner。只有 push 到 `refs/heads/main` 才会触发部署 job。

## 5. CI/CD 流程

`.github/workflows/ci-cd.yml` 包含三个阶段：

1. `test`：在 Ubuntu runner 上安装依赖、运行 unittest、compileall 和 Compose config 校验。
2. `build`：使用 Buildx 分别构建 `web-agent`、`item-service`、`claim-service`、`handover-service` 四个 Docker target，不推送镜像仓库。
3. `deploy`：仅 main push 时，在 `[self-hosted, Windows, X64, compose-local]` runner 上执行：

```powershell
./scripts/Deploy-Compose.ps1 -Sha '${{ github.sha }}'
```

部署脚本会使用 40 位 commit SHA 作为 `IMAGE_TAG`，本机构建并启动以下镜像：

```text
lost-found/web-agent:<sha>
lost-found/item-service:<sha>
lost-found/claim-service:<sha>
lost-found/handover-service:<sha>
```

## 6. 自动部署策略

`scripts/Deploy-Compose.ps1` 的关键行为：

1. 校验 `Sha` 必须是 40 位小写十六进制。
2. 校验 Docker Desktop Linux engine 可用。
3. 校验 `docker compose config --quiet`。
4. 检查当前已有容器是否完整且四个服务使用同一个 40 位 SHA tag。
5. 使用新 SHA 构建四个 target。
6. `docker compose up -d --wait --remove-orphans`。
7. 调用 `scripts/Test-Compose.ps1` 做烟测。
8. 失败时输出 `ps` 和最近 200 行 logs；如果存在上一个合法 SHA tag，则自动回滚。

脚本不会打印展开后的 Compose 配置，避免把环境变量或 secret 泄漏到日志。

## 7. 健康检查和烟测

四个容器都定义了 `/healthz`：

```text
web-agent        http://127.0.0.1:8000/healthz
item-service     internal http://item-service:8001/healthz
claim-service    internal http://claim-service:8002/healthz
handover-service internal http://handover-service:8003/healthz
```

`scripts/Test-Compose.ps1` 会验证：

- 四个服务都有容器 ID。
- 四个容器健康状态都是 `healthy`。
- 三个业务服务没有宿主机端口映射。
- `GET http://localhost:8000/healthz` 返回 `status=ok`。
- `GET http://localhost:8000/` 返回首页。
- `POST /api/chat` 能返回包含 `LF2026001` 的回复。

## 8. 回滚

查看本机已有镜像 tag：

```powershell
docker image ls lost-found/*
```

回滚到某个已经存在的 40 位 SHA：

```powershell
pwsh -NoProfile -File scripts/Rollback-Compose.ps1 -Sha <40-character-sha>
```

回滚脚本会先检查四个镜像 tag 都存在；任意一个缺失时会失败并保持当前容器不变。镜像存在后才会执行：

```powershell
docker compose -p lost-found -f compose.yaml up -d --no-build --wait --remove-orphans
```

然后重新运行 smoke test。

## 9. 清理旧镜像

只在人工确认旧 tag 既不是当前版本，也不是需要保留的上一个版本后，才显式删除旧镜像。例如：

```powershell
docker image rm lost-found/web-agent:<old-sha>
docker image rm lost-found/item-service:<old-sha>
docker image rm lost-found/claim-service:<old-sha>
docker image rm lost-found/handover-service:<old-sha>
```

不要在部署脚本中自动清理镜像；本机回滚依赖历史 SHA-tagged 镜像仍然存在。

## 10. 当前验收记录

截至 2026-07-07，本地自动化验收记录如下：

- unittest：`D:\py\anaconda\python.exe -B -m unittest discover -s tests -v`，66 项测试通过。
- compileall：`D:\py\anaconda\python.exe -B -m compileall -q .`，退出码 0。
- Compose 静态校验：`docker compose -f compose.yaml config --quiet`，退出码 0。
- Docker CLI：`Docker version 29.4.0, build 9d7ad9f`。
- Docker Compose：`Docker Compose version v5.1.1`。
- Docker daemon / Linux Engine：未运行；`docker info --format '{{.OSType}}'` 无法连接 `dockerDesktopLinuxEngine`。
- PowerShell 7：`pwsh` 当前不在 PATH；GitHub runner 或本机需要安装/配置 PowerShell 7 后再执行 `pwsh -File` 脚本。
- 容器健康输出：未验收，原因是 Docker Desktop Linux Engine 未运行。
- smoke test：未验收，原因是 Docker Desktop Linux Engine 未运行且 `pwsh` 不在 PATH。
- rollback：未验收；需要 Docker Desktop 运行且本机至少存在两个完整的 40 位 SHA 镜像版本。若本机不存在两个版本，不应伪造成功结果。
