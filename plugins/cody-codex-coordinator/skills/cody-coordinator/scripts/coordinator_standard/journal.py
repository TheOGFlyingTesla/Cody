"""Atomic coordinator run journals and recovery classification."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from uuid import UUID

from . import SCHEMA_VERSION, STANDARD_NAME, STANDARD_VERSION
from .git_state import read_tracked_preimage
from .inspector import inspect_repository
from .markers import parse_managed_block
from .model import (
    AuthorityGrant,
    Blocker,
    CoordinatorError,
    EvidenceStatus,
    Inspection,
    JournalGitEvidence,
    LockState,
    Operation,
    Phase,
    Reconciliation,
    RecoveryAction,
    RunStatus,
)
from .safety import (
    atomic_write,
    ensure_directory,
    read_regular_file,
    redact_text,
    sha256_bytes,
)


ALLOWED_NEXT: dict[Phase | None, Phase | None] = {
    None: Phase.INSPECT,
    Phase.INSPECT: Phase.PLAN,
    Phase.PLAN: Phase.APPLY,
    Phase.APPLY: Phase.VALIDATE,
    Phase.VALIDATE: Phase.FINALIZE,
    Phase.FINALIZE: None,
}
_RESOLVED = {RunStatus.COMPLETE.value, RunStatus.SUPERSEDED.value}
_ROLLBACK_FIXED = {
    "AGENTS.md",
    "docs/codex/STANDARD.json",
    "docs/codex/PROJECT.md",
    "docs/codex/STATUS.md",
    "docs/codex/ROADMAP.md",
    "docs/codex/DECISIONS.md",
    "docs/codex/WORK_ITEMS/.gitkeep",
    "docs/codex/MIGRATIONS/.gitkeep",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        raise CoordinatorError(
            Blocker(
                "naive_timestamp",
                "Journal timestamps must include a timezone.",
                "Use a timezone-aware UTC timestamp.",
            )
        )
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _path_identity(path: Path | None) -> str | None:
    if path is None:
        return None
    info = path.stat()
    return hashlib.sha256(f"{info.st_dev}:{info.st_ino}".encode("ascii")).hexdigest()


def _is_managed(path: str) -> bool:
    return path == "AGENTS.md" or path.startswith("docs/codex/")


def journal_git_evidence(inspection: Inspection) -> JournalGitEvidence:
    git = inspection.git
    return JournalGitEvidence(
        kind=git.kind.value,
        head=git.head,
        explicit_base=git.explicit_base,
        branch=redact_text(git.branch) if git.branch else None,
        is_detached=git.is_detached,
        worktree_identity_sha256=_path_identity(git.worktree),
        common_dir_identity_sha256=_path_identity(git.common_dir),
        staged_managed_paths=tuple(
            redact_text(path) for path in git.staged if _is_managed(path)
        ),
        unstaged_managed_paths=tuple(
            redact_text(path) for path in git.unstaged if _is_managed(path)
        ),
        untracked_managed_paths=tuple(
            redact_text(path) for path in git.untracked if _is_managed(path)
        ),
    )


def terminal_journal_candidate(
    *,
    run_id: str,
    command: str,
    starting: Inspection,
    post_apply: Inspection,
    authority: AuthorityGrant,
    project_id: UUID,
    project_slug: str | None,
    operations: tuple[Operation, ...],
    validation: tuple[dict[str, Any], ...],
    report_path: str,
    report_sha256: str,
    now: datetime,
    source_files: dict[str, tuple[str, str]] | None = None,
) -> tuple[str, bytes]:
    """Render the exact terminal journal shape for candidate-overlay doctor."""

    timestamp = _utc_text(now)
    data: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "standard_name": STANDARD_NAME,
        "standard_version": STANDARD_VERSION,
        "run_id": run_id,
        "command": command,
        "created_at": timestamp,
        "updated_at": timestamp,
        "repository_identity": _repository_identity(starting, project_id),
        "authority": _authority(authority),
        "starting_git": asdict(journal_git_evidence(starting)),
        "post_apply_git": asdict(journal_git_evidence(post_apply)),
        "source_files": [
            {
                "relative_path": relative,
                "sha256": digest,
                "disposition": disposition,
            }
            for relative, (digest, disposition) in sorted((source_files or {}).items())
        ],
        "planned_operations": [_operation(operation) for operation in operations],
        "phase_history": [
            {"phase": phase.value, "at": timestamp, "evidence": []}
            for phase in (
                Phase.INSPECT,
                Phase.PLAN,
                Phase.APPLY,
                Phase.VALIDATE,
                Phase.FINALIZE,
            )
        ],
        "file_hashes": [
            {
                "relative_path": operation.relative_path,
                "before_sha256": operation.before_sha256,
                "after_sha256": operation.after_sha256,
            }
            for operation in operations
            if operation.action != "git-init" and operation.after_sha256 is not None
        ],
        "validation": [dict(check) for check in validation],
        "report_path": report_path,
        "report_sha256": report_sha256,
        "status": RunStatus.COMPLETE.value,
        "next_action": "Continue normal coordination.",
    }
    if project_slug is not None:
        data["project_slug"] = project_slug
    journal_path = report_path.replace(".report.md", ".journal.json")
    content = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return journal_path, content


def _repository_identity(inspection: Inspection, project_id: UUID) -> dict[str, Any]:
    git = inspection.git
    identity_material = {
        "project_id": str(project_id),
        "basename": redact_text(inspection.repo.name),
        "worktree": _path_identity(git.worktree),
        "common_dir": _path_identity(git.common_dir),
        "remotes": list(git.remote_identities),
    }
    canonical = json.dumps(identity_material, sort_keys=True, separators=(",", ":"))
    return {
        "project_id": str(project_id),
        "fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "provisional": inspection.installed_version is None,
        "basename": redact_text(inspection.repo.name),
    }


def _authority(value: AuthorityGrant) -> dict[str, Any]:
    return {
        "command": value.command,
        "mutation_classes": list(value.mutation_classes),
        "allowed_paths": list(value.allowed_paths),
        "decisions": [
            {"name": name, "evidence_sha256": evidence}
            for name, evidence in value.decisions
        ],
        "created_at": value.created_at,
        "source_id": value.source_id,
    }


def _reversal(operation: Operation) -> dict[str, Any]:
    return {
        "kind": operation.reversal.kind,
        "reference": operation.reversal.reference,
        "metadata": [
            {"name": name, "value": value}
            for name, value in operation.reversal.metadata
        ],
    }


def _operation(operation: Operation) -> dict[str, Any]:
    return {
        "action": operation.action,
        "relative_path": operation.relative_path,
        "before_sha256": operation.before_sha256,
        "after_sha256": operation.after_sha256,
        "reversal": _reversal(operation),
    }


def _safe_evidence(evidence: dict[str, Any]) -> list[str]:
    rendered: list[str] = []
    for key, value in sorted(evidence.items()):
        text = redact_text(json.dumps(value, sort_keys=True, ensure_ascii=False))
        if text.startswith('"/') or "/Users/" in text or "/Volumes/" in text:
            text = '"[path-redacted]"'
        rendered.append(f"{key}={text}")
    return rendered


class RunJournal:
    def __init__(
        self,
        repo: Path,
        path: Path,
        data: dict[str, Any],
        visibility_guard: Callable[[], None] | None = None,
    ):
        self.repo = repo
        self.path = path
        self.data = data
        self.visibility_guard = visibility_guard

    @classmethod
    def create(
        cls,
        repo: Path,
        run_id: str,
        command: str,
        inspection: Inspection,
        authority: AuthorityGrant,
        project_id: UUID,
        *,
        now: datetime | None = None,
        visibility_guard: Callable[[], None] | None = None,
        project_slug: str | None = None,
    ) -> "RunJournal":
        moment = now or _utc_now()
        timestamp = _utc_text(moment)
        migrations = repo / "docs/codex/MIGRATIONS"
        ensure_directory(repo, migrations)
        filename_timestamp = moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = migrations / f"{filename_timestamp}-{run_id}.journal.json"
        report_path = (
            f"docs/codex/MIGRATIONS/{filename_timestamp}-{run_id}.report.md"
        )
        evidence = asdict(journal_git_evidence(inspection))
        data: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "standard_name": STANDARD_NAME,
            "standard_version": STANDARD_VERSION,
            "run_id": run_id,
            "command": command,
            "created_at": timestamp,
            "updated_at": timestamp,
            "repository_identity": _repository_identity(inspection, project_id),
            "authority": _authority(authority),
            "starting_git": evidence,
            "post_apply_git": evidence,
            "source_files": [],
            "planned_operations": [],
            "phase_history": [],
            "file_hashes": [],
            "validation": [],
            "report_path": report_path,
            "report_sha256": "",
            "status": RunStatus.FRESH.value,
            "next_action": "Continue with inspect phase.",
        }
        if project_slug is not None:
            data["project_slug"] = project_slug
        journal = cls(repo, path, data, visibility_guard)
        journal._write(create=True)
        return journal

    @classmethod
    def load(cls, repo: Path, path: Path) -> "RunJournal":
        content = read_regular_file(repo, path, max_bytes=4 * 1024 * 1024)
        if content is None:
            raise FileNotFoundError(path.name)
        data = json.loads(content)
        return cls(repo, path, data)

    def _write(self, *, create: bool = False) -> None:
        if self.visibility_guard is not None:
            self.visibility_guard()
        content = (json.dumps(self.data, indent=2, sort_keys=True) + "\n").encode("utf-8")
        if create:
            atomic_write(
                self.path,
                content,
                root=self.repo,
                public=False,
                expected_sha256=None,
            )
        else:
            atomic_write(self.path, content, root=self.repo, public=False)

    def assert_lock_visible(self) -> None:
        if self.visibility_guard is not None:
            self.visibility_guard()

    def transition(
        self,
        phase: Phase,
        evidence: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> None:
        history = self.data["phase_history"]
        current = Phase(history[-1]["phase"]) if history else None
        if ALLOWED_NEXT[current] is not phase:
            raise CoordinatorError(
                Blocker(
                    "invalid_phase_transition",
                    f"Cannot transition from {current.value if current else 'fresh'} to {phase.value}.",
                    "Reconcile the journal and resume only from its recorded next phase.",
                    (self.path.name,),
                )
            )
        if phase is Phase.PLAN and not self.data["planned_operations"]:
            raise CoordinatorError(
                Blocker(
                    "missing_operation_plan",
                    "The plan phase has no recorded operations.",
                    "Record the complete candidate operation plan before transition.",
                    (self.path.name,),
                )
            )
        moment = now or _utc_now()
        history.append(
            {
                "phase": phase.value,
                "at": _utc_text(moment),
                "evidence": _safe_evidence(evidence),
            }
        )
        self.data["updated_at"] = _utc_text(moment)
        self.data["status"] = RunStatus.IN_PROGRESS.value
        self.data["next_action"] = (
            f"Continue with {ALLOWED_NEXT[phase].value} phase."
            if ALLOWED_NEXT[phase] is not None
            else "Finalize the terminal run status."
        )
        self._write()

    def record_plan(
        self, operations: tuple[Operation, ...], *, now: datetime | None = None
    ) -> None:
        history = self.data["phase_history"]
        if not history or history[-1]["phase"] != Phase.INSPECT.value:
            raise CoordinatorError(
                Blocker(
                    "plan_without_inspection",
                    "Operations can be recorded only after inspect phase.",
                    "Complete inspect and retry planning.",
                    (self.path.name,),
                )
            )
        if self.data["planned_operations"]:
            raise CoordinatorError(
                Blocker(
                    "plan_already_recorded",
                    "The journal already has a candidate operation plan.",
                    "Reconcile or supersede the run instead of replacing its plan.",
                    (self.path.name,),
                )
            )
        self.data["planned_operations"] = [_operation(operation) for operation in operations]
        moment = now or _utc_now()
        self.data["updated_at"] = _utc_text(moment)
        self._write()

    def record_sources(
        self,
        sources: dict[str, tuple[str, str]],
        *,
        now: datetime | None = None,
    ) -> None:
        if self.data["source_files"]:
            raise CoordinatorError(
                Blocker(
                    "source_inventory_already_recorded",
                    "The source inventory is already immutable in this journal.",
                    "Start a new run if source evidence changed.",
                    (self.path.name,),
                )
            )
        self.data["source_files"] = [
            {
                "relative_path": relative,
                "sha256": digest,
                "disposition": disposition,
            }
            for relative, (digest, disposition) in sorted(sources.items())
        ]
        moment = now or _utc_now()
        self.data["updated_at"] = _utc_text(moment)
        self._write()

    def record_post_apply(
        self, inspection: Inspection, *, now: datetime | None = None
    ) -> None:
        self.data["post_apply_git"] = asdict(journal_git_evidence(inspection))
        moment = now or _utc_now()
        self.data["updated_at"] = _utc_text(moment)
        self._write()

    def record_file_write(
        self,
        relative_path: str,
        before_sha256: str | None,
        after_sha256: str | None,
        *,
        now: datetime | None = None,
    ) -> None:
        self.data["file_hashes"].append(
            {
                "relative_path": relative_path,
                "before_sha256": before_sha256,
                "after_sha256": after_sha256,
            }
        )
        moment = now or _utc_now()
        self.data["updated_at"] = _utc_text(moment)
        self._write()

    def record_validation(
        self,
        checks: tuple[dict[str, Any], ...],
        *,
        now: datetime | None = None,
    ) -> None:
        self.data["validation"] = [dict(check) for check in checks]
        moment = now or _utc_now()
        self.data["updated_at"] = _utc_text(moment)
        self._write()

    def record_recovery_receipt(
        self,
        action: str,
        relative_path: str,
        evidence_sha256: str,
        *,
        now: datetime | None = None,
    ) -> None:
        """Persist one redacted recovery step so rollback can resume safely."""

        name = f"recovery-{action}:{relative_path}:{evidence_sha256}"
        if not any(
            isinstance(item, dict) and item.get("name") == name
            for item in self.data["validation"]
        ):
            self.data["validation"].append(
                {
                    "name": name,
                    "ok": True,
                    "severity": "info",
                    "message": "A guarded recovery step completed with matching hash evidence.",
                }
            )
        moment = now or _utc_now()
        self.data["updated_at"] = _utc_text(moment)
        self._write()

    def finish(
        self,
        status: RunStatus,
        next_action: str,
        report_path: str,
        report_sha256: str,
        *,
        now: datetime | None = None,
    ) -> None:
        if status is RunStatus.COMPLETE:
            history = self.data["phase_history"]
            if not history or history[-1]["phase"] != Phase.FINALIZE.value:
                raise CoordinatorError(
                    Blocker(
                        "premature_completion",
                        "A run cannot complete before finalize phase.",
                        "Complete candidate validation and finalize before terminal status.",
                    )
                )
        moment = now or _utc_now()
        self.data["status"] = status.value
        self.data["next_action"] = redact_text(next_action)
        self.data["report_path"] = report_path
        self.data["report_sha256"] = report_sha256
        self.data["updated_at"] = _utc_text(moment)
        self._write()


def find_incomplete_runs(repo: Path) -> tuple[Path, ...]:
    migrations = repo / "docs/codex/MIGRATIONS"
    if not migrations.is_dir() or migrations.is_symlink():
        return ()
    found: list[Path] = []
    for path in sorted(migrations.glob("*.journal.json")):
        try:
            content = read_regular_file(repo, path, max_bytes=4 * 1024 * 1024)
            if content is None:
                found.append(path)
                continue
            data = json.loads(content)
        except (CoordinatorError, OSError, UnicodeError, json.JSONDecodeError):
            found.append(path)
            continue
        if data.get("status") not in _RESOLVED:
            found.append(path)
    return tuple(found)


def _safe_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        bool(value)
        and not value.startswith("/")
        and "\\" not in value
        and path.as_posix() == value
        and ".." not in path.parts
    )


def _current_operation_states(repo: Path, data: dict[str, Any]) -> dict[str, str]:
    states: dict[str, str] = {}
    for operation in data.get("planned_operations", []):
        if not isinstance(operation, dict):
            continue
        relative = operation.get("relative_path")
        before = operation.get("before_sha256")
        after = operation.get("after_sha256")
        if not isinstance(relative, str) or not _safe_relative_path(relative):
            continue
        if operation.get("action") == "git-init":
            try:
                kind = inspect_repository(repo).git.kind.value
                states[relative] = (
                    "pending" if kind in {"empty-non-git", "nonempty-non-git"} else "applied"
                )
            except (CoordinatorError, OSError):
                states[relative] = "conflicting"
            continue
        try:
            content = read_regular_file(
                repo, repo / relative, max_bytes=64 * 1024 * 1024
            )
        except CoordinatorError:
            content = None
            states[relative] = "conflicting"
            continue
        current = sha256_bytes(content) if content is not None else None
        if isinstance(after, str) and current == after:
            states[relative] = "applied"
        elif (
            relative == data.get("report_path")
            and data.get("status") in {RunStatus.FAILED.value, RunStatus.BLOCKED.value}
            and isinstance(data.get("report_sha256"), str)
            and current == data.get("report_sha256")
        ):
            states[relative] = "recovery-report"
        elif current == before:
            states[relative] = "pending"
        else:
            states[relative] = "conflicting"
    return states


def reconstruct_preimage(
    repo: Path, data: dict[str, Any], operation: dict[str, Any]
) -> bytes | None:
    """Reconstruct one prior file only from the journal's bounded evidence class."""

    relative = operation.get("relative_path")
    before_hash = operation.get("before_sha256")
    after_hash = operation.get("after_sha256")
    reversal = operation.get("reversal")
    if (
        not isinstance(relative, str)
        or not isinstance(before_hash, str)
        or not isinstance(after_hash, str)
        or not isinstance(reversal, dict)
    ):
        return None
    current = read_regular_file(
        repo, repo / relative, max_bytes=64 * 1024 * 1024
    )
    if current is None or sha256_bytes(current) != after_hash:
        return None
    metadata = {
        item.get("name"): item.get("value")
        for item in reversal.get("metadata", [])
        if isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and isinstance(item.get("value"), str)
    }
    if metadata.get("before_sha256") != before_hash:
        return None
    kind = reversal.get("kind")
    if kind == "remove-inserted-block" and relative == "AGENTS.md":
        try:
            block = parse_managed_block(current)
        except CoordinatorError:
            return None
        if block is None:
            return None
        candidate = current[: block.start] + current[block.end :]
        if sha256_bytes(candidate) == before_hash:
            return candidate
        if candidate.endswith(b"\n") and sha256_bytes(candidate[:-1]) == before_hash:
            return candidate[:-1]
        return None
    if kind == "restore-git-base":
        reference = reversal.get("reference")
        starting_git = data.get("starting_git", {})
        if (
            not isinstance(reference, str)
            or not isinstance(starting_git, dict)
            or reference
            not in {starting_git.get("head"), starting_git.get("explicit_base")}
        ):
            return None
        return read_tracked_preimage(repo, reference, relative, before_hash)
    return None


