# Windows Docker Compose DevOps Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a GitHub Actions pipeline that tests the repository, builds four Docker targets, and automatically deploys the four-service system through Docker Compose on one Windows 11 self-hosted runner with health checks and image rollback.

**Architecture:** Keep the Python monorepo but run `web-agent`, `item-service`, `claim-service`, and `handover-service` as separate Compose services. GitHub-hosted Linux runners validate code and images; the trusted Windows runner rebuilds the verified `main` commit locally, deploys SHA-tagged images, runs smoke tests, and restores the previous SHA on failure.

**Tech Stack:** Python 3.12, Docker Desktop, Docker Compose 5, Docker Buildx, GitHub Actions, PowerShell 7, unittest.

---

## File Structure

- Create `web_server.py`: Web/Agent-only HTTP process used by the `web-agent` container.
- Modify `server.py`: preserve the local all-in-one entry point while delegating Web handling to `web_server.py`.
- Modify `services/item_service.py`, `services/claim_service.py`, `services/handover_service.py`: add local `/healthz` endpoints.
- Modify `tests/test_services.py`, `tests/test_experiment4.py`: test health endpoints and Web-only startup.
- Create `Dockerfile`: shared base plus four named build targets.
- Create `.dockerignore`: exclude secrets, caches, VCS metadata, tests, and reports from image context.
- Create `compose.yaml`: four services, internal DNS, health dependencies, hardening, and only one published port.
- Create `tests/test_devops_assets.py`: static contracts for Dockerfile, Compose, PowerShell, and workflow assets.
- Create `scripts/Test-Compose.ps1`: container health, port exposure, homepage, and chat smoke tests.
- Create `scripts/Deploy-Compose.ps1`: preflight, SHA build, deployment, diagnostics, and automatic rollback.
- Create `scripts/Rollback-Compose.ps1`: explicit rollback to a locally available SHA.
- Create `.github/workflows/ci-cd.yml`: PR/main CI and trusted Windows deployment.
- Create `docs/devops-compose-windows.md`: Windows Docker Desktop and runner operations guide.
- Modify `.env.example`, `.gitignore`, and `README.md`: Compose defaults, secret exclusions, and operator documentation.

### Task 1: Separate the Web Process and Add Health Endpoints

**Files:**
- Create: `web_server.py`
- Modify: `server.py`
- Modify: `services/item_service.py`
- Modify: `services/claim_service.py`
- Modify: `services/handover_service.py`
- Modify: `tests/test_services.py`
- Modify: `tests/test_experiment4.py`

- [x] **Step 1: Write failing business-service health tests**

Append this test class to `tests/test_services.py`:

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

- [x] **Step 2: Write the failing Web-only runtime test**

In `tests/test_experiment4.py`, import `SESSIONS` and `WebHandler` from `web_server`, keep `start_business_services` and `stop_servers` imported from `server`, change `@patch("server.serve_struct")` to `@patch("web_server.serve_struct")`, and add:

```python
class WebRuntimeTests(unittest.TestCase):
    def test_web_health_does_not_require_business_services(self):
        with running_server(WebHandler) as base:
            with urllib.request.urlopen(base + "/healthz", timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(response.status, 200)
        self.assertEqual(payload, {"status": "ok"})
```

- [x] **Step 3: Run focused tests and verify RED**

```powershell
python -B -m unittest tests.test_services.HealthEndpointTests tests.test_experiment4.WebRuntimeTests -v
```

Expected: import failure because `web_server.py` does not exist; after adding the import temporarily, business `/healthz` requests return 404.

- [x] **Step 4: Create `web_server.py`**

Move `SESSIONS`, `WEB_DIR`, and the complete `WebHandler` implementation from `server.py` into `web_server.py`. Keep the current POST contract unchanged and implement these GET/startup functions:

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

if __name__ == "__main__":
    main()
```

- [x] **Step 5: Preserve the all-in-one development entry point**

Remove the Web handler implementation from `server.py`. Import `WebHandler` and `create_web_server` from `web_server`, re-export `WebHandler` for compatibility, and change `main()` to:

```python
def main():
    services = start_business_services()
    web_server = create_web_server()
    try:
        print("寻迹校园已启动：http://localhost:8000")
        web_server.serve_forever()
    finally:
        web_server.server_close()
        stop_servers(services)
```

- [x] **Step 6: Add local health branches to business services**

At the beginning of each handler's `do_GET`, immediately after `parsed = urlparse(self.path)`, add:

```python
if parsed.path == "/healthz":
    return self._send(200, {"status": "ok"})
