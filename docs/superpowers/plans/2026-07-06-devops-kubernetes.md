# Windows Minikube DevOps Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a GitHub Actions pipeline that tests the repository, publishes four immutable container images to GHCR, and deploys them automatically from a Windows self-hosted runner to a local Minikube cluster with health checks and rollback.

**Architecture:** Keep the monorepo but run `web-agent`, `item-service`, `claim-service`, and `handover-service` as separate single-replica Kubernetes Deployments. GitHub-hosted Linux runners execute CI and image builds; a repository-scoped Windows runner with the `minikube` label performs only trusted `main` deployments through Kustomize-rendered manifests and PowerShell scripts.

**Tech Stack:** Python 3.12, Docker/BuildKit, GitHub Actions, GHCR, Kubernetes, Kustomize through kubectl, Minikube Docker driver, PowerShell 7, unittest.

---

## File Structure

- Create `web_server.py`: Web/Agent-only HTTP process used by Kubernetes.
- Modify `server.py`: preserve local all-in-one startup while delegating Web handling to `web_server.py`.
- Modify `services/item_service.py`, `services/claim_service.py`, `services/handover_service.py`: add local `/healthz` endpoints.
- Modify `tests/test_services.py`, `tests/test_experiment4.py`: verify health contracts and the separated Web process.
- Create `docker/*.Dockerfile` and `.dockerignore`: four non-root, pinned-base images.
- Create `tests/test_devops_assets.py`: static contracts for Docker, Kubernetes, scripts, and workflow assets.
- Create `deploy/k8s/base/**`: Namespace, ConfigMap, four Deployments, four Services, plus a separately applied smoke Job.
- Create `deploy/k8s/overlays/minikube-windows/**`: NodePort overlay for Windows Minikube.
- Create `scripts/Test-DevOpsPrerequisites.ps1`: Windows/Docker/Minikube/kubectl preflight.
- Create `scripts/Deploy-Minikube.ps1`: render, deploy, verify, diagnose, and restore previous images.
- Create `scripts/Rollback-Minikube.ps1`: explicit operator rollback to one commit SHA.
- Create `.github/workflows/ci-cd.yml`: PR CI plus trusted `main` image publication and deployment.
- Create `docs/devops-windows.md`: Windows single-machine setup and operations runbook.
- Modify `.gitignore` and `README.md`: secret exclusions and DevOps usage.

### Task 1: Separate the Web Runtime and Add Health Endpoints

**Files:**
- Create: `web_server.py`
- Modify: `server.py`
- Modify: `services/item_service.py`
- Modify: `services/claim_service.py`
- Modify: `services/handover_service.py`
- Modify: `tests/test_services.py`
- Modify: `tests/test_experiment4.py`

- [ ] **Step 1: Write failing health and runtime-separation tests**

Add this service health contract to `tests/test_services.py`:

```python
class HealthEndpointTests(unittest.TestCase):
    def test_all_business_services_report_local_health(self):
        for handler in (ItemHandler, ClaimHandler, HandoverHandler):
            with self.subTest(handler=handler.__name__):
                with running_server(handler) as base:
                    status, payload = request_json("GET", base + "/healthz")
                self.assertEqual(status, 200)
                self.assertEqual(payload, {"status": "ok"})
```

Change the Web imports in `tests/test_experiment4.py` to import `SESSIONS` and `WebHandler` from `web_server`, keep only `start_business_services` and `stop_servers` from `server`, change `@patch("server.serve_struct")` to `@patch("web_server.serve_struct")`, and add:

```python
class WebRuntimeTests(unittest.TestCase):
    def test_web_health_does_not_start_business_services(self):
        with running_server(WebHandler) as base:
            with urllib.request.urlopen(base + "/healthz", timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 200)
        self.assertEqual(payload, {"status": "ok"})
```

- [ ] **Step 2: Run the focused tests and verify RED**

```powershell
python -B -m unittest tests.test_services.HealthEndpointTests tests.test_experiment4.WebRuntimeTests -v
```

Expected: failure because `/healthz` returns 404 and `web_server.py` does not exist.

- [ ] **Step 3: Implement the Web-only process**

Move `SESSIONS`, `WEB_DIR`, and `WebHandler` from `server.py` into `web_server.py`. Preserve the existing request validation and add the health branch before static-page handling:

```python
def do_GET(self):
    path = self.path.split("?", 1)[0]
    if path == "/healthz":
        return self._send(200, {"status": "ok"})
    if path not in ("/", "/index.html"):
        return self._send(404, {"error": "not found"})
    page_path = os.path.join(WEB_DIR, "index.html")
    if not os.path.isfile(page_path):
        return self._send(404, {"error": "page not found"})
    with open(page_path, "rb") as page:
        self._send(200, page.read(), "text/html; charset=utf-8")

def create_web_server(host="0.0.0.0", port=8000):
    return ThreadingHTTPServer((host, port), WebHandler)

def main():
    port = int(os.getenv("PORT", "8000"))
    server = create_web_server(port=port)
    try:
        print(f"[web-agent] 启动于 http://localhost:{port}")
        server.serve_forever()
    finally:
        server.server_close()
```

Call `main()` only under the module guard. In `server.py`, import `WebHandler` and `create_web_server` from `web_server`; keep business-service startup unchanged and use `create_web_server()` in `main()` so `python server.py` remains the local all-in-one command.

- [ ] **Step 4: Add health handling to all three business services**

At the beginning of each handler's `do_GET`, after parsing the URL, add exactly:

```python
if parsed.path == "/healthz":
    return self._send(200, {"status": "ok"})
```

The endpoint must not query another service or mutable business data.

- [ ] **Step 5: Run focused and full Python tests**

```powershell
python -B -m unittest tests.test_services.HealthEndpointTests tests.test_experiment4.WebRuntimeTests tests.test_experiment4.ServerTests -v
python -B -m unittest discover -s tests -v
python -B -m compileall -q .
```

Expected: all tests pass and compilation exits 0.

- [ ] **Step 6: Commit the runtime boundary**

```powershell
git add web_server.py server.py services/item_service.py services/claim_service.py services/handover_service.py tests/test_services.py tests/test_experiment4.py
git commit -m "feat: separate web runtime and add health checks"
```

### Task 2: Build Four Hardened Container Images

**Files:**
- Create: `.dockerignore`
- Create: `docker/web-agent.Dockerfile`
- Create: `docker/item-service.Dockerfile`
- Create: `docker/claim-service.Dockerfile`
- Create: `docker/handover-service.Dockerfile`
- Create: `tests/test_devops_assets.py`

- [ ] **Step 1: Write failing Docker asset tests**

Create `tests/test_devops_assets.py` with this first contract:

```python
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILES = {
    "web-agent": "web_server.py",
    "item-service": "services/item_service.py",
    "claim-service": "services/claim_service.py",
    "handover-service": "services/handover_service.py",
}

class DockerAssetTests(unittest.TestCase):
    def test_each_component_has_a_pinned_non_root_image(self):
        digest = "sha256:8a7e7cc04fd3e2bd787f7f24e22d5d119aa590d429b50c95dfe12b3abe52f48b"
        for component, entrypoint in DOCKERFILES.items():
            with self.subTest(component=component):
                text = (ROOT / "docker" / f"{component}.Dockerfile").read_text("utf-8")
                self.assertIn(f"python:3.12-slim-bookworm@{digest}", text)
                self.assertIn("USER 10001:10001", text)
                self.assertIn("PYTHONDONTWRITEBYTECODE=1", text)
                self.assertIn("HEALTHCHECK", text)
                self.assertIn(entrypoint, text)

    def test_build_context_excludes_local_secrets_and_caches(self):
        text = (ROOT / ".dockerignore").read_text("utf-8")
        for marker in (".env", ".git", "__pycache__", ".pytest_cache", "docs/"):
            self.assertIn(marker, text)
```

- [ ] **Step 2: Run the Docker asset tests and verify RED**

```powershell
python -B -m unittest tests.test_devops_assets.DockerAssetTests -v
```

Expected: failure because the Docker assets do not exist.

- [ ] **Step 3: Create the shared hardened Dockerfile pattern**

Every Dockerfile must begin with this exact base and runtime setup:

```dockerfile
FROM python:3.12-slim-bookworm@sha256:8a7e7cc04fd3e2bd787f7f24e22d5d119aa590d429b50c95dfe12b3abe52f48b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid 10001 --no-create-home app
COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt
```