def classify_run(repo: Path, path: Path) -> Reconciliation:
    try:
        run = RunJournal.load(repo, path)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        blocker = Blocker(
            "malformed_journal",
            "A coordinator run journal is unreadable or malformed.",
            "Repair or explicitly supersede the journal before mutation.",
            (path.name,),
        )
        return Reconciliation(
            run_id=None,
            status=RunStatus.BLOCKED,
            evidence=({"status": EvidenceStatus.CONFLICTING.value, "claim": "journal"},),
            safe_actions=(),
            recommended_action=RecoveryAction.REPAIR,
            blockers=(blocker,),
        )
    data = run.data
    try:
        status = RunStatus(data.get("status", RunStatus.BLOCKED.value))
    except ValueError:
        status = RunStatus.BLOCKED
    states = _current_operation_states(repo, data)
    conflicts = sorted(path for path, state in states.items() if state == "conflicting")
    blockers: list[Blocker] = []
    if conflicts:
        blockers.append(
            Blocker(
                "recovery_hash_conflict",
                "Managed files no longer match the interrupted run hashes.",
                "Inspect the conflicting files and choose repair or supersede.",
                tuple(conflicts),
            )
        )
    operations = data.get("planned_operations", [])
    receipt_hashes = {
        item.get("relative_path"): item.get("after_sha256")
        for item in data.get("file_hashes", [])
        if isinstance(item, dict) and isinstance(item.get("relative_path"), str)
    }
    def reversible_item(item: Any) -> bool:
        if not isinstance(item, dict):
            return False
        state = states.get(item.get("relative_path"), "conflicting")
        return (
            state == "pending"
            or (
                isinstance(item.get("reversal"), dict)
                and item["reversal"].get("kind") == "delete-new"
                and receipt_hashes.get(item.get("relative_path"))
                == item.get("after_sha256")
                and item.get("relative_path") == data.get("report_path")
            )
            or (state == "applied" and reconstruct_preimage(repo, data, item) is not None)
            or (
                state == "recovery-report"
                and item.get("relative_path") == data.get("report_path")
            )
        )

    reversible = all(reversible_item(item) for item in operations)
    safe: list[RecoveryAction] = []
    if status not in {RunStatus.COMPLETE, RunStatus.SUPERSEDED} and not conflicts:
        state_values = tuple(states.values())
        if operations and state_values and all(value == "applied" for value in state_values):
            safe.append(RecoveryAction.RESUME)
        if reversible:
            safe.append(RecoveryAction.ROLLBACK)
    recommended = (
        RecoveryAction.REPAIR
        if blockers
        else (
            RecoveryAction.RESUME
            if RecoveryAction.RESUME in safe
            else (
                RecoveryAction.ROLLBACK
                if RecoveryAction.ROLLBACK in safe
                else RecoveryAction.REPAIR
            )
        )
    )
    evidence = (
        {
            "status": EvidenceStatus.CONFLICTING.value if conflicts else EvidenceStatus.VERIFIED.value,
            "claim": "journal-hashes",
        },
        *(
            {
                "status": (
                    EvidenceStatus.VERIFIED.value
                    if state in {"pending", "applied", "recovery-report"}
                    else EvidenceStatus.CONFLICTING.value
                ),
                "claim": f"operation:{relative}:{state}",
            }
            for relative, state in sorted(states.items())
        ),
    )
    return Reconciliation(
        run_id=data.get("run_id") if isinstance(data.get("run_id"), str) else None,
        status=status,
        evidence=evidence,
        safe_actions=tuple(safe),
        recommended_action=recommended,
        blockers=tuple(blockers),
    )


