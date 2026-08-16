from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from uuid import UUID
from unittest import mock


SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))


SKILL_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = SKILL_ROOT / "VERSION"
STANDARD_SCHEMA = SKILL_ROOT / "assets/schema/standard.schema.json"
JOURNAL_SCHEMA = SKILL_ROOT / "assets/schema/journal.schema.json"
MODEL_FILE = SKILL_ROOT / "scripts/coordinator_standard/model.py"


class ContractTests(unittest.TestCase):
    def test_version_and_standard_schema_are_pinned(self) -> None:
        self.assertTrue(VERSION_FILE.is_file(), "VERSION must exist")
        self.assertEqual("0.1.0\n", VERSION_FILE.read_text(encoding="utf-8"))
        self.assertTrue(STANDARD_SCHEMA.is_file(), "standard schema must exist")
        schema = json.loads(STANDARD_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(1, schema["properties"]["schema_version"]["const"])
        self.assertEqual(
            "0.1.0", schema["properties"]["standard_version"]["const"]
        )
        self.assertFalse(schema["additionalProperties"])
        forbidden = {"remote_url", "home", "worktree_path", "token", "secret"}
        self.assertTrue(forbidden.isdisjoint(schema["properties"]))

    def test_journal_schema_has_all_recorded_phases(self) -> None:
        self.assertTrue(JOURNAL_SCHEMA.is_file(), "journal schema must exist")
        schema = json.loads(JOURNAL_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(
            [
                "0.1.0",
                "3.0.0",
                "3.1.0",
                "3.2.0",
                "3.2.1",
                "3.2.2",
                "3.2.3",
                "3.2.4",
                "3.2.5",
                "3.2.6",
            ],
            schema["properties"]["standard_version"]["enum"],
        )
        values = schema["$defs"]["phase"]["enum"]
        self.assertEqual(
            ["inspect", "plan", "apply", "validate", "finalize"], values
        )
        required = set(schema["required"])
        self.assertTrue(
            {"authority", "repository_identity", "starting_git", "report_path"}
            <= required
        )

    def test_model_contract_is_importable(self) -> None:
        self.assertTrue(MODEL_FILE.is_file(), "model module must exist")
        spec = importlib.util.spec_from_file_location("coordinator_model", MODEL_FILE)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)


class MarkerTests(unittest.TestCase):
    def markers(self):
        module_file = SCRIPTS_ROOT / "coordinator_standard/markers.py"
        self.assertTrue(module_file.is_file(), "markers module must exist")
        return __import__("coordinator_standard.markers", fromlist=["markers"])

    def test_appends_one_managed_block_without_changing_custom_bytes(self) -> None:
        markers = self.markers()
        before = b"User preface\r\n\xff\xfe\r\nUser ending\r\n"
        after = markers.upsert_managed_block(
            before, b"Read docs/codex/PROJECT.md first.\n"
        )
        self.assertTrue(after.startswith(before))
        self.assertEqual(1, after.count(b"<!-- cody-coordinator:start"))
        self.assertEqual(1, after.count(b"<!-- cody-coordinator:end -->"))
        self.assertIn(b"\xff\xfe", after)

    def test_replaces_only_existing_managed_span(self) -> None:
        markers = self.markers()
        before = (
            b"custom-before\n"
            b"<!-- cody-coordinator:start standard=0.1.0 -->\n"
            b"old body\n"
            b"<!-- cody-coordinator:end -->\n"
            b"custom-after\n"
        )
        after = markers.upsert_managed_block(before, b"new body\n")
        self.assertEqual(
            b"custom-before\n"
            b"<!-- cody-coordinator:start standard=0.1.0 -->\n"
            b"new body\n"
            b"<!-- cody-coordinator:end -->\n"
            b"custom-after\n",
            after,
        )

    def test_duplicate_and_malformed_markers_fail_closed(self) -> None:
        markers = self.markers()
        cases = {
            "duplicate": (
                b"<!-- cody-coordinator:start standard=3.1.0 -->\n"
                b"<!-- cody-coordinator:start standard=3.1.0 -->\n"
                b"<!-- cody-coordinator:end -->\n"
                b"<!-- cody-coordinator:end -->\n"
            ),
            "missing-end": (
                b"<!-- cody-coordinator:start standard=3.1.0 -->\nbody\n"
            ),
            "end-first": (
                b"<!-- cody-coordinator:end -->\n"
                b"<!-- cody-coordinator:start standard=3.1.0 -->\n"
            ),
        }
        for label, content in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(markers.CoordinatorError):
                    markers.parse_managed_block(content)

    def test_bare_carriage_return_tail_remains_reparseable(self) -> None:
        markers = self.markers()
        before = b"custom text\r"
        rendered = markers.upsert_managed_block(before, b"managed\n")
        self.assertTrue(rendered.startswith(before + b"\n"))
        self.assertIsNotNone(markers.parse_managed_block(rendered))


class TemplateTests(unittest.TestCase):
    def templates(self):
        module_file = SCRIPTS_ROOT / "coordinator_standard/templates.py"
        self.assertTrue(module_file.is_file(), "templates module must exist")
        return __import__("coordinator_standard.templates", fromlist=["templates"])

    def inspection(self, repo: Path):
        from coordinator_standard.model import GitSnapshot, Inspection, RepoKind

        return Inspection(
            repo=repo,
            git=GitSnapshot(
                kind=RepoKind.ESTABLISHED_GIT,
                worktree=repo,
                git_dir=repo / ".git",
                common_dir=repo / ".git",
                main_worktree=repo,
                head="a" * 40,
                explicit_base="a" * 40,
                branch="main",
                is_detached=False,
                superproject=None,
                staged=(),
                unstaged=(),
                untracked=(),
                remote_identities=("example.test/org/repo.git",),
            ),
            applicable_instructions=("AGENTS.md",),
            installed_version=None,
            discovered_commands={
                "test": ("python3 -m unittest discover -v",),
                "build": ("python3 -m build",),
            },
            blockers=(),
        )

    def test_slug_validation_is_strict(self) -> None:
        templates = self.templates()
        self.assertEqual("project-one", templates.validate_project_slug("project-one"))
        for value in ("A Project", "-bad", "bad-", "a", "bad--slug", "ümlaut"):
            with self.subTest(value=value):
                with self.assertRaises(templates.CoordinatorError):
                    templates.validate_project_slug(value)

    def test_rendered_repository_contract_is_complete_and_deterministic(self) -> None:
        templates = self.templates()
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "AGENTS.md").write_bytes(b"custom instructions\n")
            inspection = self.inspection(repo)
            now = datetime(2026, 7, 9, 21, 0, tzinfo=timezone.utc)
            project_id = UUID("12345678-1234-5678-9234-567812345678")
            first = templates.render_new_project(
                inspection, "project-one", now, project_id
            )
            second = templates.render_new_project(
                inspection, "project-one", now, project_id
            )
            self.assertEqual(first, second)
            rendered = {
                operation.relative_path: operation.content
                for operation in first
                if operation.content is not None
            }
            self.assertEqual(
                {
                    "AGENTS.md",
                    "docs/codex/STANDARD.json",
                    "docs/codex/PROJECT.md",
                    "docs/codex/STATUS.md",
                    "docs/codex/ROADMAP.md",
                    "docs/codex/DECISIONS.md",
                    "docs/codex/WORK_ITEMS/.gitkeep",
                    "docs/codex/MIGRATIONS/.gitkeep",
                },
                set(rendered),
            )
            standard = json.loads(rendered["docs/codex/STANDARD.json"])
            self.assertEqual("12345678-1234-5678-9234-567812345678", standard["project_id"])
            self.assertEqual("project-one", standard["project_slug"])
            self.assertEqual("0.1.0", standard["standard_version"])
            self.assertIn(b"custom instructions\n", rendered["AGENTS.md"])

            required_headings = {
                "docs/codex/PROJECT.md": (
                    b"## Purpose",
                    b"## Repository map",
                    b"## Validation commands",
                    b"## Authority and risk",
                ),
                "docs/codex/STATUS.md": (
                    b"## Current exact identity and deploy truth",
                    b"## Active task IDs",
                    b"## Open P0/P1",
                    b"## Authority or decision blocker",
                    b"## One next action",
                ),
                "docs/codex/ROADMAP.md": (
                    b"## Now",
                    b"## Next",
                    b"## Later",
                    b"## Parked",
                ),
                "docs/codex/DECISIONS.md": (b"## Decisions",),
            }
            for path, headings in required_headings.items():
                for heading in headings:
                    self.assertIn(heading, rendered[path], f"{path}: {heading!r}")

            combined = b"\n".join(rendered.values())
            for forbidden in (
                b"$PROJECT",
                b"$STANDARD",
                b"/Users/",
                b"/Volumes/",
                b"<PROJECT",
            ):
                self.assertNotIn(forbidden, combined)

    def test_renderer_rejects_managed_symlinks(self) -> None:
        templates = self.templates()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            outside = root / "outside"
            repo.mkdir()
            outside.mkdir()
            (outside / "AGENTS.md").write_text("outside\n", encoding="utf-8")
            (repo / "AGENTS.md").symlink_to(outside / "AGENTS.md")
            with self.assertRaises(templates.CoordinatorError) as caught:
                templates.render_new_project(
                    self.inspection(repo),
                    "fixture-repo",
                    datetime(2026, 7, 9, 21, 0, tzinfo=timezone.utc),
                    UUID("12345678-1234-5678-9234-567812345678"),
                )
            self.assertEqual("path_symlink", caught.exception.blocker.code)

    def test_renderer_rejects_symlinked_managed_ancestor(self) -> None:
        templates = self.templates()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            outside = root / "outside"
            repo.mkdir()
            (outside / "codex").mkdir(parents=True)
            (outside / "codex/PROJECT.md").write_text(
                "outside project\n", encoding="utf-8"
            )
            (repo / "docs").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(templates.CoordinatorError) as caught:
                templates.render_new_project(
                    self.inspection(repo),
                    "fixture-repo",
                    datetime(2026, 7, 9, 21, 0, tzinfo=timezone.utc),
                    UUID("12345678-1234-5678-9234-567812345678"),
                )
            self.assertEqual("path_symlink", caught.exception.blocker.code)

    def test_existing_different_project_identity_blocks_render(self) -> None:
        templates = self.templates()
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            codex = repo / "docs/codex"
            codex.mkdir(parents=True)
            existing = {
                "schema_version": 1,
                "standard_name": "cody-coordinator",
                "standard_version": "3.1.0",
                "project_id": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
                "project_slug": "fixture-repo",
                "installed_at": "2026-07-09T21:00:00Z",
                "last_validated_at": "2026-07-09T21:00:00Z",
                "risk_profiles": [],
                "migrations": [],
            }
            (codex / "STANDARD.json").write_text(json.dumps(existing), encoding="utf-8")
            with self.assertRaises(templates.CoordinatorError) as caught:
                templates.render_new_project(
                    self.inspection(repo),
                    "fixture-repo",
                    datetime(2026, 7, 9, 21, 0, tzinfo=timezone.utc),
                    UUID("12345678-1234-5678-9234-567812345678"),
                )
            self.assertEqual("project_identity_collision", caught.exception.blocker.code)

    def test_custom_current_marker_does_not_claim_reconstructive_rollback(self) -> None:
        templates = self.templates()
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "AGENTS.md").write_bytes(
                b"<!-- cody-coordinator:start standard=0.1.0 -->\n"
                b"manually altered custom policy\n"
                b"<!-- cody-coordinator:end -->\n"
            )
            operations = templates.render_new_project(
                self.inspection(repo),
                "fixture-repo",
                datetime(2026, 7, 9, 21, 0, tzinfo=timezone.utc),
                UUID("12345678-1234-5678-9234-567812345678"),
            )
            agents = next(item for item in operations if item.relative_path == "AGENTS.md")
            self.assertEqual("unavailable", agents.reversal.kind)

    def test_agents_render_uses_one_snapshot_for_content_and_preimage(self) -> None:
        templates = self.templates()
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            agents_path = repo / "AGENTS.md"
            old = b"original instructions\n"
            new = b"concurrent user work\n"
            agents_path.write_bytes(old)
            real_read = templates.read_regular_file
            agents_reads = 0

            def racing_read(root: Path, target: Path):
                nonlocal agents_reads
                if target == agents_path:
                    agents_reads += 1
                    if agents_reads == 1:
                        value = real_read(root, target)
                        agents_path.write_bytes(new)
                        return value
                return real_read(root, target)

            with mock.patch.object(
                templates, "read_regular_file", side_effect=racing_read
            ):
                operations = templates.render_new_project(
                    self.inspection(repo),
                    "fixture-repo",
                    datetime(2026, 7, 9, 21, 0, tzinfo=timezone.utc),
                    UUID("12345678-1234-5678-9234-567812345678"),
                )
            agents = next(item for item in operations if item.relative_path == "AGENTS.md")
            self.assertEqual(1, agents_reads)
            self.assertEqual(
                __import__("hashlib").sha256(old).hexdigest(),
                agents.before_sha256,
            )
            self.assertTrue((agents.content or b"").startswith(old))

    def test_journal_path_patterns_reject_hostile_paths(self) -> None:
        schema = json.loads(JOURNAL_SCHEMA.read_text(encoding="utf-8"))
        relative = schema["$defs"]["relative_path"]
        pattern = re.compile(relative["pattern"])
        hostile = (
            "/absolute",
            "C:\\absolute",
            "..\\escape",
            "safe\\..\\escape",
            ".",
            "control\nname",
            "nul\x00name",
        )
        for value in hostile:
            with self.subTest(value=repr(value)):
                self.assertIsNone(pattern.fullmatch(value))
        self.assertIsNotNone(pattern.fullmatch("docs/codex/PROJECT.md"))
        self.assertEqual(
            "#/$defs/relative_path",
            schema["properties"]["report_path"]["$ref"],
        )

    def test_model_import_executes_and_frozen_mappings_are_immutable(self) -> None:
        import importlib
        from types import MappingProxyType
        from coordinator_standard.model import OperationResult, RepoKind

        module = importlib.import_module("coordinator_standard.model")
        self.assertEqual("manual-decision", module.RecoveryAction.MANUAL_DECISION.value)
        result = OperationResult(
            command="inspect",
            ok=True,
            changed=False,
            repository=".",
            repo_kind=RepoKind.EMPTY_NON_GIT,
            run_id=None,
            standard_version=None,
            metadata={"safe": True},
        )
        self.assertIsInstance(result.metadata, MappingProxyType)
        with self.assertRaises(TypeError):
            result.metadata["mutated"] = True


if __name__ == "__main__":
    unittest.main()
