from __future__ import annotations

import hashlib
import importlib
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from support import SCRIPTS_ROOT, initialize_git, run_git


SAFETY_FILE = SCRIPTS_ROOT / "coordinator_standard/safety.py"
GIT_STATE_FILE = SCRIPTS_ROOT / "coordinator_standard/git_state.py"


class ModuleMixin:
    def safety(self):
        self.assertTrue(SAFETY_FILE.is_file(), "safety module must exist")
        return importlib.import_module("coordinator_standard.safety")

    def git_state(self):
        self.assertTrue(GIT_STATE_FILE.is_file(), "git_state module must exist")
        return importlib.import_module("coordinator_standard.git_state")

    def assert_sensitive_absent(self, label: str, sensitive: str, actual: str) -> None:
        if sensitive in actual:
            fingerprint = hashlib.sha256(sensitive.encode("utf-8")).hexdigest()[:12]
            self.fail(f"{label} leaked sensitive sentinel sha256:{fingerprint}")


class SafetyTests(ModuleMixin, unittest.TestCase):
    def setUp(self) -> None:
        self.temp_context = tempfile.TemporaryDirectory()
        self.temp = Path(self.temp_context.name)
        self.repo = self.temp / "repo"
        self.repo.mkdir()

    def tearDown(self) -> None:
        self.temp_context.cleanup()

    def valid_lock_metadata(self) -> dict[str, object]:
        return {
            "run_id": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
            "host_id_sha256": "a" * 64,
            "pid": os.getpid(),
            "created_at": "2026-07-09T21:15:00Z",
            "journal_path": (
                "docs/codex/MIGRATIONS/20260709T211500Z-"
                "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee.journal.json"
            ),
        }

    def test_unsupported_native_mutation_fails_with_explicit_blocker(self) -> None:
        safety = self.safety()
        with mock.patch.object(safety, "secure_mutation_supported", return_value=False):
            with self.assertRaises(safety.CoordinatorError) as caught:
                safety.require_secure_mutation_support()
        self.assertEqual("unsupported_platform", caught.exception.blocker.code)

    def test_redaction_never_returns_remote_credentials(self) -> None:
        safety = self.safety()
        token = "gh" + "p_" + "0123456789abcdef0123456789abcdef"
        query = "private" + "-value-012345"
        raw = f"https://alice:{token}@example.test/org/repo.git?token={query}"
        shown = safety.redact_text(raw)
        self.assert_sensitive_absent("userinfo", "alice", shown)
        self.assert_sensitive_absent("token", token, shown)
        self.assert_sensitive_absent("query", query, shown)
        self.assertIn("example.test", shown)

    def test_redaction_covers_headers_assignments_and_scp_user(self) -> None:
        safety = self.safety()
        bearer = "bearer" + "-sentinel-0123456789"
        api_value = "api" + "-sentinel-0123456789"
        raw = (
            f"Authorization: Bearer {bearer}\n"
            f"api_key={api_value}\n"
            "build-user@example.test:org/repo.git"
        )
        shown = safety.redact_text(raw)
        self.assert_sensitive_absent("bearer", bearer, shown)
        self.assert_sensitive_absent("assignment", api_value, shown)
        self.assert_sensitive_absent("scp user", "build-user", shown)
        self.assertIn("example.test", shown)

    def test_redaction_covers_prefixed_environment_secret_names(self) -> None:
        safety = self.safety()
        sentinels = {
            "MY_API_KEY": "my-api-value-0123456789",
            "AWS_SECRET_ACCESS_KEY": "aws-secret-value-0123456789",
            "SLACK_BOT_TOKEN": "slack-secret-value-0123456789",
        }
        raw = "\n".join(f"{name}={value}" for name, value in sentinels.items())

        shown = safety.redact_text(raw)

        self.assertTrue(safety.contains_credential(raw))
        for name, value in sentinels.items():
            self.assertIn(name, shown)
            self.assert_sensitive_absent(name, value, shown)

    def test_redaction_covers_ssh_client_secret_and_quoted_values(self) -> None:
        safety = self.safety()
        user_secret = "ssh" + "-userinfo-secret-012345"
        path_secret = "gh" + "p_" + "fedcba9876543210fedcba9876543210"
        query_secret = "client" + "-secret-with-spaces"
        quoted_secret = "quoted" + " secret value with spaces"
        raw = (
            f"ssh://deploy:{user_secret}@example.test/org/{path_secret}/repo.git"
            f"?client_secret={query_secret}\npassword=\"{quoted_secret}\" trailing"
        )
        shown = safety.redact_text(raw)
        for label, value in (
            ("ssh userinfo", user_secret),
            ("token path", path_secret),
            ("client secret", query_secret),
            ("quoted assignment", quoted_secret),
        ):
            self.assert_sensitive_absent(label, value, shown)
        self.assertIn("example.test", shown)

    def test_containment_rejects_resolved_symlink_escape(self) -> None:
        safety = self.safety()
        outside = self.temp / "outside"
        outside.mkdir()
        (self.repo / "docs").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(safety.CoordinatorError) as caught:
            safety.assert_contained(self.repo, self.repo / "docs/codex/STATUS.md")
        self.assertEqual("path_symlink", caught.exception.blocker.code)

    def test_containment_rejects_in_repo_symlink_for_managed_write(self) -> None:
        safety = self.safety()
        actual = self.repo / "actual"
        actual.mkdir()
        (self.repo / "docs").symlink_to(actual, target_is_directory=True)
        with self.assertRaises(safety.CoordinatorError) as caught:
            safety.assert_contained(self.repo, self.repo / "docs/codex/STATUS.md")
        self.assertEqual("path_symlink", caught.exception.blocker.code)

    def test_atomic_write_preserves_mode_and_replaces_bytes(self) -> None:
        safety = self.safety()
        target = self.repo / "AGENTS.md"
        target.write_bytes(b"before\n")
        target.chmod(0o640)
        safety.atomic_write(target, b"after\n", root=self.repo, public=True)
        self.assertEqual(b"after\n", target.read_bytes())
        self.assertEqual(0o640, stat.S_IMODE(target.stat().st_mode))

    def test_atomic_write_expected_hash_rejects_same_parent_content_change(self) -> None:
        safety = self.safety()
        target = self.repo / "managed.txt"
        target.write_bytes(b"planned preimage\n")
        expected = hashlib.sha256(target.read_bytes()).hexdigest()

        def change_target(_path: Path) -> None:
            target.write_bytes(b"concurrent user bytes\n")

        with self.assertRaises(safety.CoordinatorError) as caught:
            safety.atomic_write(
                target,
                b"candidate\n",
                root=self.repo,
                public=True,
                before_replace=change_target,
                expected_sha256=expected,
            )

        self.assertEqual("concurrent_managed_change", caught.exception.blocker.code)
        self.assertEqual(b"concurrent user bytes\n", target.read_bytes())
        self.assertEqual([], list(self.repo.glob(".*.coordinator-tmp-*")))

    def test_atomic_write_rejects_ancestor_swap(self) -> None:
        safety = self.safety()
        docs = self.repo / "docs"
        docs.mkdir()
        outside = self.temp / "outside"
        outside.mkdir()

        def swap_parent(_target: Path) -> None:
            docs.rename(self.repo / "docs-original")
            (self.repo / "docs").symlink_to(outside, target_is_directory=True)

        with self.assertRaises(safety.CoordinatorError) as caught:
            safety.atomic_write(
                docs / "PROJECT.md",
                b"project\n",
                root=self.repo,
                public=True,
                before_replace=swap_parent,
            )
        self.assertEqual("path_race", caught.exception.blocker.code)
        self.assertFalse((outside / "PROJECT.md").exists())

    def test_atomic_write_never_follows_symlinked_parent(self) -> None:
        safety = self.safety()
        outside = self.temp / "outside"
        outside.mkdir()
        safe = self.repo / "safe"
        safe.mkdir()
        (safe / "redirect").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(safety.CoordinatorError) as caught:
            safety.atomic_write(
                safe / "redirect/escaped.txt",
                b"escape\n",
                public=True,
                root=self.repo,
            )
        self.assertEqual("path_symlink", caught.exception.blocker.code)
        self.assertFalse((outside / "escaped.txt").exists())

    def test_exclusive_lock_never_follows_symlinked_parent(self) -> None:
        safety = self.safety()
        outside = self.temp / "outside"
        outside.mkdir()
        (self.repo / "locks").symlink_to(outside, target_is_directory=True)
        lock = safety.ExclusiveRunLock(
            self.repo,
            self.repo / "locks/coordinator.lock",
            self.valid_lock_metadata(),
        )
        with self.assertRaises(safety.CoordinatorError) as caught:
            lock.acquire()
        self.assertEqual("path_symlink", caught.exception.blocker.code)
        self.assertFalse((outside / "coordinator.lock").exists())

    def test_atomic_write_rejects_root_swapped_between_lstat_and_open(self) -> None:
        safety = self.safety()
        original = self.temp / "repo-original"
        replacement = self.temp / "repo-replacement"
        real_open = safety.os.open
        swapped = False

        def swapping_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal swapped
            if dir_fd is None and Path(path) == self.repo and not swapped:
                swapped = True
                self.repo.rename(original)
                replacement.rename(self.repo)
            return real_open(path, flags, mode, dir_fd=dir_fd)

        replacement.mkdir()
        with mock.patch.object(safety.os, "open", side_effect=swapping_open):
            with self.assertRaises(safety.CoordinatorError) as caught:
                safety.atomic_write(
                    self.repo / "escaped.txt",
                    b"escape\n",
                    root=self.repo,
                    public=True,
                )
        self.assertEqual("path_race", caught.exception.blocker.code)
        self.assertFalse((self.repo / "escaped.txt").exists())

    def test_lock_rejects_sensitive_metadata_and_replacement_on_release(self) -> None:
        safety = self.safety()
        lock_path = self.repo / "coordinator.lock"
        token = "gh" + "p_" + "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        unsafe = safety.ExclusiveRunLock(
            self.repo,
            lock_path,
            {"run_id": "probe", "credential": token},
        )
        with self.assertRaises(safety.CoordinatorError) as caught:
            unsafe.acquire()
        self.assertEqual("unsafe_lock_metadata", caught.exception.blocker.code)
        self.assertFalse(lock_path.exists())

        lock = safety.ExclusiveRunLock(
            self.repo,
            lock_path,
            self.valid_lock_metadata(),
        )
        lock.acquire()
        lock_path.unlink()
        lock_path.write_text("replacement\n", encoding="utf-8")
        replacement_info = lock_path.stat()
        lock._lock_identity = (replacement_info.st_dev, replacement_info.st_ino)
        with self.assertRaises(safety.CoordinatorError) as replaced:
            lock.release()
        self.assertEqual("lock_identity_changed", replaced.exception.blocker.code)
        quarantined = list(self.repo.glob(".coordinator.lock.coordinator-release-*"))
        self.assertEqual(1, len(quarantined))
        self.assertEqual("replacement\n", quarantined[0].read_text(encoding="utf-8"))

    def test_lock_release_quarantines_a_last_moment_replacement(self) -> None:
        safety = self.safety()
        lock_path = self.repo / "coordinator.lock"
        lock = safety.ExclusiveRunLock(
            self.repo,
            lock_path,
            self.valid_lock_metadata(),
        )
        lock.acquire()
        real_rename = safety.os.rename

        def replace_then_rename(source, destination, **kwargs):
            lock_path.unlink()
            lock_path.write_text("last-moment replacement\n", encoding="utf-8")
            return real_rename(source, destination, **kwargs)

        with mock.patch.object(safety.os, "rename", side_effect=replace_then_rename):
            with self.assertRaises(safety.CoordinatorError) as caught:
                lock.release()

        self.assertEqual("lock_identity_changed", caught.exception.blocker.code)
        quarantined = list(self.repo.glob(".coordinator.lock.coordinator-release-*"))
        self.assertEqual(1, len(quarantined))
        self.assertEqual(
            "last-moment replacement\n", quarantined[0].read_text(encoding="utf-8")
        )

    def test_stale_lock_replacement_is_hash_bound_and_exclusive(self) -> None:
        safety = self.safety()
        lock_path = self.repo / "coordinator.lock"
        stale = b"proven stale lock\n"
        lock_path.write_bytes(stale)
        lock = safety.ExclusiveRunLock(
            self.repo,
            lock_path,
            self.valid_lock_metadata(),
        )
        with self.assertRaises(safety.CoordinatorError) as caught:
            lock.replace_stale("0" * 64)
        self.assertEqual("concurrent_managed_change", caught.exception.blocker.code)
        self.assertEqual(stale, lock_path.read_bytes())

        lock.replace_stale(hashlib.sha256(stale).hexdigest())
        with self.assertRaises(safety.CoordinatorError):
            safety.ExclusiveRunLock(
                self.repo,
                lock_path,
                self.valid_lock_metadata(),
            ).acquire()
        lock.release()
        self.assertFalse(lock_path.exists())

    def test_held_lock_detects_visible_parent_replacement(self) -> None:
        safety = self.safety()
        migrations = self.repo / "migrations"
        migrations.mkdir()
        lock_path = migrations / "coordinator.lock"
        first = safety.ExclusiveRunLock(
            self.repo, lock_path, self.valid_lock_metadata()
        )
        first.acquire()
        moved = self.repo / "migrations-moved"
        migrations.rename(moved)
        migrations.mkdir()
        second = safety.ExclusiveRunLock(
            self.repo, lock_path, self.valid_lock_metadata()
        )
        second.acquire()

        with self.assertRaises(safety.CoordinatorError) as caught:
            first.assert_visible()

        self.assertEqual("lock_parent_changed", caught.exception.blocker.code)
        second.release()
        first.release()

    def test_lock_metadata_requires_exact_typed_safe_fields(self) -> None:
        safety = self.safety()
        cases = (
            {},
            {**self.valid_lock_metadata(), "run_id": "not-a-uuid"},
            {**self.valid_lock_metadata(), "host_id_sha256": "host-name"},
            {**self.valid_lock_metadata(), "pid": 0},
            {**self.valid_lock_metadata(), "created_at": "yesterday"},
            {
                **self.valid_lock_metadata(),
                "journal_path": "docs\\codex\\..\\escape.journal.json",
            },
        )
        for index, metadata in enumerate(cases):
            with self.subTest(metadata_keys=sorted(metadata)):
                lock_path = self.repo / f"coordinator-{index}.lock"
                lock = safety.ExclusiveRunLock(self.repo, lock_path, metadata)
                with self.assertRaises(safety.CoordinatorError) as caught:
                    lock.acquire()
                self.assertEqual("unsafe_lock_metadata", caught.exception.blocker.code)
                self.assertFalse(lock_path.exists())