Use the following exact component copies, ports, health URLs, and commands:

| Dockerfile | Copies | Port | Command |
|---|---|---:|---|
| `web-agent.Dockerfile` | `*.py`, `flows/`, `web/` | 8000 | `python -B web_server.py` |
| `item-service.Dockerfile` | `data.py`, `services/item_service.py` | 8001 | `python -B services/item_service.py` |
| `claim-service.Dockerfile` | `data.py`, `services/claim_service.py` | 8002 | `python -B services/claim_service.py` |
| `handover-service.Dockerfile` | `data.py`, `services/handover_service.py` | 8003 | `python -B services/handover_service.py` |

End each Dockerfile with its port-specific equivalent of:

```dockerfile
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]
CMD ["python", "-B", "web_server.py"]
```

Create `.dockerignore` with `.git`, `.github`, `.env`, `.env.*`, `!.env.example`, `__pycache__`, `*.py[cod]`, `.pytest_cache`, `docs/`, `tests/`, and `report.md`.

- [ ] **Step 4: Run static tests and build all images**

Start Docker Desktop first, then run:

```powershell
python -B -m unittest tests.test_devops_assets.DockerAssetTests -v
docker build -f docker/web-agent.Dockerfile -t lost-found-web-agent:test .
docker build -f docker/item-service.Dockerfile -t lost-found-item-service:test .
docker build -f docker/claim-service.Dockerfile -t lost-found-claim-service:test .
docker build -f docker/handover-service.Dockerfile -t lost-found-handover-service:test .
```

Expected: tests pass and all four Linux images build successfully.

- [ ] **Step 5: Verify image user and health**

For each image, run it detached on a temporary host port, inspect `.Config.User` and `.State.Health.Status`, then remove the container. The user must be `10001:10001`; health must become `healthy` within 60 seconds.

- [ ] **Step 6: Commit containerization**

```powershell
git add .dockerignore docker tests/test_devops_assets.py
git commit -m "feat: containerize four application components"
```

### Task 3: Define the Kubernetes Base and Windows Overlay

**Files:**
- Create: `deploy/k8s/base/namespace.yaml`
- Create: `deploy/k8s/base/configmap.yaml`
- Create: `deploy/k8s/base/kustomization.yaml`
- Create: `deploy/k8s/base/web-agent/deployment.yaml`
- Create: `deploy/k8s/base/web-agent/service.yaml`
- Create: `deploy/k8s/base/item-service/deployment.yaml`
- Create: `deploy/k8s/base/item-service/service.yaml`
- Create: `deploy/k8s/base/claim-service/deployment.yaml`
- Create: `deploy/k8s/base/claim-service/service.yaml`
- Create: `deploy/k8s/base/handover-service/deployment.yaml`
- Create: `deploy/k8s/base/handover-service/service.yaml`
- Create: `deploy/k8s/base/smoke-job.yaml`
- Create: `deploy/k8s/overlays/minikube-windows/kustomization.yaml`
- Create: `deploy/k8s/overlays/minikube-windows/web-nodeport-patch.yaml`
- Modify: `tests/test_devops_assets.py`

- [ ] **Step 1: Add failing Kubernetes asset contracts**

Add `KubernetesAssetTests` that asserts all listed files exist, the namespace is `lost-found`, only the Windows overlay contains `type: NodePort`, the fixed node port is `30080`, all Deployments contain `runAsNonRoot: true`, `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`, `drop:` plus `- ALL`, all three probe types, resources, and `imagePullSecrets` name `ghcr-pull`.

- [ ] **Step 2: Run the Kubernetes tests and verify RED**

```powershell
python -B -m unittest tests.test_devops_assets.KubernetesAssetTests -v
```

Expected: failure because `deploy/k8s` does not exist.

- [ ] **Step 3: Create Namespace, ConfigMap, and Kustomizations**

Use namespace `lost-found`. The ConfigMap must be named `lost-found-config` and contain exactly these runtime values:

```yaml
ITEM_URL: http://item-service:8001
CLAIM_URL: http://claim-service:8002
HANDOVER_URL: http://handover-service:8003
OPENAI_BASE_URL: https://dashscope.aliyuncs.com/compatible-mode/v1
CHAT_MODEL: mock-llm
POLICY_K: "2"
```

