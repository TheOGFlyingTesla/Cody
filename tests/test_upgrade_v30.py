from __future__ import annotations

import importlib
import json
from pathlib import Path
import tempfile
import unittest

from support import initialize_git, run_git


class UpgradeV30Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = tempfile.TemporaryDirectory()
        self.temp = Path(self.context.name)
        self.operations = importlib.import_module("coordinator_standard.operations")

    def tearDown(self) -> None:
        self.context.cleanup()

    def legacy_repo(self, *, preserve_historical_journal: bool = False) -> Path:
        repo = self.temp / "legacy-project"
        initialize_git(repo, commit=True)
        created = self.operations.initialize(repo, check=False)
        self.assertTrue(created.ok, created.blockers)

        agents = repo / "AGENTS.md"
        current_guidance = (
            b"At meaningful state transitions, keep `docs/codex/STATUS.md` concise and current "
            b"so replacement coordinators and the read-only read-only recovery surface can recover verified "
            b"project truth. Do not create heartbeat-only updates.\n\n"
        )
        agents.write_bytes(
            b"custom instructions\n"
            + agents.read_bytes().replace(
                b"standard=0.1.0", b"standard=3.0.0", 1
            ).replace(current_guidance, b"")
        )
        standard_path = repo / "docs/codex/STANDARD.json"
        standard = json.loads(standard_path.read_text(encoding="utf-8"))
        standard["standard_version"] = "3.0.0"
        standard["last_validated_at"] = standard["installed_at"]
        standard["migrations"] = []
        standard_path.write_text(json.dumps(standard, indent=2) + "\n", encoding="utf-8")
        status = repo / "docs/codex/STATUS.md"
        status.write_text(status.read_text(encoding="utf-8") + "\nUser status bytes.\n", encoding="utf-8")
        migrations = repo / "docs/codex/MIGRATIONS"
        for path in migrations.iterdir():
            if preserve_historical_journal and path.name.endswith(".journal.json"):
                journal = json.loads(path.read_text(encoding="utf-8"))
                journal["standard_version"] = "3.0.0"
                path.write_text(json.dumps(journal, indent=2) + "\n", encoding="utf-8")
            elif path.name != ".gitkeep" and not (
                preserve_historical_journal and path.name.endswith(".report.md")
            ):
                path.unlink()
        run_git(repo, "add", ".")
        run_git(repo, "commit", "--quiet", "-m", "legacy coordinator 3.0")
        return repo

    def test_check_apply_doctor_and_noop_preserve_project_documents(self) -> None:
        repo = self.legacy_repo()
        protected = {
            name: (repo / f"docs/codex/{name}").read_bytes()
            for name in ("PROJECT.md", "STATUS.md", "ROADMAP.md", "DECISIONS.md")
        }
        agents_before = (repo / "AGENTS.md").read_bytes()

        checked = self.operations.upgrade(repo, check=True)

        self.assertTrue(checked.ok, checked.blockers)
        self.assertTrue(checked.changed)
        paths = {item["relative_path"] for item in checked.operations}
        self.assertIn("AGENTS.md", paths)
        self.assertIn("docs/codex/STANDARD.json", paths)
        self.assertFalse(any(path.endswith(tuple(protected)) for path in paths))

        applied = self.operations.upgrade(repo, check=False)
        self.assertTrue(applied.ok, applied.blockers)
        self.assertEqual(b"custom instructions\n", (repo / "AGENTS.md").read_bytes()[:20])
        self.assertIn(b"standard=0.1.0", (repo / "AGENTS.md").read_bytes())
        self.assertEqual(1, (repo / "AGENTS.md").read_bytes().count(b"Routine continuation"))
        self.assertIn(b"Heartbeats are state-delta-only", (repo / "AGENTS.md").read_bytes())
        self.assertNotEqual(agents_before, (repo / "AGENTS.md").read_bytes())
        for name, content in protected.items():
            self.assertEqual(content, (repo / f"docs/codex/{name}").read_bytes())

        standard = json.loads((repo / "docs/codex/STANDARD.json").read_text())
        self.assertEqual("0.1.0", standard["standard_version"])
        self.assertEqual("3.0.0", standard["migrations"][-1]["source_version"])
        self.assertEqual("0.1.0", standard["migrations"][-1]["destination_version"])
        reports = sorted((repo / "docs/codex/MIGRATIONS").glob("*.md"))
        report = reports[-1].read_text(encoding="utf-8")
        self.assertIn("## Standard 3.0.0 source mapping", report)
        self.assertTrue(all(check["ok"] for check in self.operations.doctor(repo).validation))
        repeated = self.operations.upgrade(repo, check=True)
        self.assertTrue(repeated.ok, repeated.blockers)
        self.assertFalse(repeated.changed)

    def test_unsupported_standard_version_still_blocks(self) -> None:
        repo = self.legacy_repo()
        path = repo / "docs/codex/STANDARD.json"
        standard = json.loads(path.read_text())
        standard["standard_version"] = "2.9.0"
        path.write_text(json.dumps(standard, indent=2) + "\n")

        result = self.operations.upgrade(repo, check=True)

        self.assertFalse(result.ok)
        self.assertEqual("unsupported_standard_version", result.blockers[0].code)

    def test_standard_325_has_a_byte_preserving_upgrade_route(self) -> None:
        repo = self.temp / "standard-325-project"
        initialize_git(repo, commit=True)
        created = self.operations.initialize(repo, check=False)
        self.assertTrue(created.ok, created.blockers)

        markers = importlib.import_module("coordinator_standard.markers")
        agents_path = repo / "AGENTS.md"
        agents = agents_path.read_bytes()
        block = markers.parse_managed_block(agents)
        self.assertIsNotNone(block)
        downgraded = markers.format_managed_block(
            agents[block.body_start : block.body_end], version="3.2.5"
        )
        agents_path.write_bytes(agents[: block.start] + downgraded + agents[block.end :])

        standard_path = repo / "docs/codex/STANDARD.json"
        standard = json.loads(standard_path.read_text(encoding="utf-8"))
        standard["standard_version"] = "3.2.5"
        standard_path.write_text(json.dumps(standard, indent=2) + "\n", encoding="utf-8")
        protected = {
            name: (repo / f"docs/codex/{name}").read_bytes()
            for name in ("PROJECT.md", "STATUS.md", "ROADMAP.md", "DECISIONS.md")
        }
        run_git(repo, "add", ".")
        run_git(repo, "commit", "--quiet", "-m", "standard 3.2.5 baseline")

        checked = self.operations.upgrade(repo, check=True)
        self.assertTrue(checked.ok, checked.blockers)
        self.assertTrue(checked.changed)
        applied = self.operations.upgrade(repo, check=False)
        self.assertTrue(applied.ok, applied.blockers)
        self.assertIn(b"standard=0.1.0", agents_path.read_bytes())
        for name, content in protected.items():
            self.assertEqual(content, (repo / f"docs/codex/{name}").read_bytes())
        self.assertTrue(self.operations.doctor(repo).ok)
        self.assertFalse(self.operations.upgrade(repo, check=True).changed)

    def test_upgrade_preserves_and_accepts_completed_v30_journal(self) -> None:
        repo = self.legacy_repo(preserve_historical_journal=True)
        historical = next(
            (repo / "docs/codex/MIGRATIONS").glob("*.journal.json")
        )
        before = historical.read_bytes()

        checked = self.operations.upgrade(repo, check=True)

        self.assertTrue(checked.ok, checked.blockers)
        self.assertTrue(checked.changed)
        applied = self.operations.upgrade(repo, check=False)
        self.assertTrue(applied.ok, applied.blockers)
        self.assertEqual(before, historical.read_bytes())
        self.assertTrue(all(check["ok"] for check in self.operations.doctor(repo).validation))


if __name__ == "__main__":
    unittest.main()
