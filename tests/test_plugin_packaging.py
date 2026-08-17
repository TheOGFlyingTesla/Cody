from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from support import SKILL_ROOT


SYNC = SKILL_ROOT / "scripts/sync_plugin_runtime.py"
PLUGIN_ROOT = SKILL_ROOT / "plugins/cody-codex-coordinator"
PLUGIN_SKILL_ROOT = PLUGIN_ROOT / "skills/cody-coordinator"
MARKETPLACE = SKILL_ROOT / ".agents/plugins/marketplace.json"


def _sync_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("cody_sync_plugin_runtime", SYNC)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PluginPackagingTests(unittest.TestCase):
    def test_marketplace_points_to_valid_plugin(self) -> None:
        marketplace = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
        self.assertEqual("cody", marketplace["name"])
        self.assertEqual("Cody", marketplace["interface"]["displayName"])
        self.assertEqual(1, len(marketplace["plugins"]))
        entry = marketplace["plugins"][0]
        self.assertEqual("cody-codex-coordinator", entry["name"])
        self.assertEqual("local", entry["source"]["source"])
        self.assertEqual("./plugins/cody-codex-coordinator", entry["source"]["path"])
        self.assertEqual("AVAILABLE", entry["policy"]["installation"])
        self.assertEqual("ON_INSTALL", entry["policy"]["authentication"])
        self.assertEqual("Productivity", entry["category"])

        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(entry["name"], manifest["name"])
        self.assertEqual("0.1.1", manifest["version"])
        self.assertEqual("./skills/", manifest["skills"])
        self.assertNotIn("mcpServers", manifest)
        self.assertNotIn("apps", manifest)
        self.assertNotIn("hooks", manifest)
        self.assertLessEqual(len(manifest["interface"]["defaultPrompt"]), 3)

        agent = (PLUGIN_SKILL_ROOT / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: false", agent)
        self.assertEqual(
            "0.1.0",
            (PLUGIN_SKILL_ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        )

    def test_plugin_runtime_is_byte_identical_to_canonical_skill(self) -> None:
        sync = _sync_module()
        for relative in sorted(sync.PLUGIN_RUNTIME_PATHS):
            canonical = SKILL_ROOT / relative
            runtime = PLUGIN_SKILL_ROOT / relative
            self.assertTrue(canonical.is_file(), relative)
            self.assertTrue(runtime.is_file(), relative)
            self.assertEqual(canonical.read_bytes(), runtime.read_bytes(), relative)

    def test_plugin_runtime_materializer_is_deterministic_and_detects_drift(self) -> None:
        sync = _sync_module()
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "runtime"
            first = sync.sync_plugin_runtime(SKILL_ROOT, destination, check=False)
            self.assertEqual(sorted(sync.PLUGIN_RUNTIME_PATHS), first)
            self.assertEqual([], sync.sync_plugin_runtime(SKILL_ROOT, destination, check=False))
            self.assertEqual([], sync.sync_plugin_runtime(SKILL_ROOT, destination, check=True))

            (destination / "SKILL.md").write_text("drift\n", encoding="utf-8")
            with self.assertRaises(sync.PluginRuntimeError):
                sync.sync_plugin_runtime(SKILL_ROOT, destination, check=True)

    def test_materialized_plugin_runtime_runs_without_source_checkout(self) -> None:
        sync = _sync_module()
        with tempfile.TemporaryDirectory() as directory:
            copied_plugin = Path(directory) / "cody-codex-coordinator"
            copied_skill = copied_plugin / "skills/cody-coordinator"
            sync.sync_plugin_runtime(SKILL_ROOT, copied_skill, check=False)
            (copied_plugin / ".codex-plugin").mkdir(parents=True)
            (copied_plugin / ".codex-plugin/plugin.json").write_bytes(
                (PLUGIN_ROOT / ".codex-plugin/plugin.json").read_bytes()
            )

            command = [
                sys.executable,
                str(copied_skill / "scripts/coordinator_standard.py"),
                "--repo",
                directory,
                "--format",
                "json",
                "inspect",
            ]
            result = subprocess.run(
                command,
                cwd=copied_plugin,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])

    def test_offline_release_remains_skill_only_with_plugin_source_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "cody-coordinator.zip"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SKILL_ROOT / "scripts/build_release.py"),
                    "--release-root",
                    str(SKILL_ROOT),
                    "--output",
                    str(archive_path),
                ],
                cwd=SKILL_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr or result.stdout)
            with zipfile.ZipFile(archive_path) as archive:
                names = set(archive.namelist())
            self.assertFalse(any(name.startswith("plugins/") for name in names))
            self.assertFalse(any(name.startswith(".agents/") for name in names))
            self.assertNotIn("scripts/sync_plugin_runtime.py", names)

    def test_docs_lead_with_marketplace_installation(self) -> None:
        command = "codex plugin marketplace add TheOGFlyingTesla/Cody --ref main"
        install = "codex plugin add cody-codex-coordinator@cody"
        for relative in ("README.md", "docs/INSTALLATION.md", "docs/QUICKSTART.md"):
            text = (SKILL_ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(command, text, relative)
            self.assertIn(install, text, relative)
            self.assertIn("$cody-coordinator", text, relative)

    def test_plugin_release_version_is_documented_incrementally(self) -> None:
        readme = (SKILL_ROOT / "README.md").read_text(encoding="utf-8")
        installation = (SKILL_ROOT / "docs/INSTALLATION.md").read_text(
            encoding="utf-8"
        )
        changelog = (SKILL_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        releases = (SKILL_ROOT / "docs/RELEASES.md").read_text(encoding="utf-8")
        limitations = (SKILL_ROOT / "docs/LIMITATIONS.md").read_text(
            encoding="utf-8"
        )
        support = (SKILL_ROOT / "SUPPORT.md").read_text(encoding="utf-8")
        contributing = (SKILL_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")

        self.assertIn("status-v0.1.1%20preview", readme)
        self.assertIn("Cody plugin v0.1.1", installation)
        self.assertIn("## [0.1.1]", changelog)
        self.assertIn("plugin `0.1.1` ships coordinator standard `0.1.0`", changelog)
        self.assertIn("earlier `v0.1.0` tag remains the skill-only", releases)
        for text in (limitations, support, contributing):
            self.assertIn("v0.1.1", text)
            self.assertIn("standard v0.1.0", text)


if __name__ == "__main__":
    unittest.main()
