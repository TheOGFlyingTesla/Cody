from __future__ import annotations

from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from uuid import UUID, getnode

from support import SCRIPTS_ROOT, initialize_git, run_git


INSPECTOR_FILE = SCRIPTS_ROOT / "coordinator_standard/inspector.py"
JOURNAL_FILE = SCRIPTS_ROOT / "coordinator_standard/journal.py"


class ModuleMixin:
    def inspector(self):
        self.assertTrue(INSPECTOR_FILE.is_file(), "inspector module must exist")
        return importlib.import_module("coordinator_standard.inspector")

    def journal(self):
        self.assertTrue(JOURNAL_FILE.is_file(), "journal module must exist")
        return importlib.import_module("coordinator_standard.journal")


class InspectorTests(ModuleMixin, unittest.TestCase):
    def setUp(self) -> None:
        self.temp_context = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_context.name) / "repo"
        initialize_git(self.repo, commit=True)

    def tearDown(self) -> None:
        self.temp_context.cleanup()

    def test_discovers_instructions_and_commands_without_execution(self) -> None:
        inspector = self.inspector()
        (self.repo / "AGENTS.md").write_text("custom instructions\n", encoding="utf-8")
        package = {
            "scripts": {
                "test": "touch SHOULD_NOT_RUN",
                "lint": "eslint .",
                "typecheck": "tsc --noEmit",
                "build": "next build",
            }
        }
        (self.repo / "package.json").write_text(
            json.dumps(package), encoding="utf-8"
        )
        (self.repo / "Package.swift").write_text(
            "// swift-tools-version: 6.0\n", encoding="utf-8"
        )
        result = inspector.inspect_repository(self.repo)
        self.assertEqual(("AGENTS.md",), result.applicable_instructions)
        self.assertEqual(("npm test", "swift test"), result.discovered_commands["test"])
        self.assertEqual(("npm run lint",), result.discovered_commands["lint"])
        self.assertEqual(
            ("npm run typecheck",), result.discovered_commands["typecheck"]
        )
        self.assertEqual(
            ("npm run build", "swift build"), result.discovered_commands["build"]
        )
        self.assertFalse((self.repo / "SHOULD_NOT_RUN").exists())

    def test_current_and_malformed_standard_are_distinguished(self) -> None:
        inspector = self.inspector()
        codex = self.repo / "docs/codex"
        codex.mkdir(parents=True)
        standard = {
            "schema_version": 1,
            "standard_name": "cody-coordinator",
            "standard_version": "3.1.0",
            "project_id": "12345678-1234-5678-9234-567812345678",
            "project_slug": "fixture-repo",
            "installed_at": "2026-07-09T21:00:00Z",
            "last_validated_at": "2026-07-09T21:00:00Z",
            "risk_profiles": [],
            "migrations": [],
        }
        path = codex / "STANDARD.json"
        path.write_text(json.dumps(standard), encoding="utf-8")
        self.assertEqual("3.1.0", inspector.inspect_repository(self.repo).installed_version)
        path.write_text("{broken", encoding="utf-8")
        malformed = inspector.inspect_repository(self.repo)
        self.assertIsNone(malformed.installed_version)
        self.assertEqual("malformed_standard", malformed.blockers[0].code)


class ValidatorSubsetTests(unittest.TestCase):
    def validator(self):
        return importlib.import_module("coordinator_standard.validator")

    def test_schema_subset_rejects_unsupported_invalid_and_cyclic_constructs(self) -> None:
        validator = self.validator()
        cases = (
            ({"type": "string", "minProperties": 1}, "value"),
            ({"type": "string", "pattern": "["}, "value"),
            ({"type": "string", "format": "hostname"}, "value"),
            ({"$defs": {"loop": {"$ref": "#/$defs/loop"}}, "$ref": "#/$defs/loop"}, "value"),
            ({"$ref": "https://example.test/schema"}, "value"),
        )
        for schema, value in cases:
            with self.subTest(schema=schema):
                self.assertTrue(validator.validate_json(value, schema))

    def test_strict_json_rejects_duplicate_keys_and_bool_as_integer(self) -> None:
        validator = self.validator()
        with self.assertRaises(validator.DuplicateJsonKey):
            validator.strict_json_loads('{"run_id": 1, "run_id": 2}')
        self.assertTrue(validator.validate_json(True, {"type": "integer"}))
        self.assertFalse(
            validator.validate_json(None, {"type": ["string", "null"]})
        )


