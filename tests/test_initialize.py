from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from support import SCRIPTS_ROOT, initialize_git, run_git, tree_hash


OPERATIONS_FILE = SCRIPTS_ROOT / "coordinator_standard/operations.py"


class InitializeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_context = tempfile.TemporaryDirectory()
        self.temp = Path(self.temp_context.name)

    def tearDown(self) -> None:
        self.temp_context.cleanup()

    def operations(self):
        self.assertTrue(OPERATIONS_FILE.is_file(), "operations module must exist")
        return importlib.import_module("coordinator_standard.operations")

    def test_check_mode_on_empty_folder_writes_nothing(self) -> None:
        operations = self.operations()
        repo = self.temp / "empty-project"
        repo.mkdir()
        before = tree_hash(repo)
        result = operations.initialize(repo, check=True)
        self.assertTrue(result.ok)
        self.assertTrue(result.changed)
        self.assertEqual(before, tree_hash(repo))
        self.assertFalse((repo / ".git").exists())
        self.assertFalse((repo / "docs").exists())

    def test_empty_folder_initializes_without_commit_and_is_idempotent(self) -> None:
        operations = self.operations()
        repo = self.temp / "empty-project"
        repo.mkdir()
        result = operations.initialize(repo, check=False)
        self.assertTrue(result.ok, result.blockers)
        self.assertTrue(result.changed)
        self.assertTrue((repo / ".git").is_dir())
        head = run_git(repo, "rev-parse", "--verify", "HEAD", check=False)
        self.assertNotEqual(0, head.returncode)
        self.assertTrue((repo / "AGENTS.md").is_file())
        self.assertTrue((repo / "docs/codex/STANDARD.json").is_file())
        journals = sorted((repo / "docs/codex/MIGRATIONS").glob("*.journal.json"))
        reports = sorted((repo / "docs/codex/MIGRATIONS").glob("*.report.md"))
        self.assertEqual(1, len(journals))
        self.assertEqual(1, len(reports))
        journal = json.loads(journals[0].read_text(encoding="utf-8"))
        self.assertEqual("complete", journal["status"])
        self.assertEqual(
            ["inspect", "plan", "apply", "validate", "finalize"],
            [entry["phase"] for entry in journal["phase_history"]],
        )
        standard = json.loads(
            (repo / "docs/codex/STANDARD.json").read_text(encoding="utf-8")
        )
        self.assertEqual(result.run_id, standard["migrations"][0]["run_id"])

        before = tree_hash(repo, excluded_names={".git"})
        journal_count = len(journals)
        second = operations.initialize(repo, check=False)
        self.assertTrue(second.ok)
        self.assertFalse(second.changed)
        self.assertEqual(before, tree_hash(repo, excluded_names={".git"}))
        self.assertEqual(
            journal_count,
            len(list((repo / "docs/codex/MIGRATIONS").glob("*.journal.json"))),
        )

    def test_nonempty_non_git_requires_and_binds_boundary_decision(self) -> None:
        operations = self.operations()
        repo = self.temp / "existing-project"
        repo.mkdir()
        product = repo / "app.txt"
        product.write_text("product\n", encoding="utf-8")
        product_hash = hashlib.sha256(product.read_bytes()).hexdigest()
        check = operations.initialize(repo, check=True)
        self.assertFalse(check.ok)
        self.assertEqual("repository_boundary_decision_required", check.blockers[0].code)
        token = check.metadata["repository_boundary_token"]
        self.assertFalse((repo / ".git").exists())
        applied = operations.initialize(
            repo,
            check=False,
            repository_boundary_token=token,
        )
        self.assertTrue(applied.ok, applied.blockers)
        self.assertEqual(product_hash, hashlib.sha256(product.read_bytes()).hexdigest())

    def test_changed_non_git_inventory_invalidates_boundary_token(self) -> None:
        operations = self.operations()
        repo = self.temp / "existing-project"
        repo.mkdir()
        product = repo / "app.txt"
        product.write_text("one\n", encoding="utf-8")
        token = operations.initialize(repo, check=True).metadata[
            "repository_boundary_token"
        ]
        product.write_text("two\n", encoding="utf-8")
        result = operations.initialize(
            repo,
            check=False,
            repository_boundary_token=token,
        )
        self.assertFalse(result.ok)
        self.assertEqual("repository_boundary_token_stale", result.blockers[0].code)
        self.assertFalse((repo / ".git").exists())

    def test_non_git_setup_never_overwrites_preexisting_coordinator_target(self) -> None:
        operations = self.operations()
        repo = self.temp / "existing-target-project"
        target = repo / "docs/codex/PROJECT.md"
        target.parent.mkdir(parents=True)
        original = b"# User-owned project notes\n\nDo not replace me.\n"
        target.write_bytes(original)

        boundary = operations.initialize(repo, check=True)
        self.assertEqual(
            "repository_boundary_decision_required", boundary.blockers[0].code
        )
        result = operations.initialize(
            repo,
            check=False,
            repository_boundary_token=boundary.metadata["repository_boundary_token"],
        )

        self.assertFalse(result.ok)
        self.assertEqual("existing_coordinator_target", result.blockers[0].code)
        self.assertEqual(original, target.read_bytes())
        self.assertFalse((repo / ".git").exists())
        self.assertFalse((repo / "docs/codex/MIGRATIONS").exists())

    def test_ignored_existing_coordinator_target_is_preserved_and_blocks(self) -> None:
        operations = self.operations()
        repo = self.temp / "ignored-target-project"
        initialize_git(repo, commit=True)
        (repo / ".gitignore").write_text("docs/codex/PROJECT.md\n", encoding="utf-8")
        run_git(repo, "add", ".gitignore")
        run_git(repo, "commit", "--quiet", "-m", "ignore generated project")
        target = repo / "docs/codex/PROJECT.md"
        target.parent.mkdir(parents=True)
        original = b"ignored but user-owned\n"
        target.write_bytes(original)

        result = operations.initialize(repo, check=False)

        self.assertFalse(result.ok)
        self.assertEqual("existing_coordinator_target", result.blockers[0].code)
        self.assertEqual(original, target.read_bytes())
        self.assertFalse((repo / "docs/codex/MIGRATIONS").exists())

    def test_partial_failed_run_reports_change_and_blocks_retry(self) -> None:
        operations = self.operations()
        model = importlib.import_module("coordinator_standard.model")
        repo = self.temp / "partial-failure-project"
        initialize_git(repo, commit=True)
        original_apply = operations.apply_operations

        def fail_after_first(repo_path, planned, journal):
            first = next(item for item in planned if item.content is not None)
            operations.atomic_write(
                repo_path / first.relative_path,
                first.content,
                root=repo_path,
                public=True,
                expected_sha256=first.before_sha256,
            )
            journal.record_file_write(
                first.relative_path, first.before_sha256, first.after_sha256
            )
            raise model.CoordinatorError(
                model.Blocker(
                    "forced_interruption",
                    "A test interruption occurred.",
                    "Run reconcile.",
                )
            )

        with mock.patch.object(operations, "apply_operations", fail_after_first):
            result = operations.initialize(repo, check=False)

        self.assertFalse(result.ok)
        self.assertTrue(result.changed)
        self.assertTrue(result.operations)
        journals = list((repo / "docs/codex/MIGRATIONS").glob("*.journal.json"))
        self.assertEqual(1, len(journals))
        failed = json.loads(journals[0].read_text(encoding="utf-8"))
        self.assertEqual("failed", failed["status"])
        self.assertTrue((repo / failed["report_path"]).is_file())

        retry = operations.initialize(repo, check=False)
        self.assertFalse(retry.ok)
        self.assertEqual("incomplete_prior_run", retry.blockers[0].code)
        self.assertIs(operations.apply_operations, original_apply)

        picture = operations.reconcile(repo)
        record = picture.metadata["runs"][0]
        self.assertNotIn("rollback", record["safe_actions"])
        repaired = operations.recover_run(
            repo,
            run_id=record["run_id"],
            action=model.RecoveryAction.REPAIR,
            decision_token=record["decision_tokens"]["repair"],
        )
        self.assertTrue(repaired.ok, repaired.blockers)
        completed = operations.initialize(repo, check=True)
        self.assertTrue(completed.ok, completed.blockers)
        self.assertFalse(completed.changed)

    def test_unborn_git_stays_unborn(self) -> None:
        operations = self.operations()
        repo = self.temp / "unborn-project"
        initialize_git(repo, commit=False)
        result = operations.initialize(repo, check=False)
        self.assertTrue(result.ok, result.blockers)
        self.assertNotEqual(
            0,
            run_git(repo, "rev-parse", "--verify", "HEAD", check=False).returncode,
        )

    def test_unrelated_dirty_product_work_proceeds_unchanged(self) -> None:
        operations = self.operations()
        repo = self.temp / "dirty-project"
        initialize_git(repo, commit=True)
        readme = repo / "README.md"
        readme.write_text("user work\n", encoding="utf-8")
        before = readme.read_bytes()
        result = operations.initialize(repo, check=False)
        self.assertTrue(result.ok, result.blockers)
        self.assertEqual(before, readme.read_bytes())
        status = run_git(repo, "status", "--porcelain=v1").stdout.decode()
        self.assertIn("README.md", status)

    def test_dirty_managed_overlap_blocks_before_journal(self) -> None:
        operations = self.operations()
        repo = self.temp / "overlap-project"
        initialize_git(repo, commit=True)
        agents = repo / "AGENTS.md"
        agents.write_text("original\n", encoding="utf-8")
        run_git(repo, "add", "AGENTS.md")
        run_git(repo, "commit", "--quiet", "-m", "add instructions")
        agents.write_text("user edit\n", encoding="utf-8")
        before = agents.read_bytes()
        result = operations.initialize(repo, check=False)
        self.assertFalse(result.ok)
        self.assertEqual("dirty_overlap", result.blockers[0].code)
        self.assertEqual(before, agents.read_bytes())
        self.assertFalse((repo / "docs/codex/MIGRATIONS").exists())

    def test_custom_agents_content_survives(self) -> None:
        operations = self.operations()
        repo = self.temp / "custom-agents-project"
        initialize_git(repo, commit=True)
        agents = repo / "AGENTS.md"
        custom = b"Custom rule: preserve this byte-for-byte.\n"
        agents.write_bytes(custom)
        run_git(repo, "add", "AGENTS.md")
        run_git(repo, "commit", "--quiet", "-m", "add instructions")
        result = operations.initialize(repo, check=False)
        self.assertTrue(result.ok, result.blockers)
        rendered = agents.read_bytes()
        self.assertTrue(rendered.startswith(custom))
        self.assertEqual(1, rendered.count(b"<!-- cody-coordinator:start"))

    def test_git_init_ignores_configured_template_hooks(self) -> None:
        operations = self.operations()
        repo = self.temp / "template-project"
        repo.mkdir()
        fake_home = self.temp / "home"
        template = self.temp / "malicious-template"
        hooks = template / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "post-checkout").write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
        fake_home.mkdir()
        (fake_home / ".gitconfig").write_text(
            f"[init]\n\ttemplateDir = {template}\n", encoding="utf-8"
        )
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(fake_home)
        try:
            result = operations.initialize(repo, check=False)
        finally:
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home
        self.assertTrue(result.ok, result.blockers)
        self.assertFalse((repo / ".git/hooks/post-checkout").exists())

    def test_repository_root_symlink_is_rejected_without_mutation(self) -> None:
        operations = self.operations()
        real = self.temp / "real-project"
        real.mkdir()
        link = self.temp / "linked-project"
        link.symlink_to(real, target_is_directory=True)

        result = operations.initialize(link, check=False)

        self.assertFalse(result.ok)
        self.assertEqual("repository_root_symlink", result.blockers[0].code)
        self.assertEqual([], list(real.iterdir()))


if __name__ == "__main__":
    unittest.main()