def classify_lock(lock_path: Path, journal_paths: tuple[Path, ...]) -> LockState:
    if not lock_path.exists():
        return LockState("absent", None, None)
    try:
        repo = lock_path.parents[3]
        content = read_regular_file(repo, lock_path, max_bytes=64 * 1024)
        if content is None:
            return LockState("absent", None, None)
        data = json.loads(content)
    except (CoordinatorError, OSError, UnicodeError, json.JSONDecodeError):
        blocker = Blocker(
            "malformed_lock",
            "The coordinator lock is malformed.",
            "Use fingerprint-bound supersede after verifying no active run.",
        )
        return LockState("conflicting", None, None, blocker)
    run_id = data.get("run_id") if isinstance(data.get("run_id"), str) else None
    journal_path = data.get("journal_path") if isinstance(data.get("journal_path"), str) else None
    correlated = any(path.name == Path(journal_path).name for path in journal_paths) if journal_path else False
    pid = data.get("pid")
    alive = False
    if isinstance(pid, int) and pid > 0:
        try:
            os.kill(pid, 0)
            alive = True
        except ProcessLookupError:
            alive = False
        except PermissionError:
            alive = True
    if alive:
        return LockState("active", run_id, journal_path)
    return LockState("stale" if correlated or run_id else "conflicting", run_id, journal_path)