The base kustomization sets `namespace: lost-found` and lists the Namespace, ConfigMap, and four component directories. It intentionally does not list the smoke Job, because a completed Job must be deleted and recreated for every deployment. The Windows overlay references `../../base` and applies `web-nodeport-patch.yaml`, which changes only `web-agent` Service to `type: NodePort` and `nodePort: 30080`.

- [ ] **Step 4: Create four explicit Deployment and Service pairs**

Use this exact mapping; do not expose business services externally:

| Deployment/container | Image token | Port | Config |
|---|---|---:|---|
| `web-agent` | `lost-found-web-agent:dev` | 8000 | ConfigMap plus optional `OPENAI_API_KEY` from `lost-found-secrets` |
| `item-service` | `lost-found-item-service:dev` | 8001 | no environment dependency |
| `claim-service` | `lost-found-claim-service:dev` | 8002 | no environment dependency |
| `handover-service` | `lost-found-handover-service:dev` | 8003 | `CLAIM_URL` from ConfigMap |

Every Deployment uses one replica, RollingUpdate with `maxUnavailable: 0` and `maxSurge: 1`, matching `app.kubernetes.io/name` labels, `imagePullPolicy: IfNotPresent`, `imagePullSecrets: [{name: ghcr-pull}]`, and this container policy:

```yaml
securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
  capabilities:
    drop:
      - ALL
resources:
  requests:
    cpu: 50m
    memory: 64Mi
  limits:
    cpu: 500m
    memory: 512Mi
startupProbe:
  httpGet: {path: /healthz, port: http}
  failureThreshold: 30
  periodSeconds: 2
readinessProbe:
  httpGet: {path: /healthz, port: http}
  periodSeconds: 5
livenessProbe:
  httpGet: {path: /healthz, port: http}
  periodSeconds: 10
```

Set Pod security context to `runAsNonRoot: true` and `seccompProfile.type: RuntimeDefault`. Mount an `emptyDir` with `medium: Memory` at `/tmp`. Each Service selects only its matching label and maps its service port to target port `http`.

- [ ] **Step 5: Create the in-cluster smoke Job**

Create `lost-found-smoke` with `restartPolicy: Never`, `backoffLimit: 0`, `activeDeadlineSeconds: 120`, Python 3.12 Alpine, and a Python command that:

1. GETs all four ClusterIP `/healthz` URLs and asserts `{"status":"ok"}`.
2. POSTs `{"user_id":"u001","message":"帮我找图书馆发现的黑色耳机"}` to `http://web-agent:8000/api/chat`.
3. Asserts HTTP 200 and that the JSON reply contains `LF2026001`.

Apply the same non-root/capability/read-only security policy and mount `/tmp` as memory.

- [ ] **Step 6: Render and validate the overlay**

```powershell
python -B -m unittest tests.test_devops_assets.KubernetesAssetTests -v
kubectl kustomize deploy/k8s/overlays/minikube-windows | Out-File -Encoding utf8NoBOM $env:TEMP\lost-found-rendered.yaml
kubectl apply --dry-run=client --validate=false -f $env:TEMP\lost-found-rendered.yaml
```

Also run `kubectl apply --dry-run=client --validate=false -f deploy/k8s/base/smoke-job.yaml`. Expected: static tests pass; overlay rendering contains four Deployments, four Services, one Namespace, no Job, and no Ingress; both client dry-runs exit 0.

- [ ] **Step 7: Commit Kubernetes resources**

```powershell
git add deploy/k8s tests/test_devops_assets.py
git commit -m "feat: add Windows Minikube deployment manifests"
```

### Task 4: Automate Windows Preflight, Deployment, Diagnostics, and Rollback

**Files:**
- Create: `scripts/Test-DevOpsPrerequisites.ps1`
- Create: `scripts/Deploy-Minikube.ps1`
- Create: `scripts/Rollback-Minikube.ps1`
- Modify: `tests/test_devops_assets.py`

- [ ] **Step 1: Add failing PowerShell script contracts**