class JournalTests(ModuleMixin, unittest.TestCase):
    def setUp(self) -> None:
        self.temp_context = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_context.name) / "repo"
        initialize_git(self.repo, commit=True)
        self.now = datetime(2026, 7, 9, 21, 15, tzinfo=timezone.utc)
        self.run_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        self.project_id = UUID("12345678-1234-5678-9234-567812345678")

    def tearDown(self) -> None:
        self.temp_context.cleanup()

    def inspection(self):
        return self.inspector().inspect_repository(self.repo)

    def authority(self):
        model = importlib.import_module("coordinator_standard.model")
        return model.AuthorityGrant(
            command="init",
            mutation_classes=("coordinator-layer",),
            allowed_paths=("AGENTS.md", "docs/codex/"),
            decisions=(),
            created_at="2026-07-09T21:15:00Z",
            source_id="current-task:user-request",
        )

    def test_journal_creation_is_path_safe_and_records_authority(self) -> None:
        journal_module = self.journal()
        run = journal_module.RunJournal.create(
            self.repo,
            self.run_id,
            "init",
            self.inspection(),
            self.authority(),
            self.project_id,
            now=self.now,
        )
        data = json.loads(run.path.read_text(encoding="utf-8"))
        self.assertEqual("fresh", data["status"])
        self.assertEqual("current-task:user-request", data["authority"]["source_id"])
        serialized = json.dumps(data)
        self.assertNotIn(str(self.repo), serialized)
        self.assertNotIn("/Users/", serialized)
        self.assertEqual([], data["planned_operations"])
        self.assertRegex(
            run.path.name,
            r"^20260709T211500Z-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee\.journal\.json$",
        )

    def test_phase_order_and_plan_attachment_are_enforced(self) -> None:
        journal_module = self.journal()
        model = importlib.import_module("coordinator_standard.model")
        run = journal_module.RunJournal.create(
            self.repo,
            self.run_id,
            "init",
            self.inspection(),
            self.authority(),
            self.project_id,
            now=self.now,
        )
        with self.assertRaises(model.CoordinatorError):
            run.transition(model.Phase.PLAN, {"unexpected": True}, now=self.now)
        run.transition(model.Phase.INSPECT, {"repo_kind": "established-git"}, now=self.now)
        operation = model.Operation(
            action="create",
            relative_path="docs/codex/PROJECT.md",
            before_sha256=None,
            after_sha256="b" * 64,
            content=b"project\n",
            reversal=model.ReversalEvidence("delete-new", None),
        )
        run.record_plan((operation,), now=self.now)
        run.transition(model.Phase.PLAN, {"operation_count": 1}, now=self.now)
        data = json.loads(run.path.read_text(encoding="utf-8"))
        self.assertEqual(1, len(data["planned_operations"]))
        self.assertNotIn("content", data["planned_operations"][0])
        self.assertEqual(["inspect", "plan"], [item["phase"] for item in data["phase_history"]])

    def test_incomplete_run_is_found_and_classified(self) -> None:
        journal_module = self.journal()
        model = importlib.import_module("coordinator_standard.model")
        run = journal_module.RunJournal.create(
            self.repo,
            self.run_id,
            "init",
            self.inspection(),
            self.authority(),
            self.project_id,
            now=self.now,
        )
        run.transition(model.Phase.INSPECT, {}, now=self.now)
        found = journal_module.find_incomplete_runs(self.repo)
        self.assertEqual((run.path,), found)
        reconciliation = journal_module.classify_run(self.repo, run.path)
        self.assertEqual(model.RunStatus.IN_PROGRESS, reconciliation.status)
        self.assertEqual(model.RecoveryAction.ROLLBACK, reconciliation.recommended_action)
        self.assertNotIn(model.RecoveryAction.RESUME, reconciliation.safe_actions)
        self.assertIn(model.RecoveryAction.ROLLBACK, reconciliation.safe_actions)

    def test_mid_apply_state_is_not_mislabeled_resumable(self) -> None:
        journal_module = self.journal()
        model = importlib.import_module("coordinator_standard.model")
        run = journal_module.RunJournal.create(
            self.repo,
            self.run_id,
            "init",
            self.inspection(),
            self.authority(),
            self.project_id,
            now=self.now,
        )
        contents = {
            "docs/codex/one.md": b"one\n",
            "docs/codex/two.md": b"two\n",
        }
        operations = tuple(
            model.Operation(
                action="create",
                relative_path=relative,
                before_sha256=None,
                after_sha256=__import__("hashlib").sha256(content).hexdigest(),
                content=content,
                reversal=model.ReversalEvidence("delete-new", None),
            )
            for relative, content in contents.items()
        )
        run.transition(model.Phase.INSPECT, {}, now=self.now)
        run.record_plan(operations, now=self.now)
        run.transition(model.Phase.PLAN, {"operation_count": 2}, now=self.now)
        first = self.repo / "docs/codex/one.md"
        first.parent.mkdir(parents=True, exist_ok=True)
        first.write_bytes(contents["docs/codex/one.md"])
        run.record_file_write(
            operations[0].relative_path,
            operations[0].before_sha256,
            operations[0].after_sha256,
            now=self.now,
        )

        reconciliation = journal_module.classify_run(self.repo, run.path)

        self.assertNotIn(model.RecoveryAction.RESUME, reconciliation.safe_actions)
        self.assertNotIn(model.RecoveryAction.ROLLBACK, reconciliation.safe_actions)
        self.assertEqual(model.RecoveryAction.REPAIR, reconciliation.recommended_action)
        claims = [item["claim"] for item in reconciliation.evidence]
        self.assertIn("operation:docs/codex/one.md:applied", claims)
        self.assertIn("operation:docs/codex/two.md:pending", claims)


