"""Static queue/scheduling and portable Windows packaging contracts."""

import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


class WindowsBuildSchedulingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = yaml.safe_load(
            (ROOT / ".github/workflows/build-windows.yml").read_text(encoding="utf-8")
        )
        cls.windows = cls.workflow["jobs"]["windows"]

    def test_unrelated_quality_runs_do_not_enter_windows_workflow(self):
        triggers = self.workflow.get("on", self.workflow.get(True))
        trigger = triggers["workflow_run"]
        self.assertEqual(trigger["workflows"], ["P5 Quality Gates"])
        self.assertEqual(trigger["types"], ["completed"])
        self.assertEqual(trigger["branches"], ["main"])

    def test_ineligible_jobs_cannot_replace_a_queued_build(self):
        self.assertNotIn("concurrency", self.workflow)
        self.assertIn("concurrency", self.windows)
        condition = " ".join(self.windows["if"].split())
        self.assertEqual(
            condition,
            "github.event.workflow_run.conclusion == 'success' && "
            "github.event.workflow_run.head_branch == 'main'",
        )

    def test_new_builds_preserve_the_active_windows_job(self):
        queue = self.windows["concurrency"]
        self.assertEqual(queue["group"], "update-p5-edit-aja-windows")
        self.assertIs(queue["cancel-in-progress"], False)

    def test_portable_packaging_dependencies_are_checked_around_compile(self):
        commands = [step.get("run", "") for step in self.windows["steps"]]
        early = commands.index("./scripts/windows/prepare-package-images.ps1 -DependenciesOnly")
        compile_app = commands.index("./scripts/windows/invoke-craft.ps1 -Mode build")
        full = commands.index("./scripts/windows/prepare-package-images.ps1")
        package = commands.index("./scripts/windows/invoke-craft.ps1 -Mode package")
        self.assertLess(early, compile_app)
        self.assertLess(compile_app, full)
        self.assertLess(full, package)
        self.assertNotIn("./scripts/windows/invoke-craft.ps1 -Mode install-packager", commands)

    def test_windows_build_is_portable_only(self):
        workflow_text = (ROOT / ".github/workflows/build-windows.yml").read_text(encoding="utf-8")
        craft_config = (ROOT / "scripts/configure_craft.py").read_text(encoding="utf-8")
        invoke = (ROOT / "scripts/windows/invoke-craft.ps1").read_text(encoding="utf-8")
        blueprint = (ROOT / "craft/editaja/editaja.py").read_text(encoding="utf-8")
        wrapper = (ROOT / "scripts/windows/prepare-package-images.ps1").read_text(encoding="utf-8")

        self.assertIn("PortablePackager", craft_config)
        self.assertIn('"7ZipArchiveType": "zip"', craft_config)
        self.assertNotIn("install-packager", workflow_text)
        self.assertNotIn("install-packager", invoke)
        self.assertNotIn("NullsoftInstallerPackager", blueprint)
        self.assertNotIn("registry_hook", blueprint)
        self.assertNotIn("--check-installer-tools", wrapper)

    def test_portable_artifact_is_uploaded_before_smoke(self):
        names = [step["name"] for step in self.windows["steps"]]
        collect = names.index("Collect Windows portable package")
        upload = names.index("Upload Edit Aja Gemini Windows portable")
        smoke = names.index("Smoke test portable Windows app")
        source = names.index("Upload verified corresponding source")
        self.assertLess(collect, upload)
        self.assertLess(upload, smoke)
        self.assertLess(smoke, source)

        upload_step = self.windows["steps"][upload]
        self.assertEqual(upload_step["with"]["name"], "Edit-Aja-Gemini-Windows-Portable-x64")

    def test_startup_smoke_extracts_probes_and_starts_without_installing(self):
        script = (ROOT / "scripts/windows/smoke-test-package.ps1").read_text(encoding="utf-8")
        self.assertIn("Edit-Aja-Gemini-Windows-Portable-x64.zip", script)
        self.assertIn("Expand-Archive", script)
        self.assertIn("'kdenlive.exe'", script)
        self.assertIn("@('--version')", script)
        self.assertIn("$second -lt 15", script)
        self.assertIn("Assert-SmokeProcessRunning", script)
        for forbidden in ("uninstall.exe", "/CurrentUser", "Install_Dir", "Resolve-InstalledRoot"):
            self.assertNotIn(forbidden, script)

    def test_collector_rejects_installer_artifacts(self):
        script = (ROOT / "scripts/windows/collect-package.ps1").read_text(encoding="utf-8")
        self.assertIn("Edit-Aja-Gemini-Windows-Portable-x64.zip", script)
        self.assertIn("Get-FileHash", script)
        self.assertIn("Portable artifact directory must not contain an installer EXE.", script)
        self.assertNotIn("'.7z'", script)

    def test_functional_editor_smoke_runs_after_startup_smoke(self):
        names = [step["name"] for step in self.windows["steps"]]
        startup = names.index("Smoke test portable Windows app")
        functional = names.index("Functional smoke test packaged editor")
        source = names.index("Upload verified corresponding source")
        self.assertLess(startup, functional)
        self.assertLess(functional, source)

    def test_functional_editor_smoke_uses_live_native_registry_from_portable_zip(self):
        script = (ROOT / "scripts/windows/functional-smoke-package.ps1").read_text(encoding="utf-8")
        for token in (
            "Edit-Aja-Gemini-Windows-Portable-x64.zip",
            "Expand-Archive",
            "kdenlive-open-agent.json",
            "kdenlive_get_project_info",
            "kdenlive_get_timeline_state",
            "kdenlive_cut_clip",
            "kdenlive_add_subtitle",
            "kdenlive_list_subtitles",
            "kdenlive_save_project",
            "corresponding-source/tests/dataset/av.kdenlive",
            "FUNCTIONAL PORTABLE EDITOR SMOKE PASS",
        ):
            self.assertIn(token, script)
        for forbidden in ("uninstall.exe", "/CurrentUser", "Install_Dir", "Resolve-InstalledRoot"):
            self.assertNotIn(forbidden, script)

    def test_smoke_diagnostics_are_uploaded_even_after_test_failure(self):
        steps = self.windows["steps"]
        names = [step["name"] for step in steps]
        upload = next(step for step in steps if step["name"] == "Upload packaged-app smoke diagnostics")
        self.assertLess(names.index("Functional smoke test packaged editor"), names.index(upload["name"]))
        self.assertEqual(upload["if"], "${{ always() && steps.windows_package.outcome == 'success' }}")
        self.assertEqual(upload["with"]["path"], "artifacts/smoke/**")
        self.assertEqual(upload["with"]["retention-days"], 14)

    def test_functional_save_has_a_dedicated_timeout_and_timing_logs(self):
        script = (ROOT / "scripts/windows/functional-smoke-package.ps1").read_text(encoding="utf-8")
        self.assertIn("[int]$TimeoutSeconds = 30", script)
        self.assertIn("Native tool call: $Name", script)
        self.assertIn("Native tool call complete: $Name", script)
        self.assertIn(
            "-Name 'kdenlive_save_project' -Arguments @{ path = $savedProjectPath; save_copy = $true; overwrite = $true } -TimeoutSeconds 120",
            script,
        )

    def test_dependency_install_retries_transient_network_failures(self):
        script = (ROOT / "scripts/windows/invoke-craft.ps1").read_text(encoding="utf-8")
        install_block = script.split("'install-deps' {", 1)[1].split("'build' {", 1)[0]
        self.assertIn("$maxAttempts = 3", install_block)
        self.assertIn("Craft dependency attempt", script)
        self.assertIn("$PSNativeCommandUseErrorActionPreference = $false", script)
        self.assertIn("Start-Sleep -Seconds $delaySeconds", script)
        self.assertIn("already-installed packages will be reused", script)

    def test_build_uses_the_commit_that_passed_quality_gates(self):
        checkout = self.windows["steps"][0]
        self.assertTrue(checkout["uses"].startswith("actions/checkout@"))
        self.assertEqual(
            checkout["with"]["ref"], "${{ github.event.workflow_run.head_sha }}"
        )


if __name__ == "__main__":
    unittest.main()