Add `PowerShellAssetTests` asserting all three scripts use `Set-StrictMode -Version Latest`, `$ErrorActionPreference = "Stop"`, the deploy script references all four Deployments, `kubectl kustomize`, `kubectl apply`, `kubectl rollout status`, `lost-found-smoke`, diagnostics, and rollback; the preflight script checks `docker`, `minikube`, `kubectl`, Docker `OSType=linux`, Minikube status, and current context.

- [ ] **Step 2: Run tests and verify RED**

```powershell
python -B -m unittest tests.test_devops_assets.PowerShellAssetTests -v
```

Expected: failure because `scripts/` does not exist.

- [ ] **Step 3: Implement the prerequisite script**

`Test-DevOpsPrerequisites.ps1` must fail with an actionable message when a command is missing, Docker Desktop is stopped, Docker is in Windows-container mode, Minikube is stopped, or kubectl context is not `minikube`. Its success output ends with `DevOps prerequisites: OK`.

Use these exact checks:

```powershell
foreach ($Name in @("docker", "minikube", "kubectl")) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}
if ((docker info --format '{{.OSType}}') -ne "linux") {
    throw "Docker Desktop must be running in Linux containers mode"
}
if ((minikube status --format '{{.Host}}') -ne "Running") {
    throw "Minikube is not running"
}
if ((kubectl config current-context) -ne "minikube") {
    throw "kubectl current-context must be minikube"
}
```

- [ ] **Step 4: Implement atomic deployment and failure diagnostics**

`Deploy-Minikube.ps1` accepts mandatory `Owner` and 40-character hexadecimal `Sha`. It must:

1. Call the prerequisite script.
2. Read current images for all four Deployments before applying anything.
3. Run `kubectl kustomize deploy/k8s/overlays/minikube-windows`.
4. Replace the four exact tokens from this mapping and fail if any `:dev` remains:

```powershell
$Images = @{
    "lost-found-web-agent:dev" = "ghcr.io/$($Owner.ToLowerInvariant())/lost-found-web-agent:$Sha"
    "lost-found-item-service:dev" = "ghcr.io/$($Owner.ToLowerInvariant())/lost-found-item-service:$Sha"
    "lost-found-claim-service:dev" = "ghcr.io/$($Owner.ToLowerInvariant())/lost-found-claim-service:$Sha"
    "lost-found-handover-service:dev" = "ghcr.io/$($Owner.ToLowerInvariant())/lost-found-handover-service:$Sha"
}
```
5. Write UTF-8 without BOM to a temporary YAML file and apply it.
6. Wait up to 180 seconds for each Deployment rollout.
7. Delete any old smoke Job, apply `deploy/k8s/base/smoke-job.yaml`, wait up to 120 seconds, print its logs, and require successful completion.
8. On failure, print `kubectl get pods`, `kubectl get deployments`, namespace events sorted by timestamp, and logs from all four app labels.
9. If all four previous image references were captured, restore all four with `kubectl set image`, wait for their rollouts, then rethrow the original failure. On a first or partial deployment, preserve the failed resources and rethrow.
10. Always remove the temporary YAML. Preserve the completed smoke Job as deployment evidence; the next deployment deletes it before creating a fresh run.

Use a checked native-command helper so a non-zero kubectl exit code throws instead of silently continuing.

- [ ] **Step 5: Implement explicit rollback**

`Rollback-Minikube.ps1` accepts `Owner` and `Sha`, calls the prerequisite script, and sets all four image references:

```powershell
$Images = @{
    "web-agent" = "lost-found-web-agent"
    "item-service" = "lost-found-item-service"
    "claim-service" = "lost-found-claim-service"
    "handover-service" = "lost-found-handover-service"
}
foreach ($Deployment in $Images.Keys) {
    $Image = "ghcr.io/$($Owner.ToLowerInvariant())/$($Images[$Deployment]):$Sha"
    kubectl -n lost-found set image "deployment/$Deployment" "$Deployment=$Image"
    if ($LASTEXITCODE -ne 0) { throw "Failed to update $Deployment" }
}
foreach ($Deployment in $Images.Keys) {
    kubectl -n lost-found rollout status "deployment/$Deployment" --timeout=180s
    if ($LASTEXITCODE -ne 0) { throw "Rollback failed for $Deployment" }
}
```