class DoctorAndRecoveryTests(ModuleMixin, unittest.TestCase):
    def setUp(self) -> None:
        self.temp_context = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_context.name) / "doctor-project"
        self.repo.mkdir()
        self.operations = importlib.import_module("coordinator_standard.operations")
        initialized = self.operations.initialize(self.repo, check=False)
        self.assertTrue(initialized.ok, initialized.blockers)

    def tearDown(self) -> None:
        self.temp_context.cleanup()

    def installed_project_id(self) -> UUID:
        data = json.loads(
            (self.repo / "docs/codex/STANDARD.json").read_text(encoding="utf-8")
        )
        return UUID(data["project_id"])

    def test_doctor_and_check_current_accept_valid_installation(self) -> None:
        doctor = self.operations.doctor(self.repo)
        self.assertTrue(doctor.ok, doctor.validation)
        self.assertFalse(doctor.changed)
        current = self.operations.check_current(self.repo)
        self.assertTrue(current.ok)
        self.assertFalse(current.changed)
        self.assertTrue(current.metadata["current"])

    def test_doctor_preserves_user_owned_absolute_path_outside_managed_block(self) -> None:
        agents = self.repo / "AGENTS.md"
        custom_prefix = (
            b"Project root remains /Users/example/custom-project.\n"
            b"Keep the literal $PROJECT_NOTE instruction unchanged.\n"
        )
        expected = custom_prefix + agents.read_bytes()
        agents.write_bytes(expected)

        doctor = self.operations.doctor(self.repo)

        self.assertTrue(doctor.ok, doctor.validation)
        self.assertEqual(expected, agents.read_bytes())

    def test_doctor_rejects_absolute_path_inside_managed_block(self) -> None:
        agents = self.repo / "AGENTS.md"
        current = agents.read_bytes()
        agents.write_bytes(
            current.replace(
                b"Choose the smallest safe orientation tier",
                b"Choose the smallest safe orientation tier from /Users/example/private",
                1,
            )
        )

        doctor = self.operations.doctor(self.repo)

        self.assertFalse(doctor.ok)
        self.assertTrue(
            any(
                check["name"] == "personal-or-absolute-path:AGENTS.md"
                and not check["ok"]
                for check in doctor.validation
            )
        )

    def test_doctor_still_scans_user_owned_agents_content_for_credentials(self) -> None:
        token = "gh" + "p_" + "0123456789abcdef0123456789abcdef"
        agents = self.repo / "AGENTS.md"
        agents.write_bytes(f"API_KEY={token}\n".encode() + agents.read_bytes())

        doctor = self.operations.doctor(self.repo)

        self.assertFalse(doctor.ok)
        self.assertNotIn(token, repr(doctor))
        self.assertTrue(
            any(
                check["name"] == "credential-content:AGENTS.md"
                and not check["ok"]
                for check in doctor.validation
            )
        )

    def test_doctor_rejects_missing_sections_duplicate_markers_and_paths(self) -> None:
        status = self.repo / "docs/codex/STATUS.md"
        status.write_text("# Coordinator Status\n", encoding="utf-8")
        missing = self.operations.doctor(self.repo)
        self.assertFalse(missing.ok)
        self.assertTrue(
            any(check["name"] == "required-sections:STATUS.md" and not check["ok"] for check in missing.validation)
        )
        current = self.operations.check_current(self.repo)
        self.assertFalse(current.ok)
        self.assertFalse(current.metadata["current"])

        agents = self.repo / "AGENTS.md"
        agents.write_bytes(
            agents.read_bytes()
            + b"<!-- cody-coordinator:start standard=3.1.0 -->\n"
            + b"duplicate\n<!-- cody-coordinator:end -->\n"
        )
        duplicate = self.operations.doctor(self.repo)
        self.assertFalse(duplicate.ok)
        self.assertTrue(
            any(check["name"] == "managed-marker-integrity" and not check["ok"] for check in duplicate.validation)
        )

        journal = next((self.repo / "docs/codex/MIGRATIONS").glob("*.journal.json"))
        data = json.loads(journal.read_text(encoding="utf-8"))
        data["report_path"] = "/Users/example/private-report.md"
        journal.write_text(json.dumps(data), encoding="utf-8")
        hostile = self.operations.doctor(self.repo)
        self.assertFalse(hostile.ok)
        self.assertTrue(
            any(check["name"].startswith("journal-schema:") and not check["ok"] for check in hostile.validation)
        )

    def test_doctor_rejects_credential_content_without_echoing_it(self) -> None:
        token = "gh" + "p_" + "0123456789abcdef0123456789abcdef"
        project = self.repo / "docs/codex/PROJECT.md"
        project.write_text(project.read_text(encoding="utf-8") + f"\nAPI_KEY={token}\n", encoding="utf-8")
        hostile_journal = (
            self.repo
            / "docs/codex/MIGRATIONS"
            / f"CUSTOM-{token}.journal.json"
        )
        hostile_journal.write_text("{}\n", encoding="utf-8")
        result = self.operations.doctor(self.repo)
        self.assertFalse(result.ok)
        self.assertNotIn(token, repr(result))
        self.assertTrue(
            any(check["name"] == "credential-content:PROJECT.md" and not check["ok"] for check in result.validation)
        )

    def test_reconcile_is_read_only_and_labels_native_metadata_unavailable(self) -> None:
        model = importlib.import_module("coordinator_standard.model")
        journal_module = self.journal()
        inspection = self.inspector().inspect_repository(self.repo)
        authority = model.AuthorityGrant(
            command="repair",
            mutation_classes=("coordinator-layer",),
            allowed_paths=("docs/codex/PROJECT.md",),
            decisions=(),
            created_at="2026-07-09T22:00:00Z",
            source_id="current-task:user-request",
        )
        run_id = "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"
        run = journal_module.RunJournal.create(
            self.repo,
            run_id,
            "repair",
            inspection,
            authority,
            self.installed_project_id(),
            now=datetime(2026, 7, 9, 22, 0, tzinfo=timezone.utc),
        )
        run.transition(model.Phase.INSPECT, {}, now=datetime(2026, 7, 9, 22, 0, tzinfo=timezone.utc))
        before = run.path.read_bytes()
        result = self.operations.reconcile(self.repo)
        self.assertTrue(result.ok)
        self.assertFalse(result.changed)
        self.assertEqual(before, run.path.read_bytes())
        self.assertIn("native task metadata unavailable", " ".join(result.warnings).lower())
        self.assertTrue(result.metadata["runs"])
        self.assertEqual("in-progress", result.metadata["runs"][0]["status"])
        picture = result.metadata["operating_picture"]
        self.assertEqual("present", picture["durable_status"]["state"])
        self.assertTrue(picture["durable_status"]["sections"])
        self.assertTrue(picture["git"]["worktrees"])
        self.assertIn("branches", picture["git"])
        evidence = {item["claim"]: item["status"] for item in picture["evidence"]}
        self.assertEqual("verified", evidence["git:worktrees"])
        self.assertEqual("unknown", evidence["native-tasks:unavailable"])

    def test_guarded_rollback_deletes_only_matching_new_file(self) -> None:
        model = importlib.import_module("coordinator_standard.model")
        journal_module = self.journal()
        inspection = self.inspector().inspect_repository(self.repo)
        target = self.repo / (
            "docs/codex/MIGRATIONS/20260709T220500Z-"
            "cccccccc-dddd-4eee-8fff-aaaaaaaaaaaa.report.md"
        )
        content = b"created by interrupted run\n"
        operation = model.Operation(
            action="create",
            relative_path=(
                "docs/codex/MIGRATIONS/20260709T220500Z-"
                "cccccccc-dddd-4eee-8fff-aaaaaaaaaaaa.report.md"
            ),
            before_sha256=None,
            after_sha256=__import__("hashlib").sha256(content).hexdigest(),
            content=content,
            reversal=model.ReversalEvidence("delete-new", None),
        )
        authority = model.AuthorityGrant(
            command="repair",
            mutation_classes=("coordinator-layer",),
            allowed_paths=(
                "docs/codex/MIGRATIONS/20260709T220500Z-"
                "cccccccc-dddd-4eee-8fff-aaaaaaaaaaaa.report.md",
            ),
            decisions=(),
            created_at="2026-07-09T22:05:00Z",
            source_id="current-task:user-request",
        )
        run_id = "cccccccc-dddd-4eee-8fff-aaaaaaaaaaaa"
        moment = datetime(2026, 7, 9, 22, 5, tzinfo=timezone.utc)
        run = journal_module.RunJournal.create(
            self.repo,
            run_id,
            "repair",
            inspection,
            authority,
            self.installed_project_id(),
            now=moment,
        )
        run.transition(model.Phase.INSPECT, {}, now=moment)
        run.record_plan((operation,), now=moment)
        run.transition(model.Phase.PLAN, {"operation_count": 1}, now=moment)
        target.write_bytes(content)
        run.record_file_write(
            operation.relative_path,
            operation.before_sha256,
            operation.after_sha256,
            now=moment,
        )
        run.transition(model.Phase.APPLY, {"written_files": 1}, now=moment)
        picture = self.operations.reconcile(self.repo)
        record = next(item for item in picture.metadata["runs"] if item["run_id"] == run_id)
        token = record["decision_tokens"]["rollback"]
        result = self.operations.recover_run(
            self.repo,
            run_id=run_id,
            action=model.RecoveryAction.ROLLBACK,
            decision_token=token,
        )
        self.assertTrue(result.ok, result.blockers)
        self.assertTrue(result.changed)
        self.assertTrue(target.exists())
        self.assertIn("rollback", target.read_text(encoding="utf-8").lower())
        final = json.loads(run.path.read_text(encoding="utf-8"))
        self.assertEqual("superseded", final["status"])

    def test_guarded_rollback_removes_only_inserted_agents_block(self) -> None:
        model = importlib.import_module("coordinator_standard.model")
        journal_module = self.journal()
        original_block = (self.repo / "AGENTS.md").read_bytes()
        before = b"# User instructions\n"
        after = before + original_block
        (self.repo / "AGENTS.md").write_bytes(after)
        run_id = "abababab-1111-4aaa-8bbb-abababababab"
        operation = model.Operation(
            action="replace",
            relative_path="AGENTS.md",
            before_sha256=__import__("hashlib").sha256(before).hexdigest(),
            after_sha256=__import__("hashlib").sha256(after).hexdigest(),
            content=after,
            reversal=model.ReversalEvidence(
                "remove-inserted-block",
                None,
                (("before_sha256", __import__("hashlib").sha256(before).hexdigest()),),
            ),
        )
        moment = datetime(2026, 7, 9, 22, 6, tzinfo=timezone.utc)
        authority = model.AuthorityGrant(
            command="repair",
            mutation_classes=("coordinator-layer",),
            allowed_paths=("AGENTS.md",),
            decisions=(),
            created_at="2026-07-09T22:06:00Z",
            source_id="current-task:user-request",
        )
        run = journal_module.RunJournal.create(
            self.repo,
            run_id,
            "repair",
            self.inspector().inspect_repository(self.repo),
            authority,
            self.installed_project_id(),
            now=moment,
        )
        run.transition(model.Phase.INSPECT, {}, now=moment)
        run.record_plan((operation,), now=moment)
        run.transition(model.Phase.PLAN, {"operation_count": 1}, now=moment)
        run.record_file_write("AGENTS.md", operation.before_sha256, operation.after_sha256, now=moment)
        run.transition(model.Phase.APPLY, {"written_files": 1}, now=moment)
        record = next(
            item
            for item in self.operations.reconcile(self.repo).metadata["runs"]
            if item["run_id"] == run_id
        )

        result = self.operations.recover_run(
            self.repo,
            run_id=run_id,
            action=model.RecoveryAction.ROLLBACK,
            decision_token=record["decision_tokens"]["rollback"],
        )

        self.assertTrue(result.ok, result.blockers)
        self.assertEqual(before, (self.repo / "AGENTS.md").read_bytes())

    def test_guarded_rollback_restores_clean_tracked_preimage(self) -> None:
        model = importlib.import_module("coordinator_standard.model")
        journal_module = self.journal()
        run_git(self.repo, "add", ".")
        run_git(self.repo, "commit", "--quiet", "-m", "coordinator baseline")
        inspection = self.inspector().inspect_repository(self.repo)
        before = (self.repo / "docs/codex/ROADMAP.md").read_bytes()
        after = before + b"\nTemporary interrupted change.\n"
        run_id = "cdcdcdcd-2222-4bbb-8ccc-cdcdcdcdcdcd"
        before_hash = __import__("hashlib").sha256(before).hexdigest()
        operation = model.Operation(
            action="replace",
            relative_path="docs/codex/ROADMAP.md",
            before_sha256=before_hash,
            after_sha256=__import__("hashlib").sha256(after).hexdigest(),
            content=after,
            reversal=model.ReversalEvidence(
                "restore-git-base",
                inspection.git.head,
                (("before_sha256", before_hash),),
            ),
        )
        moment = datetime(2026, 7, 9, 22, 7, tzinfo=timezone.utc)
        authority = model.AuthorityGrant(
            command="repair",
            mutation_classes=("coordinator-layer",),
            allowed_paths=("docs/codex/ROADMAP.md",),
            decisions=(),
            created_at="2026-07-09T22:07:00Z",
            source_id="current-task:user-request",
        )
        run = journal_module.RunJournal.create(
            self.repo,
            run_id,
            "repair",
            inspection,
            authority,
            self.installed_project_id(),
            now=moment,
        )
        run.transition(model.Phase.INSPECT, {}, now=moment)
        run.record_plan((operation,), now=moment)
        run.transition(model.Phase.PLAN, {"operation_count": 1}, now=moment)
        (self.repo / operation.relative_path).write_bytes(after)
        run.record_file_write(operation.relative_path, before_hash, operation.after_sha256, now=moment)
        run.transition(model.Phase.APPLY, {"written_files": 1}, now=moment)
        record = next(
            item
            for item in self.operations.reconcile(self.repo).metadata["runs"]
            if item["run_id"] == run_id
        )

        result = self.operations.recover_run(
            self.repo,
            run_id=run_id,
            action=model.RecoveryAction.ROLLBACK,
            decision_token=record["decision_tokens"]["rollback"],
        )

        self.assertTrue(result.ok, result.blockers)
        self.assertEqual(before, (self.repo / operation.relative_path).read_bytes())

    def test_fully_applied_run_can_resume_to_valid_completion(self) -> None:
        model = importlib.import_module("coordinator_standard.model")
        journal_module = self.journal()
        inspection = self.inspector().inspect_repository(self.repo)
        run_id = "dddddddd-eeee-4fff-8aaa-bbbbbbbbbbbb"
        relative = (
            "docs/codex/MIGRATIONS/20260709T221000Z-"
            f"{run_id}.report.md"
        )
        target = self.repo / relative
        content = b"fully applied recovery candidate\n"
        operation = model.Operation(
            action="create",
            relative_path=relative,
            before_sha256=None,
            after_sha256=__import__("hashlib").sha256(content).hexdigest(),
            content=content,
            reversal=model.ReversalEvidence("delete-new", None),
        )
        authority = model.AuthorityGrant(
            command="repair",
            mutation_classes=("coordinator-layer",),
            allowed_paths=(relative,),
            decisions=(),
            created_at="2026-07-09T22:10:00Z",
            source_id="current-task:user-request",
        )
        moment = datetime(2026, 7, 9, 22, 10, tzinfo=timezone.utc)
        run = journal_module.RunJournal.create(
            self.repo,
            run_id,
            "repair",
            inspection,
            authority,
            self.installed_project_id(),
            now=moment,
        )
        run.transition(model.Phase.INSPECT, {}, now=moment)
        run.record_plan((operation,), now=moment)
        run.transition(model.Phase.PLAN, {"operation_count": 1}, now=moment)
        target.write_bytes(content)
        run.record_file_write(relative, None, operation.after_sha256, now=moment)
        run.record_post_apply(inspection, now=moment)
        run.transition(model.Phase.APPLY, {"written_files": 1}, now=moment)

        result = self.operations.recover_run(
            self.repo, run_id=run_id, action=model.RecoveryAction.RESUME
        )

        self.assertTrue(result.ok, result.blockers)
        final = json.loads(run.path.read_text(encoding="utf-8"))
        self.assertEqual("complete", final["status"])
        self.assertEqual(
            ["inspect", "plan", "apply", "validate", "finalize"],
            [item["phase"] for item in final["phase_history"]],
        )
        self.assertTrue(self.operations.doctor(self.repo).ok)

    def test_supersede_requires_action_specific_current_token(self) -> None:
        model = importlib.import_module("coordinator_standard.model")
        journal_module = self.journal()
        inspection = self.inspector().inspect_repository(self.repo)
        run_id = "eeeeeeee-ffff-4aaa-8bbb-cccccccccccc"
        authority = model.AuthorityGrant(
            command="repair",
            mutation_classes=("coordinator-layer",),
            allowed_paths=(),
            decisions=(),
            created_at="2026-07-09T22:15:00Z",
            source_id="current-task:user-request",
        )
        run = journal_module.RunJournal.create(
            self.repo,
            run_id,
            "repair",
            inspection,
            authority,
            self.installed_project_id(),
            now=datetime(2026, 7, 9, 22, 15, tzinfo=timezone.utc),
        )
        run.transition(
            model.Phase.INSPECT,
            {},
            now=datetime(2026, 7, 9, 22, 15, tzinfo=timezone.utc),
        )
        picture = self.operations.reconcile(self.repo)
        record = next(item for item in picture.metadata["runs"] if item["run_id"] == run_id)
        supersede_token = record["decision_tokens"]["supersede"]
        repair_token = record["decision_tokens"]["repair"]

        missing = self.operations.recover_run(
            self.repo, run_id=run_id, action=model.RecoveryAction.SUPERSEDE
        )
        swapped = self.operations.recover_run(
            self.repo,
            run_id=run_id,
            action=model.RecoveryAction.SUPERSEDE,
            decision_token=repair_token,
        )
        self.assertEqual("recovery_decision_required", missing.blockers[0].code)
        self.assertEqual("recovery_decision_required", swapped.blockers[0].code)
        self.assertEqual("in-progress", json.loads(run.path.read_text())["status"])

        completed = self.operations.recover_run(
            self.repo,
            run_id=run_id,
            action=model.RecoveryAction.SUPERSEDE,
            decision_token=supersede_token,
        )
        self.assertTrue(completed.ok, completed.blockers)
        self.assertEqual("superseded", json.loads(run.path.read_text())["status"])

    def test_journal_free_stale_lock_can_be_token_superseded(self) -> None:
        model = importlib.import_module("coordinator_standard.model")
        sentinel = "gh" + "p_abcdef0123456789abcdef0123456789"
        run_git(self.repo, "checkout", "--quiet", "-b", f"feature/{sentinel}")
        renamed = self.repo.parent / sentinel
        self.repo.rename(renamed)
        self.repo = renamed
        run_id = "12345678-aaaa-4bbb-8ccc-123456789abc"
        journal_relative = (
            "docs/codex/MIGRATIONS/20260709T223500Z-"
            f"{run_id}.journal.json"
        )
        lock = self.repo / "docs/codex/MIGRATIONS/.coordinator.lock"
        lock.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "host_id_sha256": __import__("hashlib").sha256(
                        str(getnode()).encode("ascii")
                    ).hexdigest(),
                    "pid": 2147483647,
                    "created_at": "2026-07-09T22:35:00Z",
                    "journal_path": journal_relative,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

        picture = self.operations.reconcile(self.repo)
        lock_picture = picture.metadata["lock"]
        self.assertEqual(["supersede"], lock_picture["safe_actions"])
        token = lock_picture["decision_tokens"]["supersede"]

        missing = self.operations.recover_run(
            self.repo, run_id=run_id, action=model.RecoveryAction.SUPERSEDE
        )
        self.assertEqual("recovery_decision_required", missing.blockers[0].code)
        completed = self.operations.recover_run(
            self.repo,
            run_id=run_id,
            action=model.RecoveryAction.SUPERSEDE,
            decision_token=token,
        )

        self.assertTrue(completed.ok, completed.blockers)
        self.assertFalse(lock.exists())
        journal = self.repo / journal_relative
        self.assertEqual("superseded", json.loads(journal.read_text())["status"])
        self.assertNotIn(sentinel, journal.read_text(encoding="utf-8"))
        self.assertNotIn(sentinel, repr(completed))
        self.assertTrue((self.repo / journal_relative.replace(".journal.json", ".report.md")).is_file())
        self.assertTrue(self.operations.doctor(self.repo).ok)

    def test_hostile_journals_cannot_expand_rollback_targets(self) -> None:
        model = importlib.import_module("coordinator_standard.model")
        journal_module = self.journal()
        inspection = self.inspector().inspect_repository(self.repo)
        targets = (
            "src/product-data.txt",
            "docs/codex/PROJECT_PROFILE.md",
            "docs/codex/WORK_ITEMS/WI-user-owned.md",
        )
        for index, relative in enumerate(targets, start=1):
            with self.subTest(relative=relative):
                target = self.repo / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                content = f"user-owned-{index}\n".encode()
                target.write_bytes(content)
                digest = __import__("hashlib").sha256(content).hexdigest()
                run_id = f"{index:08x}-1111-4aaa-8bbb-{index:012x}"
                authority = model.AuthorityGrant(
                    command="repair",
                    mutation_classes=("coordinator-layer",),
                    allowed_paths=(relative,),
                    decisions=(),
                    created_at="2026-07-09T22:20:00Z",
                    source_id="current-task:user-request",
                )
                run = journal_module.RunJournal.create(
                    self.repo,
                    run_id,
                    "repair",
                    inspection,
                    authority,
                    self.installed_project_id(),
                    now=datetime(2026, 7, 9, 22, 20 + index, tzinfo=timezone.utc),
                )
                operation = model.Operation(
                    action="create",
                    relative_path=relative,
                    before_sha256=None,
                    after_sha256=digest,
                    content=content,
                    reversal=model.ReversalEvidence("delete-new", None),
                )
                run.transition(model.Phase.INSPECT, {})
                run.record_plan((operation,))
                run.transition(model.Phase.PLAN, {"operation_count": 1})
                run.record_file_write(relative, None, digest)
                run.transition(model.Phase.APPLY, {"written_files": 1})

                result = self.operations.recover_run(
                    self.repo,
                    run_id=run_id,
                    action=model.RecoveryAction.ROLLBACK,
                )

                self.assertFalse(result.ok)
                self.assertEqual("invalid_recovery_journal", result.blockers[0].code)
                self.assertEqual(content, target.read_bytes())

    def test_forged_create_receipt_cannot_delete_existing_agents(self) -> None:
        model = importlib.import_module("coordinator_standard.model")
        journal_module = self.journal()
        inspection = self.inspector().inspect_repository(self.repo)
        agents = self.repo / "AGENTS.md"
        original = agents.read_bytes()
        digest = __import__("hashlib").sha256(original).hexdigest()
        run_id = "ffffffff-1111-4aaa-8bbb-dddddddddddd"
        authority = model.AuthorityGrant(
            command="repair",
            mutation_classes=("coordinator-layer",),
            allowed_paths=("AGENTS.md",),
            decisions=(),
            created_at="2026-07-09T22:30:00Z",
            source_id="current-task:user-request",
        )
        run = journal_module.RunJournal.create(
            self.repo,
            run_id,
            "repair",
            inspection,
            authority,
            self.installed_project_id(),
            now=datetime(2026, 7, 9, 22, 30, tzinfo=timezone.utc),
        )
        operation = model.Operation(
            action="create",
            relative_path="AGENTS.md",
            before_sha256=None,
            after_sha256=digest,
            content=original,
            reversal=model.ReversalEvidence("delete-new", None),
        )
        run.transition(model.Phase.INSPECT, {})
        run.record_plan((operation,))
        run.transition(model.Phase.PLAN, {"operation_count": 1})
        run.record_file_write("AGENTS.md", None, digest)
        run.transition(model.Phase.APPLY, {"written_files": 1})

        picture = self.operations.reconcile(self.repo)
        record = next(item for item in picture.metadata["runs"] if item["run_id"] == run_id)
        self.assertNotIn("rollback", record["safe_actions"])
        recovered = self.operations.recover_run(
            self.repo, run_id=run_id, action=model.RecoveryAction.ROLLBACK
        )
        self.assertFalse(recovered.ok)
        self.assertEqual(original, agents.read_bytes())


if __name__ == "__main__":
    unittest.main()
