from __future__ import annotations

import importlib
import json
from pathlib import Path
import tempfile
import unittest

from support import initialize_git, run_git


V31_MANAGED_BODY = b"""Read these durable project files before coordinating work:

1. `docs/codex/STANDARD.json`
2. `docs/codex/PROJECT.md`
3. `docs/codex/STATUS.md`
4. `docs/codex/ROADMAP.md`
5. `docs/codex/DECISIONS.md`
6. Relevant files under `docs/codex/WORK_ITEMS/` and `docs/codex/MIGRATIONS/`

This managed block and `docs/codex/` are coordinator-owned. Preserve all content outside this block. More-specific nested `AGENTS.md` files govern their subtrees.

At meaningful state transitions, keep `docs/codex/STATUS.md` concise and current so replacement coordinators and the read-only read-only recovery surface can recover verified project truth. Do not create heartbeat-only updates.

Discovered validation entry points:

$VALIDATION_COMMANDS

Project-specific exceptional risk rules:

$RISK_RULES
"""


class UpgradeV31Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = tempfile.TemporaryDirectory()
        self.temp = Path(self.context.name)
        self.operations = importlib.import_module("coordinator_standard.operations")
        self.markers = importlib.import_module("coordinator_standard.markers")

    def tearDown(self) -> None:
        self.context.cleanup()

    def legacy_repo(self) -> Path:
        repo = self.temp / "standard-31-project"
        initialize_git(repo, commit=True)
        created = self.operations.initialize(repo, check=False)
        self.assertTrue(created.ok, created.blockers)

        agents_path = repo / "AGENTS.md"
        agents = agents_path.read_bytes()
        block = self.markers.parse_managed_block(agents)
        self.assertIsNotNone(block)
        rendered_v31 = self.markers.format_managed_block(
            V31_MANAGED_BODY.replace(
                b"$VALIDATION_COMMANDS",
                b"- `python3 -m unittest discover -s tests`",
            ).replace(b"$RISK_RULES", b"- None discovered during setup."),
            version="3.1.0",
        )
        agents_path.write_bytes(agents[: block.start] + rendered_v31 + agents[block.end :])

        standard_path = repo / "docs/codex/STANDARD.json"
        standard = json.loads(standard_path.read_text(encoding="utf-8"))
        standard["standard_version"] = "3.1.0"
        standard["last_validated_at"] = standard["installed_at"]
        standard["migrations"] = []
        standard_path.write_text(json.dumps(standard, indent=2) + "\n", encoding="utf-8")
        (repo / "docs/codex/STATUS.md").write_text(
            "# Coordinator Status\n\n"
            "Checkpoint recorded: 2026-07-10T12:00:00Z\n\n"
            "## Current outcome\n\nPreserve the 3.1 checkpoint.\n\n"
            "## Last verified completed milestone\n\n- Existing milestone.\n\n"
            "## Active or possibly active work\n\n- None verified.\n\n"
            "## Blockers\n\n- None verified.\n\n"
            "## Pending project owner decisions or approvals\n\n- Upgrade approval.\n\n"
            "## Known risks\n\n- Historical detail follows.\n\n"
            "## Recommended next action\n\nRun upgrade check.\n\n"
            "## Confidence and unknowns\n\n"
            + ("Preserved user history. " * 500)
            + "\n",
            encoding="utf-8",
        )
        migrations = repo / "docs/codex/MIGRATIONS"
        for path in migrations.iterdir():
            if path.name.endswith(".journal.json"):
                journal = json.loads(path.read_text(encoding="utf-8"))
                journal["standard_version"] = "3.1.0"
                path.write_text(json.dumps(journal, indent=2) + "\n", encoding="utf-8")
            elif path.name != ".gitkeep" and not path.name.endswith(".report.md"):
                path.unlink()
        run_git(repo, "add", ".")
        run_git(repo, "commit", "--quiet", "-m", "standard 3.1 baseline")
        return repo

    def test_check_apply_doctor_noop_and_historical_journal_preservation(self) -> None:
        repo = self.legacy_repo()
        protected = {
            name: (repo / f"docs/codex/{name}").read_bytes()
            for name in ("PROJECT.md", "STATUS.md", "ROADMAP.md", "DECISIONS.md")
        }
        historical = next((repo / "docs/codex/MIGRATIONS").glob("*.journal.json"))
        historical_before = historical.read_bytes()
        outside_before = b"owner rule\n"
        (repo / "AGENTS.md").write_bytes(outside_before + (repo / "AGENTS.md").read_bytes())
        run_git(repo, "add", "AGENTS.md")
        run_git(repo, "commit", "--quiet", "-m", "owner instructions")

        checked = self.operations.upgrade(repo, check=True)

        self.assertTrue(checked.ok, checked.blockers)
        self.assertTrue(checked.changed)
        paths = {item["relative_path"] for item in checked.operations}
        self.assertIn("AGENTS.md", paths)
        self.assertIn("docs/codex/STANDARD.json", paths)
        self.assertFalse(any(path.endswith(tuple(protected)) for path in paths))

        applied = self.operations.upgrade(repo, check=False)
        self.assertTrue(applied.ok, applied.blockers)
        agents = (repo / "AGENTS.md").read_bytes()
        self.assertTrue(agents.startswith(outside_before))
        self.assertIn(b"standard=0.2.0", agents)
        self.assertIn(b"Routine continuation", agents)
        for name, content in protected.items():
            self.assertEqual(content, (repo / f"docs/codex/{name}").read_bytes())
        self.assertEqual(historical_before, historical.read_bytes())

        standard = json.loads((repo / "docs/codex/STANDARD.json").read_text())
        self.assertEqual("0.2.0", standard["standard_version"])
        self.assertEqual("3.1.0", standard["migrations"][-1]["source_version"])
        self.assertEqual("0.2.0", standard["migrations"][-1]["destination_version"])
        self.assertTrue(self.operations.doctor(repo).ok)
        repeated = self.operations.upgrade(repo, check=True)
        self.assertTrue(repeated.ok, repeated.blockers)
        self.assertFalse(repeated.changed)


if __name__ == "__main__":
    unittest.main()