```

Do not call another service or read `ITEMS`, `CLAIMS`, `APPOINTMENTS`, or slots from this branch.

- [x] **Step 7: Run focused and full regression tests**

```powershell
python -B -m unittest tests.test_services.HealthEndpointTests tests.test_experiment4.WebRuntimeTests tests.test_experiment4.ServerTests -v
python -B -m unittest discover -s tests -v
python -B -m compileall -q .
```

Expected: all tests pass and compileall exits 0.

- [ ] **Step 8: Commit the runtime split**

```powershell
git add web_server.py server.py services/item_service.py services/claim_service.py services/handover_service.py tests/test_services.py tests/test_experiment4.py
git commit -m "feat: separate web process and add health checks"
```

### Task 2: Create the Multi-Stage Docker Build

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `tests/test_devops_assets.py`

- [x] **Step 1: Write failing Docker asset tests**

Create `tests/test_devops_assets.py` with:

```python
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DockerAssetTests(unittest.TestCase):
    def test_dockerfile_has_pinned_base_and_four_targets(self):
        text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        digest = "sha256:8a7e7cc04fd3e2bd787f7f24e22d5d119aa590d429b50c95dfe12b3abe52f48b"
        self.assertIn(f"python:3.12-slim-bookworm@{digest}", text)
        for target in ("base", "web-agent", "item-service", "claim-service", "handover-service"):
            self.assertIn(f" AS {target}", text)
        self.assertEqual(text.count("USER 10001:10001"), 4)
        self.assertEqual(text.count("HEALTHCHECK"), 4)
        for entrypoint in (
            "web_server.py",
            "services/item_service.py",
            "services/claim_service.py",
            "services/handover_service.py",
        ):
            self.assertIn(entrypoint, text)

    def test_build_context_excludes_secrets_and_caches(self):
        text = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        for marker in (".env", ".git", "__pycache__", ".pytest_cache", "tests/", "docs/"):
            self.assertIn(marker, text)
```

- [x] **Step 2: Run Docker asset tests and verify RED**

```powershell
python -B -m unittest tests.test_devops_assets.DockerAssetTests -v
```

Expected: failure because `Dockerfile` and `.dockerignore` do not exist.

- [x] **Step 3: Implement the shared base stage**

Start `Dockerfile` with:

```dockerfile
FROM python:3.12-slim-bookworm@sha256:8a7e7cc04fd3e2bd787f7f24e22d5d119aa590d429b50c95dfe12b3abe52f48b AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid 10001 --no-create-home app
COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt
```

- [x] **Step 4: Implement all four final stages**

The Web stage copies root Python modules and runtime assets:

```dockerfile
FROM base AS web-agent
COPY *.py ./
COPY flows/ ./flows/
COPY web/ ./web/
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]
CMD ["python", "-B", "web_server.py"]
```

Use these complete service-stage definitions:

```dockerfile
FROM base AS item-service
COPY data.py ./data.py
COPY services/item_service.py ./services/item_service.py
USER 10001:10001
EXPOSE 8001
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/healthz', timeout=2)"]
CMD ["python", "-B", "services/item_service.py"]

FROM base AS claim-service
COPY data.py ./data.py
COPY services/claim_service.py ./services/claim_service.py
USER 10001:10001
EXPOSE 8002
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8002/healthz', timeout=2)"]
CMD ["python", "-B", "services/claim_service.py"]