def repository_identity_matches(repo: Path, data: dict[str, Any]) -> bool:
    identity = data.get("repository_identity")
    if not isinstance(identity, dict):
        return False
    project_id_text = identity.get("project_id")
    if not isinstance(project_id_text, str):
        return False
    try:
        project_id = UUID(project_id_text)
    except ValueError:
        return False
    inspection = inspect_repository(repo)
    if inspection.installed_version is not None:
        try:
            standard_bytes = read_regular_file(
                repo,
                repo / "docs/codex/STANDARD.json",
                max_bytes=4 * 1024 * 1024,
            )
            standard = json.loads(standard_bytes) if standard_bytes is not None else None
        except (CoordinatorError, UnicodeError, json.JSONDecodeError):
            return False
        if not isinstance(standard, dict) or standard.get("project_id") != project_id_text:
            return False
    expected = _repository_identity(inspection, project_id)
    return all(
        identity.get(key) == expected.get(key)
        for key in ("project_id", "fingerprint", "basename")
    )


__all__ = [
    "ALLOWED_NEXT",
    "RunJournal",
    "classify_lock",
    "classify_run",
    "find_incomplete_runs",
    "journal_git_evidence",
    "reconstruct_preimage",
    "repository_identity_matches",
    "terminal_journal_candidate",
]