- [ ] **Step 6: Run script contracts and preflight**

```powershell
python -B -m unittest tests.test_devops_assets.PowerShellAssetTests -v
pwsh -NoProfile -File scripts/Test-DevOpsPrerequisites.ps1
```

Expected before local setup: static tests pass; preflight stops specifically at missing Minikube or stopped Docker Desktop. After prerequisites are installed and started, it prints `DevOps prerequisites: OK`.

- [ ] **Step 7: Commit deployment automation**

```powershell
git add scripts tests/test_devops_assets.py
git commit -m "feat: automate Minikube deployment and rollback"
```

### Task 5: Add the GitHub Actions CI/CD Workflow

**Files:**
- Create: `.github/workflows/ci-cd.yml`
- Modify: `tests/test_devops_assets.py`

- [ ] **Step 1: Add a failing workflow safety contract**

Add `WorkflowAssetTests` asserting the workflow triggers on pull requests and `main`, defaults to `contents: read`, grants `packages: write` only to the build job, runs Python tests, uses a four-component build matrix, pushes only on `main`, pins deployment to `[self-hosted, Windows, X64, minikube]`, uses `pwsh`, has deployment concurrency, and calls `scripts/Deploy-Minikube.ps1`. Assert no deploy job runs for `pull_request`.

- [ ] **Step 2: Run the workflow contract and verify RED**

```powershell
python -B -m unittest tests.test_devops_assets.WorkflowAssetTests -v
```

Expected: failure because `.github/workflows/ci-cd.yml` does not exist.

- [ ] **Step 3: Create CI and matrix image builds**

Create one workflow named `CI CD` with `pull_request` and pushes to `main`. Define top-level `permissions: {contents: read}`. The `test` job on `ubuntu-latest` performs checkout, Python 3.12 setup, pip install, unittest discovery, compileall, Docker/Kubernetes asset tests, Kustomize render, and client dry-run.

Define a `build` job that needs `test`, runs on `ubuntu-latest`, grants only `contents: read` and `packages: write`, and uses this exact matrix:

```yaml
matrix:
  include:
    - component: web-agent
      dockerfile: docker/web-agent.Dockerfile
      image: lost-found-web-agent
    - component: item-service
      dockerfile: docker/item-service.Dockerfile
      image: lost-found-item-service
    - component: claim-service
      dockerfile: docker/claim-service.Dockerfile
      image: lost-found-claim-service
    - component: handover-service
      dockerfile: docker/handover-service.Dockerfile
      image: lost-found-handover-service
```

Use Docker Buildx. Login to `ghcr.io` only for a `main` push with `${{ github.actor }}` and `${{ secrets.GITHUB_TOKEN }}`. Build on every event, but set `push` true only for `push` on `refs/heads/main`. A shell step writes the lowercase owner to output `owner`; the exact image expression is `ghcr.io/${{ steps.repo.outputs.owner }}/${{ matrix.image }}:${{ github.sha }}`.

- [ ] **Step 4: Add the trusted Windows deployment job**

The `deploy` job needs both `test` and `build`, runs only when `github.event_name == 'push' && github.ref == 'refs/heads/main'`, and uses:

```yaml
runs-on: [self-hosted, Windows, X64, minikube]
concurrency:
  group: minikube-production
  cancel-in-progress: false
environment: minikube
defaults:
  run:
    shell: pwsh
```

After checkout, call:

```powershell
./scripts/Deploy-Minikube.ps1 `
  -Owner '${{ github.repository_owner }}' `
  -Sha '${{ github.sha }}'
```

No PR-controlled job may target the self-hosted runner.

- [ ] **Step 5: Validate workflow and run all tests**

```powershell
python -B -m unittest tests.test_devops_assets -v
python -B -m unittest discover -s tests -v
git diff --check
```

Expected: all tests pass and no whitespace errors exist.

- [ ] **Step 6: Commit CI/CD**

```powershell
git add .github/workflows/ci-cd.yml tests/test_devops_assets.py
git commit -m "feat: add GitHub Actions Kubernetes delivery pipeline"
```

### Task 6: Document Setup and Perform End-to-End Acceptance

