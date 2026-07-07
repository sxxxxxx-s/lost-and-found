from pathlib import Path
import re
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


class PowerShellAssetTests(unittest.TestCase):
    def script(self, name):
        return (ROOT / "scripts" / name).read_text(encoding="utf-8")

    def assert_strict_script(self, text):
        self.assertIn("Set-StrictMode -Version Latest", text)
        self.assertIn('$ErrorActionPreference = "Stop"', text)

    def test_test_compose_script_smoke_checks_stack(self):
        text = self.script("Test-Compose.ps1")
        self.assert_strict_script(text)
        for marker in (
            "web-agent",
            "item-service",
            "claim-service",
            "handover-service",
            "localhost:8000/healthz",
            "/api/chat",
            "docker port",
            "LF2026001",
        ):
            self.assertIn(marker, text)

    def test_test_compose_homepage_marker_matches_utf8_page_title(self):
        script = self.script("Test-Compose.ps1")
        page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("寻迹校园", page)
        self.assertIn("寻迹校园", script)
        self.assertNotIn("瀵昏抗", script)

    def test_test_compose_chat_prompt_uses_utf8_user_text(self):
        script = self.script("Test-Compose.ps1")
        self.assertIn("帮我找图书馆发现的黑色耳机", script)
        self.assertNotIn("甯", script)

    def test_deploy_script_preflights_deploys_and_rolls_back(self):
        text = self.script("Deploy-Compose.ps1")
        self.assert_strict_script(text)
        for marker in (
            "docker info",
            "docker compose version",
            "build",
            "up",
            "--wait",
            "--remove-orphans",
            "logs",
            "Test-Compose.ps1",
            "$PreviousTag",
            "Existing Compose deployment is partial, mutable, or uses mixed tags",
        ):
            self.assertIn(marker, text)

    def test_rollback_script_validates_sha_and_uses_no_build_wait(self):
        text = self.script("Rollback-Compose.ps1")
        self.assert_strict_script(text)
        self.assertIn("^[0-9a-f]{40}$", text)
        self.assertIn("--no-build", text)
        self.assertIn("--wait", text)

    def test_scripts_do_not_assign_to_powershell_home_variable(self):
        for name in (
            "Test-Compose.ps1",
            "Deploy-Compose.ps1",
            "Rollback-Compose.ps1",
        ):
            with self.subTest(script=name):
                self.assertIsNone(
                    re.search(r"(?im)^\s*\$home\s*=", self.script(name)),
                    "$HOME is a read-only PowerShell variable",
                )

    def test_scripts_do_not_trim_null_native_output(self):
        for name in ("Test-Compose.ps1", "Deploy-Compose.ps1"):
            with self.subTest(script=name):
                text = self.script(name)
                self.assertNotIn(
                    "$ContainerId = ($ContainerIdRaw | Select-Object -First 1).Trim()",
                    text,
                )
                self.assertNotIn(
                    "$ContainerId = ($ContainerId | Select-Object -First 1).Trim()",
                    text,
                )

    def test_deploy_script_allows_first_deployment_without_existing_containers(self):
        text = self.script("Deploy-Compose.ps1")
        self.assertIn("$ContainerIdLine = $ContainerIdRaw | Select-Object -First 1", text)
        self.assertIn("if ($null -eq $ContainerIdLine)", text)
        self.assertIn("continue", text)


class WorkflowAssetTests(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / ".github" / "workflows" / "ci-cd.yml").read_text(
            encoding="utf-8"
        )

    def test_workflow_triggers_permissions_and_static_validation(self):
        for marker in (
            "name: CI CD",
            "pull_request:",
            "push:",
            "branches:",
            "- main",
            "permissions:",
            "contents: read",
            "python -B -m unittest discover -s tests -v",
            "python -B -m compileall -q .",
            "IMAGE_TAG=ci docker compose -f compose.yaml config --quiet",
        ):
            self.assertIn(marker, self.text)

    def test_workflow_builds_four_targets_without_registry_push(self):
        for marker in (
            "docker/setup-buildx-action@v3",
            "docker/build-push-action@v6",
            "target: ${{ matrix.target }}",
            "push: false",
            "cache-from: type=gha",
            "cache-to: type=gha,mode=max",
            "web-agent",
            "item-service",
            "claim-service",
            "handover-service",
        ):
            self.assertIn(marker, self.text)
        self.assertNotIn("docker/login-action", self.text)

    def test_workflow_deploys_only_main_push_on_trusted_windows_runner(self):
        for marker in (
            "if: github.event_name == 'push' && github.ref == 'refs/heads/main'",
            "runs-on: [self-hosted, Windows, X64, compose-local]",
            "environment: compose-local",
            "concurrency:",
            "group: compose-local-production",
            "cancel-in-progress: false",
            "shell: pwsh",
            "./scripts/Deploy-Compose.ps1 -Sha '${{ github.sha }}'",
            "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}",
        ):
            self.assertIn(marker, self.text)