FROM base AS handover-service
COPY data.py ./data.py
COPY services/handover_service.py ./services/handover_service.py
USER 10001:10001
EXPOSE 8003
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8003/healthz', timeout=2)"]
CMD ["python", "-B", "services/handover_service.py"]
```

- [x] **Step 5: Create `.dockerignore`**

Use exactly:

```dockerignore
.git
.github
.agents
.codex
.env
.env.*
!.env.example
__pycache__/
*.py[cod]
.pytest_cache/
tests/
docs/
report.md
```

- [ ] **Step 6: Run static tests and build every target**

Start Docker Desktop in Linux containers mode, then run:

```powershell
python -B -m unittest tests.test_devops_assets.DockerAssetTests -v
docker build --target web-agent -t lost-found/web-agent:test .
docker build --target item-service -t lost-found/item-service:test .
docker build --target claim-service -t lost-found/claim-service:test .
docker build --target handover-service -t lost-found/handover-service:test .
```

Expected: tests pass and all four builds exit 0.

- [ ] **Step 7: Inspect the image runtime users**

```powershell
docker image inspect lost-found/web-agent:test --format '{{.Config.User}}'
docker image inspect lost-found/item-service:test --format '{{.Config.User}}'
docker image inspect lost-found/claim-service:test --format '{{.Config.User}}'
docker image inspect lost-found/handover-service:test --format '{{.Config.User}}'
```

Expected: each command prints `10001:10001`.

- [ ] **Step 8: Commit container builds**

```powershell
git add Dockerfile .dockerignore tests/test_devops_assets.py
git commit -m "feat: add multi-stage container builds"
```

### Task 3: Define the Four-Service Compose Stack

**Files:**
- Create: `compose.yaml`
- Modify: `tests/test_devops_assets.py`

- [x] **Step 1: Add failing Compose contracts**

Append:

```python
class ComposeAssetTests(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    def test_stack_has_four_sha_tagged_services_and_one_host_port(self):
        self.assertIn("name: lost-found", self.text)
        for service in ("web-agent", "item-service", "claim-service", "handover-service"):
            self.assertIn(f"  {service}:\n", self.text)
            self.assertIn(f"target: {service}", self.text)
        self.assertEqual(self.text.count("127.0.0.1:8000:8000"), 1)
        for forbidden in ("8001:8001", "8002:8002", "8003:8003"):
            self.assertNotIn(forbidden, self.text)

    def test_stack_has_internal_dns_health_dependencies_and_hardening(self):
        for url in (
            "http://item-service:8001",
            "http://claim-service:8002",
            "http://handover-service:8003",
        ):
            self.assertIn(url, self.text)
        for marker in (
            "condition: service_healthy",
            "read_only: true",
            "no-new-privileges:true",
            "cap_drop:",
            "- ALL",
            "tmpfs:",
            "restart: unless-stopped",
        ):
            self.assertIn(marker, self.text)
```

- [x] **Step 2: Run Compose tests and verify RED**

```powershell
python -B -m unittest tests.test_devops_assets.ComposeAssetTests -v
```

Expected: failure because `compose.yaml` does not exist.

- [x] **Step 3: Create the shared Compose service policy**

Start `compose.yaml` with:

```yaml
name: lost-found

x-service-defaults: &service-defaults
  restart: unless-stopped
  read_only: true
  tmpfs:
    - /tmp:size=64m,mode=1777
  security_opt:
    - no-new-privileges:true
  cap_drop:
    - ALL
  networks:
    - backend
  cpus: 0.50
  mem_limit: 512m
```

- [x] **Step 4: Define `web-agent`**

```yaml
services:
  web-agent:
    <<: *service-defaults
    build:
      context: .
      dockerfile: Dockerfile
      target: web-agent
    image: lost-found/web-agent:${IMAGE_TAG:-dev}
    ports:
      - "127.0.0.1:8000:8000"
    environment:
      ITEM_URL: http://item-service:8001
      CLAIM_URL: http://claim-service:8002
      HANDOVER_URL: http://handover-service:8003
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      OPENAI_BASE_URL: ${OPENAI_BASE_URL:-https://dashscope.aliyuncs.com/compatible-mode/v1}
      CHAT_MODEL: ${CHAT_MODEL:-mock-llm}
      POLICY_K: ${POLICY_K:-2}
    depends_on:
      item-service:
        condition: service_healthy
      claim-service:
        condition: service_healthy
      handover-service:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]
      interval: 10s
      timeout: 3s
      retries: 6
      start_period: 5s
```

- [x] **Step 5: Define the three business services**

```yaml
  item-service:
    <<: *service-defaults
    build:
      context: .
      dockerfile: Dockerfile
      target: item-service
    image: lost-found/item-service:${IMAGE_TAG:-dev}
    expose:
      - "8001"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/healthz', timeout=2)"]
      interval: 10s
      timeout: 3s
      retries: 6
      start_period: 5s

  claim-service:
    <<: *service-defaults
    build:
      context: .
      dockerfile: Dockerfile
      target: claim-service
    image: lost-found/claim-service:${IMAGE_TAG:-dev}
    expose:
      - "8002"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8002/healthz', timeout=2)"]
      interval: 10s
      timeout: 3s
      retries: 6
      start_period: 5s

  handover-service:
    <<: *service-defaults
    build:
      context: .
      dockerfile: Dockerfile
      target: handover-service
    image: lost-found/handover-service:${IMAGE_TAG:-dev}
    expose:
      - "8003"
    environment:
      CLAIM_URL: http://claim-service:8002
    depends_on:
      claim-service:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8003/healthz', timeout=2)"]
      interval: 10s
      timeout: 3s
      retries: 6
      start_period: 5s

networks:
  backend:
    driver: bridge
```

- [x] **Step 6: Validate the Compose model**

```powershell
python -B -m unittest tests.test_devops_assets.ComposeAssetTests -v
docker compose -f compose.yaml config --quiet
docker compose -f compose.yaml config --services
```

Expected: tests pass, config exits 0, and the service list contains `web-agent`, `item-service`, `claim-service`, and `handover-service` with no extra service.

- [ ] **Step 7: Build and start the stack manually**

```powershell
$env:IMAGE_TAG='dev'
docker compose -p lost-found -f compose.yaml build
docker compose -p lost-found -f compose.yaml up -d --wait --remove-orphans
docker compose -p lost-found -f compose.yaml ps
```

Expected: four containers are running and healthy; only `web-agent` shows a published host port.

- [ ] **Step 8: Commit Compose orchestration**

```powershell
git add compose.yaml tests/test_devops_assets.py
git commit -m "feat: add four-service Compose stack"
```

### Task 4: Add Windows Deployment, Smoke Test, and Rollback Scripts

**Files:**
- Create: `scripts/Test-Compose.ps1`
- Create: `scripts/Deploy-Compose.ps1`
- Create: `scripts/Rollback-Compose.ps1`
- Modify: `tests/test_devops_assets.py`

- [x] **Step 1: Add failing PowerShell asset contracts**

Append a `PowerShellAssetTests` class that loads all three scripts and asserts each uses `Set-StrictMode -Version Latest` and `$ErrorActionPreference = "Stop"`. Assert `Test-Compose.ps1` references four services, `localhost:8000/healthz`, `/api/chat`, and `docker port`; assert `Deploy-Compose.ps1` references `docker info`, `docker compose version`, `build`, `up`, `--wait`, `--remove-orphans`, `logs`, the smoke script, and old-tag rollback; assert `Rollback-Compose.ps1` validates a 40-character hexadecimal SHA and uses `--no-build --wait`.

- [x] **Step 2: Run script contracts and verify RED**

```powershell
python -B -m unittest tests.test_devops_assets.PowerShellAssetTests -v
```

Expected: failure because `scripts/` does not exist.

- [x] **Step 3: Implement `Test-Compose.ps1`**

The script parameters are `ProjectName = "lost-found"`, `ComposeFile = "compose.yaml"`, and `BaseUrl = "http://localhost:8000"`. It must:

1. Query each service ID using `docker compose -p $ProjectName -f $ComposeFile ps -q $Service` and fail if empty.
2. Inspect `{{.State.Health.Status}}` for every container and require `healthy`.
3. Require `docker port` output to be empty for `item-service`, `claim-service`, and `handover-service`.
4. GET `$BaseUrl/healthz` and require `status=ok`.
5. GET `$BaseUrl/` and require `寻迹校园`.
6. POST this JSON and require HTTP 200 plus `LF2026001` in `reply`:

```json
{"user_id":"u001","message":"帮我找图书馆发现的黑色耳机"}
```

Use `Invoke-RestMethod`, `ConvertTo-Json -Compress`, and a 10-second timeout. End with `Compose smoke tests: PASS`.

- [x] **Step 4: Implement deployment preflight and old-tag detection**

`Deploy-Compose.ps1` accepts mandatory `Sha` with `[ValidatePattern('^[0-9a-f]{40}$')]`, plus the same project/file defaults. It checks that `docker`, `docker compose`, and Docker daemon are available; requires `docker info --format '{{.OSType}}'` to equal `linux`; and runs `docker compose config --quiet` without printing expanded configuration.

Use this exact service/image mapping:

```powershell
$Images = [ordered]@{
    "web-agent" = "lost-found/web-agent"
    "item-service" = "lost-found/item-service"
    "claim-service" = "lost-found/claim-service"
    "handover-service" = "lost-found/handover-service"
}
```

For each running service, inspect `.Config.Image`, require the matching image prefix, and collect its tag. If zero containers exist, treat this as first deployment. If one to three exist, distinct tags are found, or the common tag is not 40 lowercase hexadecimal characters, stop before building and print `Existing Compose deployment is partial, mutable, or uses mixed tags`.

- [x] **Step 5: Implement build, deploy, diagnostics, and rollback**

Within `try`, set `$env:IMAGE_TAG = $Sha`, then invoke checked native commands for:

```powershell
docker compose -p $ProjectName -f $ComposeFile build --pull
docker compose -p $ProjectName -f $ComposeFile up -d --wait --remove-orphans
& "$PSScriptRoot/Test-Compose.ps1" -ProjectName $ProjectName -ComposeFile $ComposeFile
```

Within `catch`, capture the original error, run `docker compose ps` and `docker compose logs --tail 200` without printing environment/configuration, then:

```powershell
if ($PreviousTag) {
    $env:IMAGE_TAG = $PreviousTag
    docker compose -p $ProjectName -f $ComposeFile up -d --no-build --wait --remove-orphans
    & "$PSScriptRoot/Test-Compose.ps1" -ProjectName $ProjectName -ComposeFile $ComposeFile
}
throw $OriginalError
```

A checked native-command helper must examine `$LASTEXITCODE` after every Docker command and throw a message containing the command name and exit code.

- [x] **Step 6: Implement `Rollback-Compose.ps1`**

Accept mandatory `Sha` with the same validation and defaults. For every image in the ordered mapping, run `docker image inspect "$ImageName`:$Sha"`; if any image is absent, fail before changing containers. Set `$env:IMAGE_TAG`, run:

```powershell
docker compose -p $ProjectName -f $ComposeFile up -d --no-build --wait --remove-orphans
& "$PSScriptRoot/Test-Compose.ps1" -ProjectName $ProjectName -ComposeFile $ComposeFile
```

End with `Rollback completed: $Sha`.

- [ ] **Step 7: Run static tests and a dev smoke test**

```powershell
python -B -m unittest tests.test_devops_assets.PowerShellAssetTests -v
pwsh -NoProfile -File scripts/Test-Compose.ps1
docker compose -p lost-found -f compose.yaml down
```

Expected: static tests pass; with the Task 3 stack running, the script prints `Compose smoke tests: PASS`; the final command removes the mutable `dev` deployment before immutable-SHA testing.

- [ ] **Step 8: Verify SHA deployment locally**

```powershell
$sha = git rev-parse HEAD
pwsh -NoProfile -File scripts/Deploy-Compose.ps1 -Sha $sha
docker compose -p lost-found -f compose.yaml images
```

Expected: deployment and smoke tests pass; all four images use the same 40-character tag.

- [ ] **Step 9: Commit operation scripts**

```powershell
git add scripts tests/test_devops_assets.py
git commit -m "feat: automate Compose deployment and rollback"
```

### Task 5: Add GitHub Actions CI/CD

**Files:**
- Create: `.github/workflows/ci-cd.yml`
- Modify: `tests/test_devops_assets.py`

- [x] **Step 1: Add a failing workflow safety contract**

Append `WorkflowAssetTests` asserting `.github/workflows/ci-cd.yml` triggers on pull requests and `main`, defaults to `contents: read`, runs unittest/compileall/Compose validation, builds a four-target matrix without pushing, and has a deploy job with `[self-hosted, Windows, X64, compose-local]`, `environment: compose-local`, `shell: pwsh`, concurrency, and `Deploy-Compose.ps1`. Assert the deploy condition requires both a push event and `refs/heads/main`.

- [x] **Step 2: Run the workflow test and verify RED**

```powershell
python -B -m unittest tests.test_devops_assets.WorkflowAssetTests -v
```

Expected: failure because `.github/workflows/ci-cd.yml` does not exist.

- [x] **Step 3: Create the test and target-build jobs**

Create workflow `CI CD` with pull request and `main` push triggers, top-level `permissions: {contents: read}`, and a `test` job on `ubuntu-latest`. Use `actions/checkout@v4` and `actions/setup-python@v5` with Python 3.12, install requirements, run unittest discovery and compileall, then run `IMAGE_TAG=ci docker compose -f compose.yaml config --quiet`.

Create a `build` job that needs `test`, runs on `ubuntu-latest`, and uses this matrix:

```yaml
matrix:
  target:
    - web-agent
    - item-service
    - claim-service
    - handover-service
```

Use `actions/checkout@v4`, `docker/setup-buildx-action@v3`, and `docker/build-push-action@v6` with `context: .`, `file: Dockerfile`, `target: ${{ matrix.target }}`, `push: false`, `cache-from: type=gha`, and `cache-to: type=gha,mode=max`. No workflow job logs into a registry.

- [x] **Step 4: Create the trusted Windows deploy job**

The deploy job needs both prior jobs and uses:

```yaml
if: github.event_name == 'push' && github.ref == 'refs/heads/main'
runs-on: [self-hosted, Windows, X64, compose-local]
environment: compose-local
concurrency:
  group: compose-local-production
  cancel-in-progress: false
defaults:
  run:
    shell: pwsh
```

After `actions/checkout@v4`, run:

```powershell
./scripts/Deploy-Compose.ps1 -Sha '${{ github.sha }}'
```

Set only this step's `OPENAI_API_KEY` environment value to `${{ secrets.OPENAI_API_KEY }}`. Do not target the self-hosted runner from PR jobs.

- [x] **Step 5: Run workflow and full static contracts**

```powershell
python -B -m unittest tests.test_devops_assets -v
python -B -m unittest discover -s tests -v
git diff --check
```

Expected: all tests pass and no whitespace errors exist.

- [ ] **Step 6: Commit CI/CD**

```powershell
git add .github/workflows/ci-cd.yml tests/test_devops_assets.py
git commit -m "feat: add Compose CI CD workflow"
```

### Task 6: Document Windows Operations and Complete Acceptance

**Files:**
- Create: `docs/devops-compose-windows.md`
- Modify: `.env.example`
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-07-06-devops-docker-compose.md`

- [x] **Step 1: Update example configuration and ignores**

Keep `.env` ignored. Add `IMAGE_TAG=dev` to `.env.example` and explain that Compose replaces the localhost service URLs internally. Add these `.gitignore` entries:

```gitignore
actions-runner/
.deploy/
*.secret.env
```

- [x] **Step 2: Write the Windows runbook**

`docs/devops-compose-windows.md` must document:

1. Start Docker Desktop, select Linux containers, and verify `docker info --format '{{.OSType}}'` returns `linux`.
2. Run local tests, Compose validation, manual build, start, status, logs, smoke test, and stop commands.
3. Explain that `docker compose down` removes containers and resets all in-memory business state on the next start.
4. In GitHub repository Settings → Actions → Runners, add a Windows x64 repository runner, assign custom label `compose-local`, and keep `run.cmd` open under the same Windows user that runs Docker Desktop.
5. In Settings → Environments, create `compose-local`; optionally add secret `OPENAI_API_KEY`.
6. Protect `main` so the GitHub-hosted test/build jobs must pass before merge.
7. Trigger deployment by merging or pushing reviewed code to `main`.
8. Inspect Actions, Compose status, bounded logs, and container health.
9. Find available local tags with `docker image ls lost-found/*` and invoke `Rollback-Compose.ps1` with an existing 40-character SHA.
10. Remove old images only through an explicit operator command after confirming they are not the current or previous tag.

- [x] **Step 3: Update README**

Add a DevOps section linking the design, implementation plan, and Windows runbook. Show the four-service topology, `http://localhost:8000`, local Compose commands, GitHub Actions stages, rollback command, and the in-memory data limitation. Replace the statement that Docker is out of scope only after implementation and verification succeed.

- [x] **Step 4: Run complete automated verification**

```powershell
python -B -m unittest discover -s tests -v
python -B -m compileall -q .
docker compose -f compose.yaml config --quiet
git diff --check
git status --short
```

Expected: all tests pass, Compose validation exits 0, and only intended files are modified.

- [ ] **Step 5: Run container acceptance**

```powershell
$sha = git rev-parse HEAD
pwsh -NoProfile -File scripts/Deploy-Compose.ps1 -Sha $sha
docker compose -p lost-found -f compose.yaml ps
pwsh -NoProfile -File scripts/Test-Compose.ps1
```

Expected: four containers are healthy, only `127.0.0.1:8000` is published, and smoke tests pass.

- [ ] **Step 6: Verify rollback with two image revisions**

Build and deploy two valid commit SHAs in order. Run `Rollback-Compose.ps1` with the first SHA, verify all four running `.Config.Image` values end in the first SHA, then redeploy the latest SHA. Do not fabricate rollback success when two local revisions are unavailable.

- [ ] **Step 7: Record evidence and commit documentation**

Record the actual unittest count, Docker/Compose versions, container health output, smoke result, and rollback result in `docs/devops-compose-windows.md`. Mark only completed plan checkboxes, then:

```powershell
git add .env.example .gitignore README.md docs/devops-compose-windows.md docs/superpowers/plans/2026-07-06-devops-docker-compose.md
git commit -m "docs: add Windows Compose operations guide"
git status --short
```

Expected: no `.env`, API key, runner files, secret environment file, Python cache, or unrelated user file is tracked. If Docker Desktop or the self-hosted runner is unavailable, record that external acceptance step as unverified rather than marking it complete.