**Files:**
- Create: `docs/devops-windows.md`
- Modify: `README.md`
- Modify: `.gitignore`
- Modify: `docs/superpowers/plans/2026-07-06-devops-kubernetes.md`

- [ ] **Step 1: Protect local credentials and runtime files**

Add these entries to `.gitignore`:

```gitignore
actions-runner/
.kube/
*-secret.yaml
deploy/.rendered/
```

Confirm `.env` remains ignored and tracked files contain no API key, PAT, kubeconfig, or Docker registry auth.

- [ ] **Step 2: Write the Windows operations runbook**

`docs/devops-windows.md` must document these concrete steps:

1. Start Docker Desktop in Linux containers mode.
2. Install Minikube with `winget install Kubernetes.minikube` and start it with `minikube start --driver=docker --container-runtime=containerd`.
3. Validate with `docker info`, `minikube status`, and `kubectl cluster-info`.
4. Create namespace and GHCR pull secret using `$env:GHCR_USER` and `$env:GHCR_PAT`, with PAT scope `read:packages`.
5. Optionally create `lost-found-secrets` with `OPENAI_API_KEY`; otherwise use `mock-llm`.
6. Register a repository-level Windows x64 GitHub Actions runner, assign label `minikube`, and run it interactively with `run.cmd` under the same Windows user.
7. Explain the hosted-runner CI/build versus local-runner deploy boundary.
8. Trigger deployment by pushing reviewed code to `main`.
9. Open the application with `minikube service web-agent --namespace lost-found --url` and keep that PowerShell window open.
10. Inspect Pods, rollouts, events, and logs; execute `Rollback-Minikube.ps1` with a known 40-character commit SHA.
11. State that all services use one replica and in-memory data resets when Pods restart.

- [ ] **Step 3: Update the README**

Add a DevOps section linking the design, implementation plan, and Windows runbook. Include the four-image topology, GitHub Actions stages, the local access command, and the in-memory-data limitation. Do not claim Minikube deployment was verified until Task 6 Step 6 succeeds.

- [ ] **Step 4: Run complete local verification before cluster setup**

```powershell
python -B -m unittest discover -s tests -v
python -B -m compileall -q .
kubectl kustomize deploy/k8s/overlays/minikube-windows | Out-File -Encoding utf8NoBOM $env:TEMP\lost-found-rendered.yaml
kubectl apply --dry-run=client --validate=false -f $env:TEMP\lost-found-rendered.yaml
git diff --check
git status --short
```

Expected: all automated tests pass, manifests render and dry-run successfully, and only intended files are changed.

- [ ] **Step 5: Prepare the single Windows machine**

Start Docker Desktop. If Minikube is still absent, request user approval before running `winget install Kubernetes.minikube`. Start the cluster with the Docker driver, create `ghcr-pull`, and start the repository-scoped runner interactively. Never print PAT or API key values.

- [ ] **Step 6: Perform end-to-end deployment acceptance**

Run `Deploy-Minikube.ps1` with the GitHub owner and an existing pushed 40-character SHA, then verify:

```powershell
kubectl -n lost-found get deployments,pods,services
kubectl -n lost-found get job lost-found-smoke
minikube service web-agent --namespace lost-found --url
```

Expected: four Deployments are `Available`, four app Pods are Ready, smoke Job completes, only `web-agent` is NodePort, and the returned local URL serves the page and `/api/chat`.

- [ ] **Step 7: Verify rollback with two real image revisions**

Deploy a second valid SHA, run `Rollback-Minikube.ps1` with the first SHA, and use `kubectl -n lost-found get deployments -o jsonpath` to confirm every running image uses the first SHA. Re-deploy the latest SHA after the rollback test.

- [ ] **Step 8: Commit documentation and final status**

Mark completed checkboxes in this plan, record the actual test count and cluster verification evidence in `docs/devops-windows.md`, then:

```powershell
git add .gitignore README.md docs/devops-windows.md docs/superpowers/plans/2026-07-06-devops-kubernetes.md
git commit -m "docs: add Windows Kubernetes operations guide"
git status --short
```

Expected: no unintended or secret files are tracked. If cluster acceptance could not run because Docker Desktop, Minikube, GHCR credentials, or the GitHub runner is unavailable, document that exact external prerequisite as unverified rather than marking deployment complete.
