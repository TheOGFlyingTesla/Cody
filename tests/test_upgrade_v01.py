from __future__ import annotations

import importlib
import json
from pathlib import Path
import tempfile
import unittest

from support import initialize_git, run_git


class UpgradeV01Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = tempfile.TemporaryDirectory()
        self.temp = Path(self.context.name)
        self.operations = importlib.import_module("coordinator_standard.operations")
        self.markers = importlib.import_module("coordinator_standard.markers")

    def tearDown(self) -> None:
        self.context.cleanup()

    def test_explicit_upgrade_from_010_to_020_is_supported_and_idempotent(self) -> None:
        self._exercise_upgrade("0.1.0")

    def test_explicit_legacy_326_migration_to_public_020_is_supported(self) -> None:
        self._exercise_upgrade("3.2.6")

    def _exercise_upgrade(self, source_version: str) -> None:
        repo = self.temp / "standard-010-project"
        initialize_git(repo, commit=True)
        created = self.operations.initialize(repo, check=False)
        self.assertTrue(created.ok, created.blockers)

        agents_path = repo / "AGENTS.md"
        agents = agents_path.read_bytes()
        block = self.markers.parse_managed_block(agents)
        self.assertIsNotNone(block)
        assert block is not None
        legacy_block = self.markers.format_managed_block(
            agents[block.body_start:block.body_end], version=source_version
        )
        agents_path.write_bytes(agents[:block.start] + legacy_block + agents[block.end:])

        standard_path = repo / "docs/codex/STANDARD.json"
        standard = json.loads(standard_path.read_text(encoding="utf-8"))
        standard["standard_version"] = source_version
        standard_path.write_text(json.dumps(standard, indent=2) + "\n", encoding="utf-8")
        run_git(repo, "add", ".")
        run_git(repo, "commit", "--quiet", "-m", f"standard {source_version} baseline")

        checked = self.operations.upgrade(repo, check=True)
        self.assertTrue(checked.ok, checked.blockers)
        self.assertTrue(checked.changed)

        applied = self.operations.upgrade(repo, check=False)
        self.assertTrue(applied.ok, applied.blockers)
        self.assertIn(b"standard=0.2.0", agents_path.read_bytes())
        upgraded = json.loads(standard_path.read_text(encoding="utf-8"))
        self.assertEqual("0.2.0", upgraded["standard_version"])
        self.assertEqual(source_version, upgraded["migrations"][-1]["source_version"])
        self.assertEqual("0.2.0", upgraded["migrations"][-1]["destination_version"])
        self.assertTrue(self.operations.doctor(repo).ok)
        repeated = self.operations.upgrade(repo, check=True)
        self.assertTrue(repeated.ok, repeated.blockers)
        self.assertFalse(repeated.changed)


if __name__ == "__main__":
    unittest.main()