class GitStateTests(ModuleMixin, unittest.TestCase):
    def setUp(self) -> None:
        self.temp_context = tempfile.TemporaryDirectory()
        self.temp = Path(self.temp_context.name)

    def tearDown(self) -> None:
        self.temp_context.cleanup()

    def test_classifies_empty_and_nonempty_non_git(self) -> None:
        model = importlib.import_module("coordinator_standard.model")
        git_state = self.git_state()
        empty = self.temp / "empty"
        empty.mkdir()
        self.assertEqual(model.RepoKind.EMPTY_NON_GIT, git_state.inspect_git(empty).kind)
        nonempty = self.temp / "nonempty"
        nonempty.mkdir()
        (nonempty / "app.txt").write_text("app\n", encoding="utf-8")
        self.assertEqual(
            model.RepoKind.NONEMPTY_NON_GIT, git_state.inspect_git(nonempty).kind
        )

    def test_classifies_unborn_established_bare_and_linked(self) -> None:
        model = importlib.import_module("coordinator_standard.model")
        git_state = self.git_state()
        unborn = self.temp / "unborn"
        initialize_git(unborn, commit=False)
        self.assertEqual(model.RepoKind.UNBORN_GIT, git_state.inspect_git(unborn).kind)

        established = self.temp / "established"
        initialize_git(established, commit=True)
        self.assertEqual(
            model.RepoKind.ESTABLISHED_GIT, git_state.inspect_git(established).kind
        )

        linked = self.temp / "linked"
        run_git(established, "worktree", "add", "--quiet", "-b", "linked-test", str(linked))
        linked_snapshot = git_state.inspect_git(linked)
        self.assertEqual(model.RepoKind.LINKED_WORKTREE, linked_snapshot.kind)
        self.assertEqual("linked-test", linked_snapshot.branch)
        self.assertEqual(established.resolve(), linked_snapshot.main_worktree)

        bare = self.temp / "bare.git"
        bare.mkdir()
        run_git(bare, "init", "--quiet", "--bare")
        self.assertEqual(model.RepoKind.BARE_GIT, git_state.inspect_git(bare).kind)

    def test_remote_credentials_are_not_retained(self) -> None:
        git_state = self.git_state()
        repo = self.temp / "repo"
        initialize_git(repo, commit=True)
        token = "gh" + "p_" + "abcdef0123456789abcdef0123456789"
        raw = f"https://alice:{token}@example.test/org/repo.git?token=private-value"
        run_git(repo, "remote", "add", "origin", raw)
        snapshot = git_state.inspect_git(repo)
        rendered = repr(snapshot.remote_identities)
        self.assert_sensitive_absent("remote token", token, rendered)
        self.assert_sensitive_absent("remote user", "alice", rendered)
        self.assert_sensitive_absent("remote query", "private-value", rendered)
        self.assertEqual(("example.test/org/repo.git",), snapshot.remote_identities)

    def test_remote_identity_never_retains_secret_or_control_path_content(self) -> None:
        git_state = self.git_state()
        repo = self.temp / "repo"
        initialize_git(repo, commit=True)
        token = "gh" + "p_" + "13579bdf2468ace013579bdf2468ace0"
        raw = f"ssh://deploy@example.test/org/{token}/line%0Abreak.git"
        run_git(repo, "remote", "add", "origin", raw)
        rendered = repr(git_state.inspect_git(repo).remote_identities)
        self.assert_sensitive_absent("remote path token", token, rendered)
        self.assertNotIn("\n", rendered)
        self.assertNotIn("\r", rendered)

    def test_git_directory_symlink_is_rejected(self) -> None:
        git_state = self.git_state()
        source = self.temp / "source"
        initialize_git(source, commit=True)
        target = self.temp / "target"
        target.mkdir()
        (target / ".git").symlink_to(source / ".git", target_is_directory=True)
        with self.assertRaises(git_state.CoordinatorError) as caught:
            git_state.inspect_git(target)
        self.assertEqual("unsafe_git_metadata", caught.exception.blocker.code)

    def test_git_file_cannot_redirect_to_unregistered_worktree(self) -> None:
        git_state = self.git_state()
        source = self.temp / "source"
        initialize_git(source, commit=True)
        target = self.temp / "target"
        target.mkdir()
        (target / ".git").write_text(
            f"gitdir: {(source / '.git').resolve()}\n", encoding="utf-8"
        )
        with self.assertRaises(git_state.CoordinatorError) as caught:
            git_state.inspect_git(target)
        self.assertEqual("unsafe_git_metadata", caught.exception.blocker.code)

    def test_nested_directory_is_not_classified_as_safe_non_git(self) -> None:
        git_state = self.git_state()
        outer = self.temp / "outer"
        initialize_git(outer, commit=True)
        nested = outer / "nested"
        nested.mkdir()
        with self.assertRaises(git_state.CoordinatorError) as caught:
            git_state.inspect_git(nested)
        self.assertEqual("nested_repository_boundary", caught.exception.blocker.code)

    def test_repository_selecting_environment_is_blocked(self) -> None:
        git_state = self.git_state()
        repo = self.temp / "repo"
        initialize_git(repo, commit=True)
        old = os.environ.get("GIT_DIR")
        os.environ["GIT_DIR"] = str(self.temp / "redirect")
        try:
            with self.assertRaises(git_state.CoordinatorError) as caught:
                git_state.inspect_git(repo)
        finally:
            if old is None:
                os.environ.pop("GIT_DIR", None)
            else:
                os.environ["GIT_DIR"] = old
        self.assertEqual("git_environment_override", caught.exception.blocker.code)

    def test_all_repository_selecting_environment_names_are_blocked(self) -> None:
        git_state = self.git_state()
        repo = self.temp / "repo"
        initialize_git(repo, commit=True)
        names = (
            "GIT_WORK_TREE",
            "GIT_INDEX_FILE",
            "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            "GIT_CEILING_DIRECTORIES",
            "GIT_CONFIG_COUNT",
        )
        for name in names:
            with self.subTest(name=name):
                old = os.environ.get(name)
                os.environ[name] = "unsafe-value"
                try:
                    with self.assertRaises(git_state.CoordinatorError):
                        git_state.inspect_git(repo)
                finally:
                    if old is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = old

    def test_status_parser_preserves_both_sides_of_staged_rename(self) -> None:
        git_state = self.git_state()
        data = b"R  docs/codex/PROJECT-new.md\0docs/codex/PROJECT.md\0"
        staged, unstaged, untracked = git_state._parse_status(data)
        self.assertEqual(
            ("docs/codex/PROJECT-new.md", "docs/codex/PROJECT.md"), staged
        )
        self.assertEqual((), unstaged)
        self.assertEqual((), untracked)

    def test_repo_fsmonitor_is_not_executed_and_index_is_not_rewritten(self) -> None:
        git_state = self.git_state()
        repo = self.temp / "repo"
        initialize_git(repo, commit=True)
        sentinel = self.temp / "fsmonitor-ran"
        hook = self.temp / "fsmonitor-hook"
        hook.write_text(f"#!/bin/sh\ntouch '{sentinel}'\nexit 0\n", encoding="utf-8")
        hook.chmod(0o755)
        run_git(repo, "config", "core.fsmonitor", str(hook))
        index = Path(run_git(repo, "rev-parse", "--git-path", "index").stdout.decode().strip())
        if not index.is_absolute():
            index = repo / index
        before = (index.read_bytes(), index.stat().st_mtime_ns)
        git_state.inspect_git(repo)
        after = (index.read_bytes(), index.stat().st_mtime_ns)
        self.assertFalse(sentinel.exists())
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
