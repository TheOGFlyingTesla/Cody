"""Coordinator Standard initialization and shared operation execution."""

from __future__ import annotations

import copy
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from typing import Any
from uuid import UUID, uuid4, getnode

from . import STANDARD_VERSION
from .git_state import recovery_git_picture, sterile_git_environment
from .inspector import inspect_repository
from .journal import RunJournal
from .journal import classify_lock, classify_run, journal_git_evidence
from .journal import find_incomplete_runs
from .journal import reconstruct_preimage, repository_identity_matches, terminal_journal_candidate
from .markers import parse_managed_block
from .model import (
    AuthorityGrant,
    Blocker,
    CoordinatorError,
    Inspection,
    Operation,
    OperationResult,
    Phase,
    RecoveryAction,
    RepoKind,
    ReversalEvidence,
    RunStatus,
)
from .safety import (
    ExclusiveRunLock,
    assert_contained,
    atomic_write,
    contains_credential,
    ensure_directory,
    read_regular_file,
    redact_text,
    sha256_bytes,
    unlink_regular_file,
)
from .templates import derive_project_slug, render_new_project, validate_project_slug
from .validator import (
    strict_json_loads,
    validate_repository,
    validate_schema_document,
)


_ALLOWED_FIXED = {
    "AGENTS.md",
    "docs/codex/STANDARD.json",
    "docs/codex/PROJECT.md",
    "docs/codex/STATUS.md",
    "docs/codex/ROADMAP.md",
    "docs/codex/DECISIONS.md",
    "docs/codex/WORK_ITEMS/.gitkeep",
    "docs/codex/MIGRATIONS/.gitkeep",
}
_MAX_BOUNDARY_FILE = 64 * 1024 * 1024
_MAX_BOUNDARY_TOTAL = 256 * 1024 * 1024


def _preexisting_unmanaged_targets(repo: Path) -> tuple[str, ...]:
    """Return coordinator targets that an unmanaged install must not replace."""

    protected = tuple(
        sorted(
            path
            for path in _ALLOWED_FIXED
            if path not in {"AGENTS.md", "docs/codex/STANDARD.json"}
        )
    )
    return tuple(
        relative
        for relative in protected
        if read_regular_file(repo, repo / relative) is not None
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _result_operations(operations: tuple[Operation, ...]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "action": operation.action,
            "relative_path": operation.relative_path,
            "before_sha256": operation.before_sha256,
            "after_sha256": operation.after_sha256,
        }
        for operation in operations
    )


def _blocked(
    command: str,
    inspection: Inspection,
    blocker: Blocker,
    *,
    slug: str = ".",
    metadata: dict[str, Any] | None = None,
    run_id: str | None = None,
    changed: bool = False,
    operations: tuple[dict[str, Any], ...] = (),
) -> OperationResult:
    safe_blocker = Blocker(
        code=redact_text(blocker.code),
        message=redact_text(blocker.message),
        recovery=redact_text(blocker.recovery),
        paths=tuple(redact_text(path) for path in blocker.paths),
    )
    return OperationResult(
        command=command,
        ok=False,
        changed=changed,
        repository=slug,
        repo_kind=inspection.git.kind,
        run_id=run_id,
        standard_version=inspection.installed_version,
        operations=operations,
        blockers=(safe_blocker,),
        recommended_next_action=safe_blocker.recovery,
        metadata=metadata or {},
    )


def _bounded_inventory(repo: Path) -> tuple[dict[str, Any], ...]:
    entries: list[dict[str, Any]] = []
    total = 0
    for path in sorted(repo.rglob("*"), key=lambda item: item.relative_to(repo).as_posix()):
        relative = path.relative_to(repo).as_posix()
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise CoordinatorError(
                Blocker(
                    "repository_boundary_symlink",
                    "The non-Git folder contains a symbolic link.",
                    "Choose the intended repository boundary and replace unsafe links before initialization.",
                    (relative,),
                )
            )
        if stat.S_ISDIR(info.st_mode):
            entries.append({"path": relative, "kind": "directory"})
            continue
        if not stat.S_ISREG(info.st_mode):
            raise CoordinatorError(
                Blocker(
                    "repository_boundary_special_file",
                    "The non-Git folder contains a special file.",
                    "Remove or relocate sockets, devices, and pipes before initialization.",
                    (relative,),
                )
            )
        if info.st_size > _MAX_BOUNDARY_FILE or total + info.st_size > _MAX_BOUNDARY_TOTAL:
            raise CoordinatorError(
                Blocker(
                    "repository_boundary_too_large",
                    "The non-Git folder exceeds the bounded decision inventory limit.",
                    "Choose the repository boundary explicitly after reviewing large files.",
                    (relative,),
                )
            )
        total += info.st_size
        content = read_regular_file(repo, path)
        if content is None:
            raise CoordinatorError(
                Blocker(
                    "repository_boundary_changed",
                    "A file disappeared during repository-boundary inspection.",
                    "Retry after concurrent filesystem changes stop.",
                    (relative,),
                )
            )
        entries.append(
            {
                "path": relative,
                "kind": "file",
                "size": info.st_size,
                "sha256": sha256_bytes(content),
                "device": info.st_dev,
                "inode": info.st_ino,
            }
        )
    return tuple(entries)


def make_decision_token(inspection: Inspection, decision: str) -> str:
    inventory = _bounded_inventory(inspection.repo)
    material = {
        "decision": decision,
        "standard_version": STANDARD_VERSION,
        "repo_kind": inspection.git.kind.value,
        "basename": inspection.repo.name,
        "inventory": inventory,
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _candidate_inspection(inspection: Inspection) -> Inspection:
    if inspection.git.kind not in {RepoKind.EMPTY_NON_GIT, RepoKind.NONEMPTY_NON_GIT}:
        return inspection
    expected_git = replace(
        inspection.git,
        kind=RepoKind.UNBORN_GIT,
        branch="main",
        is_detached=False,
    )
    return replace(inspection, git=expected_git)


def _git_evidence_fingerprint(inspection: Inspection) -> str:
    evidence = journal_git_evidence(inspection)
    canonical = json.dumps(
        {
            "kind": evidence.kind,
            "head": evidence.head,
            "explicit_base": evidence.explicit_base,
            "worktree_identity_sha256": evidence.worktree_identity_sha256,
            "common_dir_identity_sha256": evidence.common_dir_identity_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_bytes(canonical.encode("utf-8"))


def _report_content(
    *,
    run_id: str,
    timestamp: str,
    source_version: str,
    operations: tuple[Operation, ...],
    mapping_rows: tuple[tuple[str, str, str], ...] = (),
    git_fingerprint: str = "unknown",
    warnings: tuple[str, ...] = (),
) -> bytes:
    paths = "\n".join(
        f"- `{operation.relative_path}` ({operation.action})"
        for operation in operations
        if operation.action != "git-init"
    )
    mapping = "\n".join(
        f"| `{source}` | `{destination}` | {disposition} |"
        for source, destination, disposition in mapping_rows
    )
    mapping_section = (
        f"## Standard {source_version} source mapping\n\n"
        "| Source | Destination | Disposition |\n"
        "|---|---|---|\n"
        f"{mapping}\n\n"
        if mapping_rows
        else ""
    )
    warning_lines = "\n".join(f"- {redact_text(item)}" for item in warnings) or "- None."
    return (
        "# Coordinator Migration Report\n\n"
        "## Summary\n\n"
        f"- Run ID: `{run_id}`\n"
        f"- Completed at: `{timestamp}`\n"
        f"- Source: `{source_version}`\n"
        f"- Destination: `{STANDARD_VERSION}`\n"
        f"- Git evidence fingerprint: `{git_fingerprint}`\n"
        "- Scope: coordinator-layer files only\n\n"
        "## Files changed\n\n"
        f"{paths}\n\n"
        "## Preservation\n\n"
        "Product files, retained source evidence, remotes, commits, branches, deployments, and external systems were not changed by this run. Coordinator targets normalized in place are listed above.\n\n"
        f"{mapping_section}"
        "## Validation run\n\n"
        "Candidate scope, markers, identity JSON, credential patterns, actual bytes, and repeated-render stability were checked.\n\n"
        "## Review findings\n\n"
        "No unresolved correctness, security, migration-fidelity, or release-integrity finding was recorded by this repository-scoped run.\n\n"
        "## P0/P1 status\n\n"
        "No P0 or P1 finding was detected by the bounded candidate validation.\n\n"
        "## P2/P3 disposition\n\n"
        "Legacy cleanup and optional documentation polish remain separate explicit work.\n\n"
        "## Remaining risks\n\n"
        "Live worker/task claims and external-system state remain unknown until independently reconciled.\n\n"
        "### Warnings\n\n"
        f"{warning_lines}\n\n"
        "## Next step\n\n"
        "Run `doctor`, review STATUS, and continue only from verified repository evidence.\n\n"
        "## Cleanup\n\n"
        "No legacy source was deleted or archived. Cleanup remains a separate explicit decision.\n"
    ).encode("utf-8")


def _failure_report(run_id: str, blocker: Blocker) -> bytes:
    return (
        "# Coordinator Run Failure Report\n\n"
        "## Summary\n\n"
        f"- Run ID: `{run_id}`\n"
        f"- Blocker: `{redact_text(blocker.code)}`\n"
        "- Result: the run is unresolved; no completion is claimed.\n\n"
        "## Files changed\n\nSee the run journal receipts; product files were outside authority.\n\n"
        "## Validation run\n\nTerminal validation did not complete successfully.\n\n"
        "## Review findings\n\nThe recorded blocker requires reconciliation.\n\n"
        "## P0/P1 status\n\nUnknown until the interrupted state is reconciled.\n\n"
        "## P2/P3 disposition\n\nDeferred until the blocking state is resolved.\n\n"
        "## Remaining risks\n\nJournal and current file hashes may disagree; do not infer recovery bytes.\n\n"
        "## Next step\n\n"
        f"{redact_text(blocker.recovery)}\n"
    ).encode("utf-8")


def _finish_failed_run(journal: RunJournal, run_id: str, blocker: Blocker) -> None:
    report_path = journal.data["report_path"]
    content = _failure_report(run_id, blocker)
    ensure_directory(journal.repo, (journal.repo / report_path).parent)
    atomic_write(journal.repo / report_path, content, root=journal.repo, public=True)
    journal.finish(
        RunStatus.FAILED,
        blocker.recovery,
        report_path,
        sha256_bytes(content),
    )


def _with_run_record(
    operations: tuple[Operation, ...],
    *,
    run_id: str,
    timestamp: str,
    source_version: str,
    report_path: str,
    mapping_rows: tuple[tuple[str, str, str], ...] = (),
    git_fingerprint: str = "unknown",
    warnings: tuple[str, ...] = (),
) -> tuple[Operation, ...]:
    updated: list[Operation] = []
    for operation in operations:
        if operation.relative_path != "docs/codex/STANDARD.json":
            updated.append(operation)
            continue
        if operation.content is None:
            raise CoordinatorError(
                Blocker(
                    "missing_standard_candidate",
                    "The candidate installation record has no content.",
                    "Re-render the coordinator candidate before applying it.",
                )
            )
        standard = json.loads(operation.content)
        prior_migrations = standard.get("migrations", [])
        if not isinstance(prior_migrations, list):
            raise CoordinatorError(
                Blocker(
                    "malformed_migration_history",
                    "The installation record has malformed migration history.",
                    "Repair STANDARD.json before applying the migration.",
                    ("docs/codex/STANDARD.json",),
                )
            )
        standard["migrations"] = [
            *prior_migrations,
            {
                "source_version": source_version,
                "destination_version": STANDARD_VERSION,
                "run_id": run_id,
                "completed_at": timestamp,
                "record_path": report_path,
            }
        ]
        content = (json.dumps(standard, indent=2, ensure_ascii=False) + "\n").encode(
            "utf-8"
        )
        updated.append(
            replace(operation, content=content, after_sha256=sha256_bytes(content))
        )
    report_content = _report_content(
        run_id=run_id,
        timestamp=timestamp,
        source_version=source_version,
        operations=tuple(updated),
        mapping_rows=mapping_rows,
        git_fingerprint=git_fingerprint,
        warnings=warnings,
    )
    updated.append(
        Operation(
            action="create",
            relative_path=report_path,
            before_sha256=None,
            after_sha256=sha256_bytes(report_content),
            content=report_content,
            reversal=ReversalEvidence("delete-new", None),
        )
    )
    return tuple(updated)


def _run_metadata_paths(report_path: str) -> tuple[str, ...]:
    return (
        "docs",
        "docs/codex",
        "docs/codex/WORK_ITEMS",
        "docs/codex/MIGRATIONS",
        "docs/codex/MIGRATIONS/.coordinator.lock",
        report_path.replace(".report.md", ".journal.json"),
    )


def _candidate_checks(operations: tuple[Operation, ...]) -> tuple[dict[str, Any], ...]:
    checks: list[dict[str, Any]] = []
    paths = [operation.relative_path for operation in operations]
    allowed = all(
        path in _ALLOWED_FIXED
        or (
            path.startswith("docs/codex/MIGRATIONS/")
            and path.endswith(".report.md")
        )
        or (operation.action == "git-init" and path == ".git")
        for path, operation in zip(paths, operations)
    )
    checks.append(
        {
            "name": "changed-path-allowlist",
            "ok": allowed,
            "severity": "P1",
            "message": "Candidate paths are inside the coordinator allowlist.",
        }
    )
    for operation in operations:
        if operation.content is None:
            continue
        relative = operation.relative_path
        text = operation.content.decode("utf-8", errors="strict")
        safe = not contains_credential(text)
        checks.append(
            {
                "name": f"credential-content:{relative}",
                "ok": safe,
                "severity": "P0",
                "message": f"Credential scan completed for {relative}.",
            }
        )
        no_personal_path = all(
            marker not in text for marker in ("/Users/", "/Volumes/", "C:\\Users\\")
        )
        checks.append(
            {
                "name": f"personal-path:{relative}",
                "ok": no_personal_path,
                "severity": "P1",
                "message": f"Personal-path scan completed for {relative}.",
            }
        )
        unresolved = not any(
            marker in text
            for marker in ("$PROJECT_", "$STANDARD_", "<PROJECT", "{{")
        )
        checks.append(
            {
                "name": f"template-placeholders:{relative}",
                "ok": unresolved,
                "severity": "P1",
                "message": f"Template-token scan completed for {relative}.",
            }
        )
        if relative == "AGENTS.md":
            marker_ok = parse_managed_block(operation.content) is not None
            checks.append(
                {
                    "name": "managed-marker-integrity",
                    "ok": marker_ok,
                    "severity": "P1",
                    "message": "AGENTS.md has one valid managed block.",
                }
            )
        if relative == "docs/codex/STANDARD.json":
            try:
                standard = json.loads(operation.content)
                json_ok = (
                    isinstance(standard, dict)
                    and standard.get("standard_version") == STANDARD_VERSION
                    and isinstance(standard.get("project_id"), str)
                )
            except json.JSONDecodeError:
                json_ok = False
            checks.append(
                {
                    "name": "standard-json",
                    "ok": json_ok,
                    "severity": "P1",
                    "message": "STANDARD.json is valid and versioned.",
                }
            )
    return tuple(checks)


def _require_repeatable_candidate(
    first: tuple[Operation, ...], second: tuple[Operation, ...]
) -> None:
    identity = lambda values: tuple(
        (
            item.action,
            item.relative_path,
            item.before_sha256,
            item.after_sha256,
        )
        for item in values
    )
    if identity(first) != identity(second):
        raise CoordinatorError(
            Blocker(
                "candidate_render_drift",
                "Repeated coordinator rendering produced different candidate hashes.",
                "Stop and repair nondeterministic template or discovery inputs.",
            )
        )


def _require_candidate(checks: tuple[dict[str, Any], ...]) -> None:
    failed = [check for check in checks if not check["ok"]]
    if failed:
        first = failed[0]
        raise CoordinatorError(
            Blocker(
                "candidate_validation_failed",
                f"Candidate validation failed: {first['name']}",
                "Correct the source content or repository boundary and retry.",
            )
        )


def _terminal_candidate_checks(
    *,
    inspection: Inspection,
    post_apply: Inspection,
    authority: AuthorityGrant,
    project_id: UUID,
    project_slug: str,
    operations: tuple[Operation, ...],
    base_checks: tuple[dict[str, Any], ...],
    report_path: str,
    run_id: str,
    now: datetime,
    source_files: dict[str, tuple[str, str]] | None = None,
) -> tuple[dict[str, Any], ...]:
    report_hash = next(
        (
            item.after_sha256
            for item in operations
            if item.relative_path == report_path
        ),
        None,
    )
    if not isinstance(report_hash, str):
        raise CoordinatorError(
            Blocker(
                "missing_report_candidate",
                "The terminal candidate has no hashed migration report.",
                "Rebuild the complete operation candidate before mutation.",
            )
        )

    checks = base_checks
    previous_signature: tuple[tuple[str, bool], ...] | None = None
    for _iteration in range(3):
        journal_path, journal_content = terminal_journal_candidate(
            run_id=run_id,
            command=authority.command,
            starting=inspection,
            post_apply=post_apply,
            authority=authority,
            project_id=project_id,
            project_slug=project_slug,
            operations=operations,
            validation=checks,
            report_path=report_path,
            report_sha256=report_hash,
            now=now,
            source_files=source_files,
        )
        overlay = {
            item.relative_path: item.content
            for item in operations
            if item.content is not None
        }
        overlay[journal_path] = journal_content
        candidate = tuple(
            {
                "name": check.name,
                "ok": check.ok,
                "severity": check.severity,
                "message": check.message,
            }
            for check in validate_repository(
                inspection.repo, candidate_overlay=overlay
            )
        )
        signature = tuple((item["name"], item["ok"]) for item in candidate)
        if previous_signature == signature:
            _require_candidate(candidate)
            return candidate
        previous_signature = signature
        checks = candidate
    raise CoordinatorError(
        Blocker(
            "terminal_validation_drift",
            "Terminal candidate validation did not reach a stable result.",
            "Repair the journal/doctor dependency before coordinator mutation.",
        )
    )


def _dirty_overlap(
    inspection: Inspection, operations: tuple[Operation, ...]
) -> tuple[str, ...]:
    dirty = set(inspection.git.staged) | set(inspection.git.unstaged) | set(
        inspection.git.untracked
    )
    targets = {operation.relative_path for operation in operations}
    overlap: list[str] = []
    for relative in sorted(dirty & targets):
        operation = next(item for item in operations if item.relative_path == relative)
        current = read_regular_file(inspection.repo, inspection.repo / relative)
        if current is not None and operation.content == current:
            continue
        overlap.append(relative)
    return tuple(overlap)


def _current_installation_is_complete(inspection: Inspection) -> bool:
    if inspection.installed_version != STANDARD_VERSION or inspection.blockers:
        return False
    try:
        return all(check.ok for check in validate_repository(inspection.repo))
    except (CoordinatorError, OSError):
        return False


def _git_init(repo: Path) -> None:
    with tempfile.TemporaryDirectory(
        prefix="cody-coordinator-empty-template-"
    ) as template_dir:
        result = subprocess.run(
            [
                "git",
                "init",
                "--quiet",
                "--initial-branch=main",
                f"--template={template_dir}",
            ],
            cwd=repo,
            env=sterile_git_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    if result.returncode != 0:
        diagnostic = redact_text(result.stderr.decode("utf-8", errors="replace")).strip()
        raise CoordinatorError(
            Blocker(
                "git_init_unsupported",
                f"Git initialization failed: {diagnostic or 'no diagnostic'}",
                "Use a Git version supporting explicit initial branches and templates.",
            )
        )


def _verify_preimage(repo: Path, operation: Operation) -> None:
    current = read_regular_file(repo, repo / operation.relative_path)
    current_hash = sha256_bytes(current) if current is not None else None
    if current_hash != operation.before_sha256:
        raise CoordinatorError(
            Blocker(
                "concurrent_managed_change",
                "A managed target changed after planning.",
                "Reconcile the current bytes and rerun the operation.",
                (operation.relative_path,),
            )
        )


def apply_operations(
    repo: Path, operations: tuple[Operation, ...], journal: RunJournal
) -> None:
    for operation in operations:
        if operation.action == "git-init" or operation.content is None:
            continue
        journal.assert_lock_visible()
        _verify_preimage(repo, operation)
        target = repo / operation.relative_path
        assert_contained(repo, target)
        ensure_directory(repo, target.parent)
        atomic_write(
            target,
            operation.content,
            root=repo,
            public=True,
            expected_sha256=operation.before_sha256,
        )
        journal.record_file_write(
            operation.relative_path,
            operation.before_sha256,
            operation.after_sha256,
        )


def _verify_actual(repo: Path, operations: tuple[Operation, ...]) -> None:
    for operation in operations:
        if operation.content is None:
            continue
        current = read_regular_file(repo, repo / operation.relative_path)
        if current is None or sha256_bytes(current) != operation.after_sha256:
            raise CoordinatorError(
                Blocker(
                    "post_apply_hash_mismatch",
                    "A managed file does not match its validated candidate hash.",
                    "Stop and reconcile the interrupted run before further mutation.",
                    (operation.relative_path,),
                )
            )


def initialize(
    repo: Path,
    *,
    check: bool,
    project_slug: str | None = None,
    repository_boundary_token: str | None = None,
) -> OperationResult:
    command = "init"
    selected = Path(os.path.abspath(repo))
    if selected.is_symlink():
        return OperationResult(
            command=command,
            ok=False,
            changed=False,
            repository=".",
            repo_kind=RepoKind.UNSAFE_GIT,
            run_id=None,
            standard_version=None,
            blockers=(
                Blocker(
                    "repository_root_symlink",
                    "The selected repository root is a symbolic link.",
                    "Open the real repository directory before coordinator setup.",
                ),
            ),
            recommended_next_action="Open the real repository directory before coordinator setup.",
        )
    repo = selected.resolve(strict=True)
    inspection = inspect_repository(repo)
    slug = (
        validate_project_slug(project_slug)
        if project_slug is not None
        else derive_project_slug(repo.name)
    )
    if inspection.blockers:
        return _blocked(command, inspection, inspection.blockers[0], slug=slug)
    if inspection.git.kind in {RepoKind.BARE_GIT, RepoKind.UNSAFE_GIT}:
        return _blocked(
            command,
            inspection,
            Blocker(
                "unsupported_git_shape",
                "Coordinator setup cannot mutate this Git repository shape.",
                "Use a normal checkout with safe Git metadata.",
            ),
            slug=slug,
        )
    incomplete = find_incomplete_runs(repo)
    if incomplete:
        return _blocked(
            command,
            inspection,
            Blocker(
                "incomplete_prior_run",
                "An earlier coordinator run is unresolved.",
                "Run reconcile and choose an evidence-supported recovery action.",
                tuple(path.name for path in incomplete),
            ),
            slug=slug,
        )
    if _current_installation_is_complete(inspection):
        return OperationResult(
            command=command,
            ok=True,
            changed=False,
            repository=slug,
            repo_kind=inspection.git.kind,
            run_id=None,
            standard_version=STANDARD_VERSION,
            recommended_next_action="Continue normal coordination.",
        )
    if inspection.installed_version == STANDARD_VERSION:
        return _blocked(
            command,
            inspection,
            Blocker(
                "current_installation_invalid",
                "The current coordinator installation is incomplete or inconsistent.",
                "Run doctor and repair the reported coordinator files.",
            ),
            slug=slug,
        )
    if inspection.git.kind is RepoKind.NONEMPTY_NON_GIT:
        token = make_decision_token(inspection, "initialize-repository-boundary")
        if repository_boundary_token is None:
            return _blocked(
                command,
                inspection,
                Blocker(
                    "repository_boundary_decision_required",
                    "This non-empty folder needs one explicit repository-boundary decision.",
                    "Approve the fingerprint-bound repository boundary and retry.",
                ),
                slug=slug,
                metadata={"repository_boundary_token": token},
            )
        if repository_boundary_token != token:
            return _blocked(
                command,
                inspection,
                Blocker(
                    "repository_boundary_token_stale",
                    "The repository-boundary evidence changed after approval.",
                    "Inspect the changed folder and approve the new decision token.",
                ),
                slug=slug,
                metadata={"repository_boundary_token": token},
            )

    existing_targets = _preexisting_unmanaged_targets(repo)
    if existing_targets:
        return _blocked(
            command,
            inspection,
            Blocker(
                "existing_coordinator_target",
                "An unmanaged project already contains files at coordinator-owned destinations.",
                "Preserve and classify those files before choosing an explicit migration or repair path.",
                existing_targets,
            ),
            slug=slug,
        )

    now = _utc_now()
    timestamp = _utc_text(now)
    run_id = str(uuid4())
    project_id = uuid4()
    filename_timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    report_path = (
        f"docs/codex/MIGRATIONS/{filename_timestamp}-{run_id}.report.md"
    )
    candidate_inspection = _candidate_inspection(inspection)
    git_fingerprint = _git_evidence_fingerprint(candidate_inspection)
    operations = render_new_project(
        candidate_inspection, slug, now, UUID(str(project_id))
    )
    operations = _with_run_record(
        operations,
        run_id=run_id,
        timestamp=timestamp,
        source_version="unmanaged",
        report_path=report_path,
        git_fingerprint=git_fingerprint,
    )
    repeated_operations = _with_run_record(
        render_new_project(candidate_inspection, slug, now, UUID(str(project_id))),
        run_id=run_id,
        timestamp=timestamp,
        source_version="unmanaged",
        report_path=report_path,
        git_fingerprint=git_fingerprint,
    )
    try:
        _require_repeatable_candidate(operations, repeated_operations)
    except CoordinatorError as error:
        return _blocked(command, inspection, error.blocker, slug=slug)
    needs_git_init = inspection.git.kind in {
        RepoKind.EMPTY_NON_GIT,
        RepoKind.NONEMPTY_NON_GIT,
    }
    git_operation = (
        Operation(
            action="git-init",
            relative_path=".git",
            before_sha256=None,
            after_sha256=None,
            content=None,
            reversal=ReversalEvidence("unavailable", None),
        ),
    ) if needs_git_init else ()
    complete_plan = git_operation + operations
    decisions = (
        (("initialize-repository-boundary", repository_boundary_token),)
        if repository_boundary_token is not None
        else ()
    )
    authority = AuthorityGrant(
        command=command,
        mutation_classes=(
            "coordinator-layer",
            "run-metadata",
            "managed-directories",
            *(("git-init",) if needs_git_init else ()),
        ),
        allowed_paths=tuple(
            sorted(
                {operation.relative_path for operation in complete_plan}
                | set(_run_metadata_paths(report_path))
            )
        ),
        decisions=decisions,
        created_at=timestamp,
        source_id="current-task:user-request",
    )
    base_checks = _candidate_checks(complete_plan)
    try:
        _require_candidate(base_checks)
        checks = _terminal_candidate_checks(
            inspection=inspection,
            post_apply=candidate_inspection,
            authority=authority,
            project_id=project_id,
            project_slug=slug,
            operations=complete_plan,
            base_checks=base_checks,
            report_path=report_path,
            run_id=run_id,
            now=now,
        )
    except CoordinatorError as error:
        return _blocked(command, inspection, error.blocker, slug=slug)
    overlap = _dirty_overlap(inspection, complete_plan)
    if overlap:
        return _blocked(
            command,
            inspection,
            Blocker(
                "dirty_overlap",
                "Uncommitted work overlaps coordinator-managed targets.",
                "Reconcile or preserve the overlapping user edits before setup.",
                overlap,
            ),
            slug=slug,
        )
    if check:
        return OperationResult(
            command=command,
            ok=True,
            changed=True,
            repository=slug,
            repo_kind=inspection.git.kind,
            run_id=None,
            standard_version=None,
            operations=_result_operations(complete_plan),
            validation=checks,
            recommended_next_action="Run initialization to apply this validated candidate.",
        )

    migrations = repo / "docs/codex/MIGRATIONS"
    ensure_directory(repo, migrations)
    lock_path = migrations / ".coordinator.lock"
    host_hash = hashlib.sha256(str(getnode()).encode("ascii")).hexdigest()
    lock = ExclusiveRunLock(
        repo,
        lock_path,
        {
            "run_id": run_id,
            "host_id_sha256": host_hash,
            "pid": os.getpid(),
            "created_at": timestamp,
            "journal_path": report_path.replace(".report.md", ".journal.json"),
        },
    )
    journal: RunJournal | None = None
    try:
        lock.acquire()
        journal = RunJournal.create(
            repo,
            run_id,
            command,
            inspection,
            authority,
            project_id,
            now=now,
            visibility_guard=lock.assert_visible,
            project_slug=slug,
        )
        journal.transition(Phase.INSPECT, {"repo_kind": inspection.git.kind.value}, now=now)
        journal.record_plan(complete_plan, now=now)
        journal.transition(Phase.PLAN, {"operation_count": len(complete_plan)}, now=now)

        if needs_git_init:
            lock.assert_visible()
            _git_init(repo)
            after_init = inspect_repository(repo)
            rerendered = _with_run_record(
                render_new_project(after_init, slug, now, project_id),
                run_id=run_id,
                timestamp=timestamp,
                source_version="unmanaged",
                report_path=report_path,
                git_fingerprint=git_fingerprint,
            )
            if tuple(
                (item.relative_path, item.after_sha256) for item in rerendered
            ) != tuple((item.relative_path, item.after_sha256) for item in operations):
                raise CoordinatorError(
                    Blocker(
                        "post_git_init_candidate_drift",
                        "The coordinator candidate changed after Git initialization.",
                        "Reconcile the initialized repository and restart setup.",
                    )
                )
            _require_candidate(_candidate_checks(git_operation + rerendered))

        apply_operations(repo, operations, journal)
        after_apply = inspect_repository(repo)
        journal.record_post_apply(after_apply, now=now)
        journal.transition(Phase.APPLY, {"written_files": len(operations)}, now=now)
        _verify_actual(repo, operations)
        journal.record_validation(checks, now=now)
        journal.transition(Phase.VALIDATE, {"checks": len(checks)}, now=now)
        journal.transition(Phase.FINALIZE, {"report_path": report_path}, now=now)
        report_hash = next(
            item.after_sha256 for item in operations if item.relative_path == report_path
        ) or ""
        journal.finish(
            RunStatus.COMPLETE,
            "Continue normal coordination.",
            report_path,
            report_hash,
            now=now,
        )
        return OperationResult(
            command=command,
            ok=True,
            changed=True,
            repository=slug,
            repo_kind=after_apply.git.kind,
            run_id=run_id,
            standard_version=STANDARD_VERSION,
            operations=_result_operations(complete_plan),
            validation=checks,
            recommended_next_action="Set the first project outcome with the project owner.",
        )
    except CoordinatorError as error:
        if journal is not None:
            try:
                _finish_failed_run(journal, run_id, error.blocker)
            except CoordinatorError:
                pass
        return _blocked(
            command,
            inspection,
            error.blocker,
            slug=slug,
            run_id=run_id,
            changed=journal is not None,
            operations=(
                tuple(
                    {
                        "action": "recorded-write",
                        "relative_path": item.get("relative_path"),
                        "before_sha256": item.get("before_sha256"),
                        "after_sha256": item.get("after_sha256"),
                    }
                    for item in journal.data.get("file_hashes", [])
                    if isinstance(item, dict)
                )
                if journal is not None
                else ()
            ),
            metadata=(
                {"journal": journal.path.name}
                if journal is not None
                else None
            ),
        )
    finally:
        lock.release()


def _upgrade_v30(repo: Path, inspection: Inspection, *, check: bool) -> OperationResult:
    from .migrate_v30 import plan_v30_migration

    command = "upgrade"
    slug = derive_project_slug(repo.name)
    now = _utc_now()
    timestamp = _utc_text(now)
    run_id = str(uuid4())
    report_path = (
        f"docs/codex/MIGRATIONS/{now.strftime('%Y%m%dT%H%M%SZ')}-{run_id}.report.md"
    )
    try:
        migration = plan_v30_migration(inspection, now=now)
        operations = _with_run_record(
            migration.operations,
            run_id=run_id,
            timestamp=timestamp,
            source_version=migration.source_version,
            report_path=report_path,
            mapping_rows=migration.mapping_rows,
            git_fingerprint=_git_evidence_fingerprint(inspection),
        )
        repeated = plan_v30_migration(inspection, now=now)
        repeated_operations = _with_run_record(
            repeated.operations,
            run_id=run_id,
            timestamp=timestamp,
            source_version=repeated.source_version,
            report_path=report_path,
            mapping_rows=repeated.mapping_rows,
            git_fingerprint=_git_evidence_fingerprint(inspection),
        )
        _require_repeatable_candidate(operations, repeated_operations)
    except CoordinatorError as error:
        return _blocked(command, inspection, error.blocker, slug=slug)

    standard_bytes = read_regular_file(repo, repo / "docs/codex/STANDARD.json") or b"{}"
    try:
        standard_before = strict_json_loads(standard_bytes)
        project_id = UUID(str(standard_before["project_id"]))
        project_slug = str(standard_before["project_slug"])
    except (CoordinatorError, KeyError, TypeError, ValueError) as error:
        return _blocked(
            command,
            inspection,
            Blocker(
                "malformed_v30_standard",
                "The Standard 3.0 identity fields are invalid.",
                "Repair STANDARD.json before upgrading.",
                ("docs/codex/STANDARD.json",),
            ),
            slug=slug,
        )
    source_records = {
        relative: (
            sha256_bytes((repo / relative).read_bytes()),
            "normalized-in-place",
        )
        for relative in ("AGENTS.md", "docs/codex/STANDARD.json")
    }
    authority = AuthorityGrant(
        command=command,
        mutation_classes=("coordinator-layer", "sequential-safe-migration", "run-metadata"),
        allowed_paths=tuple(
            sorted(
                {operation.relative_path for operation in operations}
                | set(_run_metadata_paths(report_path))
            )
        ),
        decisions=(),
        created_at=timestamp,
        source_id="current-task:user-request",
    )
    base_checks = _candidate_checks(operations)
    try:
        _require_candidate(base_checks)
        checks = _terminal_candidate_checks(
            inspection=inspection,
            post_apply=inspection,
            authority=authority,
            project_id=project_id,
            project_slug=project_slug,
            operations=operations,
            base_checks=base_checks,
            report_path=report_path,
            run_id=run_id,
            now=now,
            source_files=source_records,
        )
    except CoordinatorError as error:
        return _blocked(command, inspection, error.blocker, slug=slug)
    overlap = _dirty_overlap(inspection, operations)
    if overlap:
        return _blocked(
            command,
            inspection,
            Blocker(
                "dirty_overlap",
                "Uncommitted work overlaps coordinator migration targets.",
                "Preserve or reconcile the overlapping coordinator edits before upgrade.",
                overlap,
            ),
            slug=slug,
        )
    if check:
        return OperationResult(
            command=command,
            ok=True,
            changed=True,
            repository=project_slug,
            repo_kind=inspection.git.kind,
            run_id=None,
            standard_version=None,
            operations=_result_operations(operations),
            validation=checks,
            recommended_next_action=f"Run upgrade to apply this validated {STANDARD_VERSION} migration.",
        )

    migrations = repo / "docs/codex/MIGRATIONS"
    ensure_directory(repo, migrations)
    lock = ExclusiveRunLock(
        repo,
        migrations / ".coordinator.lock",
        {
            "run_id": run_id,
            "host_id_sha256": hashlib.sha256(str(getnode()).encode("ascii")).hexdigest(),
            "pid": os.getpid(),
            "created_at": timestamp,
            "journal_path": report_path.replace(".report.md", ".journal.json"),
        },
    )
    journal: RunJournal | None = None
    try:
        lock.acquire()
        journal = RunJournal.create(
            repo,
            run_id,
            command,
            inspection,
            authority,
            project_id,
            now=now,
            visibility_guard=lock.assert_visible,
            project_slug=project_slug,
        )
        journal.transition(Phase.INSPECT, {"repo_kind": inspection.git.kind.value}, now=now)
        journal.record_sources(source_records, now=now)
        journal.record_plan(operations, now=now)
        journal.transition(Phase.PLAN, {"operation_count": len(operations)}, now=now)
        apply_operations(repo, operations, journal)
        after_apply = inspect_repository(repo)
        journal.record_post_apply(after_apply, now=now)
        journal.transition(Phase.APPLY, {"written_files": len(operations)}, now=now)
        _verify_actual(repo, operations)
        journal.record_validation(checks, now=now)
        journal.transition(Phase.VALIDATE, {"checks": len(checks)}, now=now)
        journal.transition(Phase.FINALIZE, {"report_path": report_path}, now=now)
        report_hash = next(
            item.after_sha256 for item in operations if item.relative_path == report_path
        ) or ""
        journal.finish(
            RunStatus.COMPLETE,
            "Continue normal coordination and keep STATUS current at meaningful checkpoints.",
            report_path,
            report_hash,
            now=now,
        )
        return OperationResult(
            command=command,
            ok=True,
            changed=True,
            repository=project_slug,
            repo_kind=after_apply.git.kind,
            run_id=run_id,
            standard_version=STANDARD_VERSION,
            operations=_result_operations(operations),
            validation=checks,
            recommended_next_action="Continue normal coordination.",
        )
    except CoordinatorError as error:
        if journal is not None:
            try:
                _finish_failed_run(journal, run_id, error.blocker)
            except CoordinatorError:
                pass
        return _blocked(
            command,
            inspection,
            error.blocker,
            slug=slug,
            run_id=run_id,
            changed=journal is not None,
        )
    finally:
        lock.release()


def upgrade(repo: Path, *, check: bool) -> OperationResult:
    """Upgrade a supported Cody installation or initialize an unmanaged repository."""

    command = "upgrade"
    selected = Path(os.path.abspath(repo))
    if selected.is_symlink():
        return OperationResult(
            command=command,
            ok=False,
            changed=False,
            repository=".",
            repo_kind=RepoKind.UNSAFE_GIT,
            run_id=None,
            standard_version=None,
            blockers=(
                Blocker(
                    "repository_root_symlink",
                    "The selected repository root is a symbolic link.",
                    "Open the real repository directory before coordinator upgrade.",
                ),
            ),
            recommended_next_action="Open the real repository directory before coordinator upgrade.",
        )
    repo = selected.resolve(strict=True)
    inspection = inspect_repository(repo)
    slug = derive_project_slug(repo.name)
    if inspection.blockers:
        return _blocked(command, inspection, inspection.blockers[0], slug=slug)
    if inspection.git.kind in {RepoKind.BARE_GIT, RepoKind.UNSAFE_GIT}:
        return _blocked(
            command,
            inspection,
            Blocker(
                "unsupported_git_shape",
                "Coordinator upgrade requires a normal safe Git checkout.",
                "Place the existing project in a normal Git checkout before running the upgrade.",
            ),
            slug=slug,
        )
    incomplete = find_incomplete_runs(repo)
    if incomplete:
        return _blocked(
            command,
            inspection,
            Blocker(
                "incomplete_prior_run",
                "An earlier coordinator run is unresolved.",
                "Run reconcile and choose an evidence-supported recovery action.",
                tuple(path.name for path in incomplete),
            ),
            slug=slug,
        )
    if _current_installation_is_complete(inspection):
        return OperationResult(
            command=command,
            ok=True,
            changed=False,
            repository=slug,
            repo_kind=inspection.git.kind,
            run_id=None,
            standard_version=STANDARD_VERSION,
            recommended_next_action="Continue normal coordination.",
        )
    if inspection.installed_version in {
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
    }:
        return _upgrade_v30(repo, inspection, check=check)
    if inspection.installed_version is not None:
        return _blocked(
            command,
            inspection,
            Blocker(
                "unsupported_standard_version",
                f"Installed coordinator version {inspection.installed_version} has no supported migration route.",
                "Use a supported sequential migration; do not skip an unknown version.",
                ("docs/codex/STANDARD.json",),
            ),
            slug=slug,
        )
    initialized = initialize(repo, check=check, project_slug=slug)
    return replace(initialized, command=command)
def _validation_mappings(repo: Path) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "name": check.name,
            "ok": check.ok,
            "severity": check.severity,
            "message": redact_text(check.message),
        }
        for check in validate_repository(repo)
    )


def _installed_slug(repo: Path) -> str:
    try:
        content = read_regular_file(
            repo,
            repo / "docs/codex/STANDARD.json",
            max_bytes=4 * 1024 * 1024,
        )
        data = strict_json_loads(content) if content is not None else None
        slug = data.get("project_slug") if isinstance(data, dict) else None
        return validate_project_slug(slug) if isinstance(slug, str) else "."
    except (CoordinatorError, UnicodeError, json.JSONDecodeError, ValueError):
        return "."


def doctor(repo: Path) -> OperationResult:
    """Run deterministic, read-only Standard 3 repository validation."""

    command = "doctor"
    original = Path(os.path.abspath(repo))
    if original.is_symlink():
        return OperationResult(
            command=command,
            ok=False,
            changed=False,
            repository=".",
            repo_kind=RepoKind.UNSAFE_GIT,
            run_id=None,
            standard_version=None,
            blockers=(
                Blocker(
                    "repository_root_symlink",
                    "The selected repository root is a symbolic link.",
                    "Open the real repository directory and retry doctor.",
                ),
            ),
            recommended_next_action="Open the real repository directory and retry doctor.",
        )
    repo = original.resolve(strict=True)
    inspection = inspect_repository(repo)
    slug = _installed_slug(repo)
    try:
        checks = _validation_mappings(repo)
    except (CoordinatorError, OSError) as error:
        blocker = (
            error.blocker
            if isinstance(error, CoordinatorError)
            else Blocker(
                "doctor_io_failure",
                "Doctor could not safely read the coordinator contract.",
                "Repair the reported managed path and retry.",
            )
        )
        return _blocked(command, inspection, blocker, slug=slug)
    failed = tuple(check for check in checks if not check["ok"])
    blockers = (
        (
            Blocker(
                "repository_validation_failed",
                "The coordinator repository contract failed validation.",
                "Repair the failed named checks before coordinator mutation.",
            ),
        )
        if failed
        else ()
    )
    return OperationResult(
        command=command,
        ok=not failed,
        changed=False,
        repository=slug,
        repo_kind=inspection.git.kind,
        run_id=None,
        standard_version=inspection.installed_version,
        blockers=blockers,
        warnings=inspection.warnings,
        validation=checks,
        recommended_next_action=(
            "Continue normal coordination."
            if not failed
            else "Repair the failed named checks before coordinator mutation."
        ),
        metadata={"current": not failed and inspection.installed_version == STANDARD_VERSION},
    )


def check_current(repo: Path) -> OperationResult:
    """Report whether the repository is structurally current without mutation."""

    original = Path(os.path.abspath(repo))
    if original.is_symlink():
        return replace(doctor(original), command="check-current")
    resolved = original.resolve(strict=True)
    inspection = inspect_repository(resolved)
    slug = _installed_slug(resolved)
    if inspection.installed_version == STANDARD_VERSION:
        checked = doctor(resolved)
        current = checked.ok
        return replace(
            checked,
            command="check-current",
            metadata={
                "current": current,
                "installed_version": inspection.installed_version,
                "available_version": STANDARD_VERSION,
                "explicit_upgrade_would_change": not current,
            },
            recommended_next_action=(
                "Continue normal coordination."
                if current
                else "Run doctor and explicitly repair the reported drift."
            ),
        )
    return OperationResult(
        command="check-current",
        ok=not inspection.blockers,
        changed=False,
        repository=slug,
        repo_kind=inspection.git.kind,
        run_id=None,
        standard_version=inspection.installed_version,
        blockers=inspection.blockers,
        warnings=inspection.warnings,
        recommended_next_action="Request an explicit coordinator setup or upgrade.",
        metadata={
            "current": False,
            "installed_version": inspection.installed_version,
            "available_version": STANDARD_VERSION,
            "explicit_upgrade_would_change": not inspection.blockers,
        },
    )


def _canonical_report_for_journal(path: Path, run_id: str) -> str | None:
    suffix = f"-{run_id}.journal.json"
    if not path.name.endswith(suffix):
        return None
    stamp = path.name[: -len(suffix)]
    if re.fullmatch(r"[0-9]{8}T[0-9]{6}Z", stamp) is None:
        return None
    return f"docs/codex/MIGRATIONS/{stamp}-{run_id}.report.md"


def _hard_allowed_recovery_path(relative: str, action: str, report_path: str) -> bool:
    if relative == ".git":
        return action == "git-init"
    if relative in _ALLOWED_FIXED:
        return True
    return relative == report_path and bool(
        re.fullmatch(
            r"docs/codex/MIGRATIONS/[0-9]{8}T[0-9]{6}Z-[0-9a-f-]{36}\.report\.md",
            relative,
        )
    )


def _journal_validation_errors(
    repo: Path, path: Path, data: dict[str, Any], raw: bytes
) -> tuple[str, ...]:
    errors: list[str] = list(validate_schema_document(data, "journal.schema.json"))
    run_id = data.get("run_id")
    report_path = (
        _canonical_report_for_journal(path, run_id)
        if isinstance(run_id, str)
        else None
    )
    if report_path is None or data.get("report_path") != report_path:
        errors.append("journal filename/report correlation")
    if not repository_identity_matches(repo, data):
        errors.append("repository identity mismatch")
    authority = data.get("authority")
    if not isinstance(authority, dict) or data.get("command") != authority.get("command"):
        errors.append("authority command mismatch")
        authority = {}
    allowed_paths = authority.get("allowed_paths", [])
    operations = data.get("planned_operations", [])
    receipts = data.get("file_hashes", [])
    if not isinstance(operations, list) or not isinstance(receipts, list):
        errors.append("operation evidence malformed")
        operations = []
        receipts = []
    operation_paths: list[str] = []
    for operation in operations:
        if not isinstance(operation, dict):
            errors.append("operation evidence malformed")
            continue
        relative = operation.get("relative_path")
        action = operation.get("action")
        if not isinstance(relative, str) or not isinstance(action, str):
            errors.append("operation path malformed")
            continue
        operation_paths.append(relative)
        if report_path is None or not _hard_allowed_recovery_path(relative, action, report_path):
            errors.append("operation outside hard allowlist")
        if relative not in allowed_paths:
            errors.append("operation outside immutable authority")
        reversal = operation.get("reversal")
        if not isinstance(reversal, dict):
            errors.append("reversal evidence malformed")
        elif action == "create" and (
            operation.get("before_sha256") is not None
            or not isinstance(operation.get("after_sha256"), str)
            or reversal.get("kind") != "delete-new"
        ):
            errors.append("create/reversal mismatch")
        elif action == "replace" and operation.get("before_sha256") is None:
            errors.append("replace/preimage mismatch")
        elif action == "git-init" and relative != ".git":
            errors.append("git-init path mismatch")
    receipt_paths: list[str] = []
    for receipt in receipts:
        if not isinstance(receipt, dict) or not isinstance(receipt.get("relative_path"), str):
            errors.append("file receipt malformed")
            continue
        receipt_paths.append(receipt["relative_path"])
        if receipt["relative_path"] not in operation_paths:
            errors.append("file receipt outside plan")
    phases = [
        item.get("phase")
        for item in data.get("phase_history", [])
        if isinstance(item, dict)
    ]
    if phases != ["inspect", "plan", "apply", "validate", "finalize"][: len(phases)]:
        errors.append("phase order mismatch")
    serialized = raw.decode("utf-8", errors="replace")
    if contains_credential(serialized) or any(
        marker in serialized for marker in ("/Users/", "/Volumes/", "C:\\Users\\")
    ):
        errors.append("sensitive journal evidence")
    current_git = journal_git_evidence(inspect_repository(repo))
    recorded = data.get("post_apply_git") if "apply" in phases else data.get("starting_git")
    if isinstance(recorded, dict):
        stable_fields = (
            "worktree_identity_sha256",
            "common_dir_identity_sha256",
        )
        if any(recorded.get(name) != getattr(current_git, name) for name in stable_fields):
            errors.append("worktree identity mismatch")
    else:
        errors.append("git evidence malformed")
    return tuple(sorted(set(errors)))


def _journal_candidates(repo: Path) -> tuple[Path, ...]:
    migrations = repo / "docs/codex/MIGRATIONS"
    if not migrations.is_dir() or migrations.is_symlink():
        return ()
    return tuple(sorted(migrations.glob("*.journal.json")))


def _load_journal_candidate(
    repo: Path, path: Path
) -> tuple[dict[str, Any] | None, bytes | None, tuple[str, ...]]:
    try:
        raw = read_regular_file(repo, path, max_bytes=4 * 1024 * 1024)
        if raw is None:
            return None, None, ("journal missing",)
        parsed = strict_json_loads(raw)
        if not isinstance(parsed, dict):
            return None, raw, ("journal root malformed",)
        return parsed, raw, _journal_validation_errors(repo, path, parsed, raw)
    except (CoordinatorError, UnicodeError, json.JSONDecodeError, ValueError):
        return None, None, ("journal unreadable",)


def _current_operation_hashes(repo: Path, data: dict[str, Any]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for item in data.get("planned_operations", []):
        if not isinstance(item, dict) or not isinstance(item.get("relative_path"), str):
            continue
        if item.get("action") == "git-init":
            continue
        relative = item["relative_path"]
        try:
            content = read_regular_file(
                repo, repo / relative, max_bytes=64 * 1024 * 1024
            )
            hashes[relative] = sha256_bytes(content) if content is not None else "absent"
        except CoordinatorError:
            hashes[relative] = "unsafe"
    return hashes


def _recovery_decision_token(
    repo: Path,
    path: Path,
    data: dict[str, Any],
    raw: bytes,
    action: RecoveryAction,
) -> str:
    inspection = inspect_repository(repo)
    git = journal_git_evidence(inspection)
    lock_path = repo / "docs/codex/MIGRATIONS/.coordinator.lock"
    try:
        lock_bytes = read_regular_file(repo, lock_path, max_bytes=64 * 1024)
        lock_hash = sha256_bytes(lock_bytes) if lock_bytes is not None else "absent"
    except CoordinatorError:
        lock_hash = "unsafe"
    material = {
        "action": action.value,
        "standard_version": STANDARD_VERSION,
        "run_id": data.get("run_id"),
        "journal_name": path.name,
        "journal_sha256": sha256_bytes(raw),
        "repository_identity": data.get("repository_identity"),
        "current_file_hashes": _current_operation_hashes(repo, data),
        "git": {
            "kind": git.kind,
            "head": git.head,
            "explicit_base": git.explicit_base,
            "branch": git.branch,
            "is_detached": git.is_detached,
            "worktree_identity_sha256": git.worktree_identity_sha256,
            "common_dir_identity_sha256": git.common_dir_identity_sha256,
        },
        "lock_sha256": lock_hash,
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _serialized_blockers(blockers: tuple[Blocker, ...]) -> list[dict[str, Any]]:
    return [
        {
            "code": redact_text(blocker.code),
            "message": redact_text(blocker.message),
            "recovery": redact_text(blocker.recovery),
            "paths": [redact_text(path) for path in blocker.paths],
        }
        for blocker in blockers
    ]


def _installed_project_id(repo: Path) -> UUID | None:
    try:
        raw = read_regular_file(
            repo,
            repo / "docs/codex/STANDARD.json",
            max_bytes=4 * 1024 * 1024,
        )
        data = strict_json_loads(raw) if raw is not None else None
        value = data.get("project_id") if isinstance(data, dict) else None
        return UUID(value) if isinstance(value, str) else None
    except (CoordinatorError, UnicodeError, json.JSONDecodeError, ValueError):
        return None


def _lock_only_candidate(
    repo: Path,
) -> tuple[dict[str, Any] | None, bytes | None, Blocker | None]:
    """Validate a local stale lock whose promised journal was never created."""

    lock_path = repo / "docs/codex/MIGRATIONS/.coordinator.lock"
    try:
        raw = read_regular_file(repo, lock_path, max_bytes=64 * 1024)
    except CoordinatorError as error:
        return None, None, error.blocker
    if raw is None:
        return None, None, None
    try:
        data = strict_json_loads(raw)
        if not isinstance(data, dict):
            raise ValueError("lock root")
        # Reuse the exact public lock payload contract without creating a file.
        ExclusiveRunLock(repo, lock_path, data)._validated_payload()
    except (CoordinatorError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        blocker = (
            error.blocker
            if isinstance(error, CoordinatorError)
            else Blocker(
                "recovery_lock_malformed",
                "The coordinator lock metadata is malformed.",
                "Preserve the lock and use a reviewed manual recovery plan.",
            )
        )
        return None, raw, blocker
    run_id = data["run_id"]
    journal_relative = data["journal_path"]
    journal_path = repo / journal_relative
    if any(
        candidate.name == journal_path.name
        or (
            _load_journal_candidate(repo, candidate)[0] or {}
        ).get("run_id") == run_id
        for candidate in _journal_candidates(repo)
    ):
        return None, raw, None
    if read_regular_file(repo, journal_path, max_bytes=64 * 1024 * 1024) is not None:
        return None, raw, None
    expected_host = hashlib.sha256(str(getnode()).encode("ascii")).hexdigest()
    if data.get("host_id_sha256") != expected_host:
        return None, raw, Blocker(
            "recovery_lock_conflicting",
            "The journal-free lock belongs to another host identity.",
            "Preserve it and verify ownership manually before mutation.",
        )
    try:
        os.kill(data["pid"], 0)
        return None, raw, Blocker(
            "active_coordinator_run",
            "The journal-free coordinator process is still active.",
            "Wait for it to finish before recovery.",
        )
    except PermissionError:
        return None, raw, Blocker(
            "recovery_lock_conflicting",
            "The journal-free coordinator process cannot be verified.",
            "Preserve it and verify process ownership manually.",
        )
    except ProcessLookupError:
        return data, raw, None


def _lock_only_decision_token(
    repo: Path, data: dict[str, Any], raw: bytes
) -> str:
    inspection = inspect_repository(repo)
    material = {
        "action": RecoveryAction.SUPERSEDE.value,
        "standard_version": STANDARD_VERSION,
        "run_id": data["run_id"],
        "journal_name": Path(data["journal_path"]).name,
        "stale_lock_sha256": sha256_bytes(raw),
        "project_id": str(_installed_project_id(repo)),
        "git": asdict(journal_git_evidence(inspection)),
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _durable_status_picture(
    repo: Path, inspection: Inspection
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Summarize STATUS without returning repository-controlled prose."""

    path = repo / "docs/codex/STATUS.md"
    try:
        raw = read_regular_file(repo, path, max_bytes=4 * 1024 * 1024)
    except CoordinatorError:
        return (
            {"state": "unsafe", "sections": []},
            [{"status": "conflicting", "claim": "durable-status:unsafe"}],
        )
    if raw is None:
        return (
            {"state": "missing", "sections": []},
            [{"status": "unknown", "claim": "durable-status:missing"}],
        )
    text = raw.decode("utf-8", errors="replace")
    sections: list[dict[str, Any]] = []
    evidence: list[dict[str, str]] = [
        {"status": "verified", "claim": "durable-status:file-present"}
    ]
    matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        heading = redact_text(match.group(1).strip())
        corroborated = bool(
            body
            and (
                (inspection.git.head and inspection.git.head in body)
                or (inspection.git.branch and inspection.git.branch in body)
            )
        )
        status = "inferred" if body else "unknown"
        sections.append(
            {
                "heading": heading,
                "content_sha256": sha256_bytes(body.encode("utf-8")),
                "nonempty": bool(body),
                "evidence_status": status,
            }
        )
        evidence.append(
            {"status": status, "claim": f"durable-status-section:{heading}"}
        )
        if corroborated:
            evidence.append(
                {
                    "status": "verified",
                    "claim": f"durable-status-git-correlation:{heading}",
                }
            )
    if contains_credential(text):
        evidence.append(
            {"status": "conflicting", "claim": "durable-status:credential-shaped-content"}
        )
    return (
        {
            "state": "present",
            "sha256": sha256_bytes(raw),
            "section_count": len(sections),
            "sections": sections,
            "checkpoint_present": bool(re.search(r"(?im)^checkpoint recorded:\s*\S+", text)),
        },
        evidence,
    )


def _operating_picture(repo: Path, inspection: Inspection) -> dict[str, Any]:
    git = recovery_git_picture(repo)
    status, evidence = _durable_status_picture(repo, inspection)
    git_evidence: list[dict[str, str]] = [
        {
            "status": "verified" if git.get("head") else "unknown",
            "claim": "git:current-head",
        },
        {
            "status": "verified" if git.get("branch") else "unknown",
            "claim": "git:current-branch",
        },
        {"status": "verified", "claim": "git:branches"},
        {"status": "verified", "claim": "git:worktrees"},
        {
            "status": "verified" if git.get("recent_commits") else "unknown",
            "claim": "git:recent-commits",
        },
        {"status": "unknown", "claim": "native-tasks:unavailable"},
    ]
    return {
        "durable_status": status,
        "git": git,
        "evidence": [*evidence, *git_evidence],
    }


def reconcile(repo: Path) -> OperationResult:
    """Return a read-only operating picture for interrupted coordinator runs."""

    original = Path(os.path.abspath(repo))
    if original.is_symlink():
        return replace(doctor(original), command="reconcile")
    repo = original.resolve(strict=True)
    inspection = inspect_repository(repo)
    slug = _installed_slug(repo)
    operating_picture = _operating_picture(repo, inspection)
    paths = find_incomplete_runs(repo)
    runs: list[dict[str, Any]] = []
    for path in paths:
        data, raw, errors = _load_journal_candidate(repo, path)
        if data is None or raw is None or errors:
            runs.append(
                {
                    "journal": redact_text(path.name),
                    "run_id": data.get("run_id") if isinstance(data, dict) else None,
                    "status": "blocked",
                    "evidence": [{"status": "conflicting", "claim": "journal"}],
                    "safe_actions": [],
                    "recommended_action": RecoveryAction.REPAIR.value,
                    "blockers": [
                        {
                            "code": "invalid_recovery_journal",
                            "message": "The interrupted run journal failed strict validation.",
                            "recovery": "Inspect the named journal and request a fingerprint-bound repair decision.",
                            "paths": [redact_text(path.name)],
                        }
                    ],
                    "validation_errors": list(errors),
                }
            )
            continue
        picture = classify_run(repo, path)
        safe_actions = [action.value for action in picture.safe_actions]
        runs.append(
            {
                "journal": redact_text(path.name),
                "run_id": picture.run_id,
                "status": picture.status.value,
                "evidence": [dict(item) for item in picture.evidence],
                "safe_actions": safe_actions,
                "recommended_action": (
                    picture.recommended_action.value
                    if picture.recommended_action is not None
                    else None
                ),
                "blockers": _serialized_blockers(picture.blockers),
                "decision_tokens": {
                    action.value: _recovery_decision_token(repo, path, data, raw, action)
                    for action in (
                        RecoveryAction.ROLLBACK,
                        RecoveryAction.REPAIR,
                        RecoveryAction.SUPERSEDE,
                    )
                    if action in picture.safe_actions
                    or action in {RecoveryAction.REPAIR, RecoveryAction.SUPERSEDE}
                },
            }
        )
    lock = classify_lock(
        repo / "docs/codex/MIGRATIONS/.coordinator.lock",
        _journal_candidates(repo),
    )
    lock_only, lock_raw, lock_only_blocker = _lock_only_candidate(repo)
    lock_metadata: dict[str, Any] = {
        "state": lock.state,
        "run_id": lock.run_id,
        "journal": redact_text(Path(lock.journal_path).name) if lock.journal_path else None,
        "safe_actions": [],
        "recommended_action": None,
        "decision_tokens": {},
    }
    if lock_only is not None and lock_raw is not None:
        lock_metadata.update(
            {
                "safe_actions": [RecoveryAction.SUPERSEDE.value],
                "recommended_action": RecoveryAction.SUPERSEDE.value,
                "decision_tokens": {
                    RecoveryAction.SUPERSEDE.value: _lock_only_decision_token(
                        repo, lock_only, lock_raw
                    )
                },
            }
        )
    elif lock_only_blocker is not None:
        lock_metadata["blockers"] = _serialized_blockers((lock_only_blocker,))
    warnings = tuple(inspection.warnings) + (
        "Native task metadata unavailable on this execution surface; durable repository and Git evidence were checked.",
    )
    return OperationResult(
        command="reconcile",
        ok=not inspection.blockers,
        changed=False,
        repository=slug,
        repo_kind=inspection.git.kind,
        run_id=None,
        standard_version=inspection.installed_version,
        blockers=inspection.blockers,
        warnings=warnings,
        recommended_next_action=(
            "Choose only an action listed as safe for the interrupted run."
            if runs or lock_metadata["safe_actions"]
            else "No interrupted coordinator run requires recovery."
        ),
        metadata={
            "operating_picture": operating_picture,
            "runs": runs,
            "lock": lock_metadata,
            "native_task_metadata": "unavailable",
        },
    )


def _find_run_by_id(
    repo: Path, run_id: str
) -> tuple[Path | None, dict[str, Any] | None, bytes | None, tuple[str, ...]]:
    try:
        if str(UUID(run_id)) != run_id:
            return None, None, None, ("run id malformed",)
    except ValueError:
        return None, None, None, ("run id malformed",)
    matches: list[tuple[Path, dict[str, Any], bytes, tuple[str, ...]]] = []
    for path in _journal_candidates(repo):
        data, raw, errors = _load_journal_candidate(repo, path)
        if data is not None and raw is not None and data.get("run_id") == run_id:
            matches.append((path, data, raw, errors))
    if len(matches) != 1:
        return None, None, None, ("run id is missing or duplicated",)
    return matches[0]


def _recovery_report(run_id: str, action: RecoveryAction) -> bytes:
    result = {
        RecoveryAction.ROLLBACK: "the guarded rollback completed using matching journal and file-hash evidence",
        RecoveryAction.SUPERSEDE: "the inactive run was superseded after an action-specific state decision",
        RecoveryAction.RESUME: "the fully applied candidate was validated and finalized",
        RecoveryAction.REPAIR: "the reviewed repair disposition was recorded",
    }.get(action, "the recovery disposition was recorded")
    return (
        "# Coordinator Recovery Report\n\n"
        "## Summary\n\n"
        f"- Run ID: `{run_id}`\n"
        f"- Recovery action: `{action.value}`\n"
        f"- Result: {result}.\n\n"
        "## Files changed\n\nOnly journal-authorized coordinator recovery records and the named recovery report were changed.\n\n"
        "## Validation run\n\nCurrent hashes, authority, journal identity, and the selected action were checked before mutation.\n\n"
        "## Review findings\n\nNo product-file authority was granted by recovery.\n\n"
        "## P0/P1 status\n\nNo P0/P1 finding was introduced by the bounded recovery action.\n\n"
        "## P2/P3 disposition\n\nFollow-up cleanup remains explicit and separate.\n\n"
        "## Remaining risks\n\nNative task state and external systems were not inspected on this execution surface.\n\n"
        "## Next step\n\nRun `doctor` before starting another coordinator mutation.\n\n"
        "No product files, Git metadata, commits, remotes, deployments, secrets, or external systems were changed.\n"
    ).encode("utf-8")


def _recover_lock_only(
    repo: Path,
    inspection: Inspection,
    slug: str,
    data: dict[str, Any],
    raw: bytes,
    decision_token: str | None,
) -> OperationResult:
    run_id = data["run_id"]
    expected = _lock_only_decision_token(repo, data, raw)
    if decision_token is None or not hmac.compare_digest(decision_token, expected):
        return _blocked(
            "recover",
            inspection,
            Blocker(
                "recovery_decision_required",
                "Journal-free stale-lock recovery requires the current supersede token.",
                "Run reconcile, review the lock-only evidence, and approve its supersede token.",
            ),
            slug=slug,
            run_id=run_id,
            metadata={"decision_token": expected},
        )
    project_id = _installed_project_id(repo)
    if project_id is None:
        return _blocked(
            "recover",
            inspection,
            Blocker(
                "recovery_identity_missing",
                "The installed project identity is unavailable for a recovery journal.",
                "Repair STANDARD.json before superseding the journal-free lock.",
            ),
            slug=slug,
            run_id=run_id,
        )
    journal_relative = data["journal_path"]
    journal_path = repo / journal_relative
    stamp = journal_path.name.split("-", 1)[0]
    try:
        moment = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return _blocked(
            "recover",
            inspection,
            Blocker(
                "recovery_lock_malformed",
                "The journal-free lock has an invalid journal timestamp.",
                "Preserve it and use a reviewed manual recovery plan.",
            ),
            slug=slug,
            run_id=run_id,
        )
    report_relative = journal_relative.replace(".journal.json", ".report.md")
    now = _utc_now()
    authority = AuthorityGrant(
        command="recover",
        mutation_classes=("coordinator-recovery",),
        allowed_paths=(journal_relative, report_relative),
        decisions=(("lock-only-supersede", sha256_bytes(expected.encode("ascii"))),),
        created_at=_utc_text(now),
        source_id="current-task:approved-recovery-token",
    )
    lock_path = repo / "docs/codex/MIGRATIONS/.coordinator.lock"
    replacement_lock = ExclusiveRunLock(
        repo,
        lock_path,
        {
            "run_id": run_id,
            "host_id_sha256": hashlib.sha256(str(getnode()).encode("ascii")).hexdigest(),
            "pid": os.getpid(),
            "created_at": _utc_text(now),
            "journal_path": journal_relative,
        },
    )
    try:
        replacement_lock.replace_stale(sha256_bytes(raw))
        journal = RunJournal.create(
            repo,
            run_id,
            "recover",
            inspection,
            authority,
            project_id,
            now=moment,
            visibility_guard=replacement_lock.assert_visible,
            project_slug=slug,
        )
        journal.transition(Phase.INSPECT, {"lock_only": True}, now=now)
        replacement_lock.assert_visible()
        report = _recovery_report(run_id, RecoveryAction.SUPERSEDE)
        report_path = repo / report_relative
        atomic_write(
            report_path,
            report,
            root=repo,
            public=True,
            expected_sha256=None,
        )
        journal.finish(
            RunStatus.SUPERSEDED,
            "The journal-free stale lock was superseded; run doctor before mutation.",
            report_relative,
            sha256_bytes(report),
            now=now,
        )
        return OperationResult(
            command="recover",
            ok=True,
            changed=True,
            repository=slug,
            repo_kind=inspection.git.kind,
            run_id=run_id,
            standard_version=inspection.installed_version,
            operations=(
                {"action": "supersede-lock-only", "relative_path": journal_path.name},
                {"action": "create-report", "relative_path": report_path.name},
            ),
            recommended_next_action="Run doctor before starting another coordinator mutation.",
            metadata={"action": RecoveryAction.SUPERSEDE.value, "report": report_relative},
        )
    except CoordinatorError as error:
        return _blocked(
            "recover",
            inspection,
            error.blocker,
            slug=slug,
            run_id=run_id,
        )
    finally:
        replacement_lock.release()


def _prepare_recovery_lock(
    repo: Path,
    path: Path,
    data: dict[str, Any],
) -> tuple[Blocker | None, str | None]:
    lock_path = repo / "docs/codex/MIGRATIONS/.coordinator.lock"
    try:
        raw = read_regular_file(repo, lock_path, max_bytes=64 * 1024)
    except CoordinatorError:
        return Blocker(
            "recovery_lock_unsafe",
            "The coordinator lock is not a safe regular file.",
            "Repair lock ownership before recovery mutation.",
        ), None
    if raw is None:
        return None, None
    try:
        lock_data = strict_json_loads(raw)
    except (UnicodeError, json.JSONDecodeError, ValueError):
        return Blocker(
            "recovery_lock_malformed",
            "The coordinator lock metadata is malformed.",
            "Use a reviewed fingerprint-bound supersede decision.",
        ), None
    expected_keys = {"run_id", "host_id_sha256", "pid", "created_at", "journal_path"}
    expected_host = hashlib.sha256(str(getnode()).encode("ascii")).hexdigest()
    expected_journal = f"docs/codex/MIGRATIONS/{path.name}"
    if (
        not isinstance(lock_data, dict)
        or set(lock_data) != expected_keys
        or lock_data.get("run_id") != data.get("run_id")
        or lock_data.get("journal_path") != expected_journal
        or lock_data.get("host_id_sha256") != expected_host
        or not isinstance(lock_data.get("pid"), int)
        or isinstance(lock_data.get("pid"), bool)
        or lock_data["pid"] <= 0
    ):
        return Blocker(
            "recovery_lock_conflicting",
            "The coordinator lock cannot be correlated with this local run.",
            "Preserve it and use a reviewed fingerprint-bound recovery decision.",
        ), None
    try:
        os.kill(lock_data["pid"], 0)
        return Blocker(
            "active_coordinator_run",
            "The correlated coordinator process is still active.",
            "Wait for it to finish or verify process ownership before recovery.",
        ), None
    except PermissionError:
        return Blocker(
            "recovery_lock_conflicting",
            "The correlated coordinator process cannot be verified.",
            "Preserve the lock and verify process ownership manually.",
        ), None
    except ProcessLookupError:
        pass
    lock_hash = sha256_bytes(raw)
    return None, lock_hash


def _resume_terminal_candidate(
    repo: Path,
    path: Path,
    data: dict[str, Any],
    raw: bytes,
    *,
    candidate_overlay: dict[str, bytes] | None = None,
) -> tuple[bytes, tuple[dict[str, Any], ...]]:
    prospective = json.loads(json.dumps(data))
    now = _utc_now()
    timestamp = _utc_text(now)
    phases = [
        item.get("phase")
        for item in prospective.get("phase_history", [])
        if isinstance(item, dict)
    ]
    ordered = ["inspect", "plan", "apply", "validate", "finalize"]
    for phase in ordered[len(phases) :]:
        prospective["phase_history"].append(
            {
                "phase": phase,
                "at": timestamp,
                "evidence": ["recovery=verified fully applied candidate"],
            }
        )
    inspection = inspect_repository(repo)
    prospective["post_apply_git"] = asdict(journal_git_evidence(inspection))
    prospective["file_hashes"] = [
        {
            "relative_path": operation["relative_path"],
            "before_sha256": operation.get("before_sha256"),
            "after_sha256": operation.get("after_sha256"),
        }
        for operation in prospective["planned_operations"]
        if operation.get("action") != "git-init"
    ]
    report_path = prospective["report_path"]
    overlay = dict(candidate_overlay or {})
    report = overlay.get(report_path)
    if report is None:
        report = read_regular_file(
            repo, repo / report_path, max_bytes=64 * 1024 * 1024
        )
    if report is None:
        raise CoordinatorError(
            Blocker(
                "resume_report_missing",
                "The fully applied run has no matching final report.",
                "Choose rollback or reviewed repair; do not claim completion.",
            )
        )
    prospective["report_sha256"] = sha256_bytes(report)
    prospective["status"] = RunStatus.COMPLETE.value
    prospective["next_action"] = "Continue normal coordination after recovered validation."
    prospective["updated_at"] = timestamp
    seed = (
        {
            "name": "recovery-current-hashes",
            "ok": True,
            "severity": "P1",
            "message": "Every planned after-hash matched before recovery finalization.",
        },
    )
    recovery_receipts = tuple(
        dict(item)
        for item in prospective.get("validation", [])
        if isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and item["name"].startswith("recovery-")
        and item.get("ok") is True
    )
    checks = seed
    previous: tuple[tuple[str, bool], ...] | None = None
    relative_journal = path.relative_to(repo).as_posix()
    for _iteration in range(3):
        prospective["validation"] = [
            *recovery_receipts,
            *(dict(item) for item in checks),
        ]
        content = (json.dumps(prospective, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        validation_overlay = dict(overlay)
        validation_overlay[relative_journal] = content
        candidate = tuple(
            {
                "name": check.name,
                "ok": check.ok,
                "severity": check.severity,
                "message": check.message,
            }
            for check in validate_repository(
                repo, candidate_overlay=validation_overlay
            )
        )
        signature = tuple((item["name"], item["ok"]) for item in candidate)
        if previous == signature:
            _require_candidate(candidate)
            prospective["validation"] = [
                *recovery_receipts,
                *(dict(item) for item in candidate),
            ]
            final = (json.dumps(prospective, indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            )
            return final, candidate
        previous = signature
        checks = candidate
    raise CoordinatorError(
        Blocker(
            "resume_validation_drift",
            "Recovered terminal validation did not stabilize.",
            "Choose reviewed repair without completing the run.",
        )
    )


def _rebuild_interrupted_init(
    repo: Path, data: dict[str, Any]
) -> tuple[Operation, ...] | None:
    if data.get("command") != "init":
        return None
    slug_value = data.get("project_slug")
    identity = data.get("repository_identity")
    if not isinstance(slug_value, str) or not isinstance(identity, dict):
        return None
    try:
        slug = validate_project_slug(slug_value)
        project_id = UUID(identity["project_id"])
        moment = datetime.strptime(data["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except (KeyError, TypeError, ValueError):
        return None
    inspection = inspect_repository(repo)
    rendered = render_new_project(inspection, slug, moment, project_id)
    planned = {
        item.get("relative_path"): item
        for item in data.get("planned_operations", [])
        if isinstance(item, dict) and isinstance(item.get("relative_path"), str)
    }
    aligned: list[Operation] = []
    for operation in rendered:
        source = planned.get(operation.relative_path)
        if not isinstance(source, dict):
            return None
        reversal = source.get("reversal", {})
        metadata = tuple(
            (item["name"], item["value"])
            for item in reversal.get("metadata", [])
            if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and isinstance(item.get("value"), str)
        )
        aligned.append(
            replace(
                operation,
                action=source.get("action", operation.action),
                before_sha256=source.get("before_sha256"),
                reversal=ReversalEvidence(
                    reversal.get("kind", "unavailable"),
                    reversal.get("reference"),
                    metadata,
                ),
            )
        )
    rebuilt = _with_run_record(
        tuple(aligned),
        run_id=data["run_id"],
        timestamp=data["created_at"],
        source_version="unmanaged",
        report_path=data["report_path"],
        git_fingerprint=_git_evidence_fingerprint(inspection),
    )
    rebuilt_map = {item.relative_path: item for item in rebuilt}
    for relative, source in planned.items():
        if source.get("action") == "git-init":
            continue
        operation = rebuilt_map.get(relative)
        if operation is None or operation.after_sha256 != source.get("after_sha256"):
            return None
    return rebuilt


def _operation_from_journal_record(
    record: dict[str, Any], content: bytes
) -> Operation | None:
    relative = record.get("relative_path")
    action = record.get("action")
    after_hash = record.get("after_sha256")
    before_hash = record.get("before_sha256")
    reversal = record.get("reversal")
    if (
        not isinstance(relative, str)
        or action not in {"create", "replace"}
        or not isinstance(after_hash, str)
        or (before_hash is not None and not isinstance(before_hash, str))
        or not isinstance(reversal, dict)
    ):
        return None
    metadata = tuple(
        (item["name"], item["value"])
        for item in reversal.get("metadata", [])
        if isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and isinstance(item.get("value"), str)
    )
    return Operation(
        action=action,
        relative_path=relative,
        before_sha256=before_hash,
        after_sha256=after_hash,
        content=content,
        reversal=ReversalEvidence(
            reversal.get("kind", "unavailable"),
            reversal.get("reference"),
            metadata,
        ),
    )


def _rebuild_interrupted_upgrade(
    repo: Path, data: dict[str, Any]
) -> tuple[tuple[Operation, ...], dict[str, Any] | None] | None:
    """Rebuild a mid-skill upgrade only after every fixed target is exact."""

    if data.get("command") != "upgrade":
        return None
    planned = data.get("planned_operations")
    report_path = data.get("report_path")
    run_id = data.get("run_id")
    if (
        not isinstance(planned, list)
        or not isinstance(report_path, str)
        or not isinstance(run_id, str)
    ):
        return None
    rebuilt: list[Operation] = []
    amended = copy.deepcopy(data)
    amended_plan = amended.get("planned_operations")
    if not isinstance(amended_plan, list) or len(amended_plan) != len(planned):
        return None
    changed_plan = False
    saw_report = False
    for index, record in enumerate(planned):
        if not isinstance(record, dict) or record.get("action") == "git-init":
            return None
        relative = record.get("relative_path")
        before_hash = record.get("before_sha256")
        after_hash = record.get("after_sha256")
        if not isinstance(relative, str) or not isinstance(after_hash, str):
            return None
        try:
            current = read_regular_file(
                repo, repo / relative, max_bytes=64 * 1024 * 1024
            )
        except CoordinatorError:
            return None
        current_hash = sha256_bytes(current) if current is not None else None
        content: bytes | None = None
        if relative == report_path:
            saw_report = True
            if current is not None and current_hash == after_hash:
                content = current
            elif (
                current is not None
                and current_hash == data.get("report_sha256")
                and data.get("status")
                in {RunStatus.FAILED.value, RunStatus.BLOCKED.value}
            ):
                content = _recovery_report(run_id, RecoveryAction.REPAIR)
                repaired_hash = sha256_bytes(content)
                amended_record = amended_plan[index]
                if not isinstance(amended_record, dict):
                    return None
                amended_record["after_sha256"] = repaired_hash
                after_hash = repaired_hash
                changed_plan = True
            else:
                return None
        else:
            # This bounded repair is available only after the exact fixed
            # Standard candidate is already present. It never guesses a
            # partially rendered coordinator document.
            if current is None or current_hash != after_hash:
                return None
            content = current
        operation = _operation_from_journal_record(record, content)
        if operation is None:
            return None
        if operation.after_sha256 != after_hash:
            operation = replace(operation, after_sha256=after_hash)
        rebuilt.append(operation)
    if not saw_report:
        return None
    return tuple(rebuilt), amended if changed_plan else None


def recover_run(
    repo: Path,
    *,
    run_id: str,
    action: RecoveryAction,
    decision_token: str | None = None,
) -> OperationResult:
    """Perform one explicitly selected, evidence-bounded recovery action."""

    original = Path(os.path.abspath(repo))
    if original.is_symlink():
        return replace(doctor(original), command="recover")
    repo = original.resolve(strict=True)
    inspection = inspect_repository(repo)
    slug = _installed_slug(repo)
    if not isinstance(action, RecoveryAction):
        try:
            action = RecoveryAction(action)
        except (TypeError, ValueError):
            return _blocked(
                "recover",
                inspection,
                Blocker(
                    "unsupported_recovery_action",
                    "The requested recovery action is unsupported.",
                    "Choose resume, rollback, repair, or supersede from reconcile output.",
                ),
                slug=slug,
            )
    if action is RecoveryAction.SUPERSEDE:
        lock_only, lock_raw, _lock_blocker = _lock_only_candidate(repo)
        if (
            lock_only is not None
            and lock_raw is not None
            and lock_only.get("run_id") == run_id
        ):
            return _recover_lock_only(
                repo,
                inspection,
                slug,
                lock_only,
                lock_raw,
                decision_token,
            )
    path, data, raw, errors = _find_run_by_id(repo, run_id)
    if path is None or data is None or raw is None or errors:
        return _blocked(
            "recover",
            inspection,
            Blocker(
                "invalid_recovery_journal",
                "The requested interrupted run is missing, duplicated, or invalid.",
                "Run reconcile and repair the journal evidence before mutation.",
            ),
            slug=slug,
            run_id=run_id,
        )
    if action in {RecoveryAction.REPAIR, RecoveryAction.SUPERSEDE}:
        expected = _recovery_decision_token(repo, path, data, raw, action)
        if decision_token is None or not hmac.compare_digest(decision_token, expected):
            return _blocked(
                "recover",
                inspection,
                Blocker(
                    "recovery_decision_required",
                    "This recovery action requires the current action-specific decision token.",
                    "Run reconcile, review the current evidence, and approve the matching token.",
                ),
                slug=slug,
                run_id=run_id,
                metadata={"decision_token": expected},
            )
    picture = classify_run(repo, path)
    if action is RecoveryAction.ROLLBACK and action not in picture.safe_actions:
        blocker = picture.blockers[0] if picture.blockers else Blocker(
            "rollback_not_provable",
            "The interrupted run does not have complete reconstructive rollback evidence.",
            "Choose repair or a new fingerprint-bound decision after inspection.",
        )
        return _blocked("recover", inspection, blocker, slug=slug, run_id=run_id)
    if action is RecoveryAction.ROLLBACK:
        expected = _recovery_decision_token(repo, path, data, raw, action)
        if decision_token is None or not hmac.compare_digest(decision_token, expected):
            return _blocked(
                "recover",
                inspection,
                Blocker(
                    "recovery_decision_required",
                    "Rollback requires the current action-specific decision token.",
                    "Run reconcile, review every reconstructive reversal, and approve the rollback token.",
                ),
                slug=slug,
                run_id=run_id,
                metadata={"decision_token": expected},
            )
    if action is RecoveryAction.RESUME and action not in picture.safe_actions:
        blocker = picture.blockers[0] if picture.blockers else Blocker(
            "resume_not_provable",
            "The exact candidate is not fully applied at its recorded hashes.",
            "Choose rollback when listed safe, or request reviewed repair.",
        )
        return _blocked("recover", inspection, blocker, slug=slug, run_id=run_id)
    repair_operations: tuple[Operation, ...] | None = None
    repair_journal_data: dict[str, Any] | None = None
    if action is RecoveryAction.REPAIR:
        repair_operations = _rebuild_interrupted_init(repo, data)
        if repair_operations is None:
            rebuilt_upgrade = _rebuild_interrupted_upgrade(repo, data)
            if rebuilt_upgrade is not None:
                repair_operations, repair_journal_data = rebuilt_upgrade
        if repair_operations is None:
            return _blocked(
                "recover",
                inspection,
                Blocker(
                    "repair_requires_reviewed_plan",
                    "Repair cannot reconstruct the exact original candidate from durable evidence.",
                    "Create a reviewed repair plan from current repository evidence; the decision token does not authorize guessed bytes.",
                ),
                slug=slug,
                run_id=run_id,
            )
        try:
            _require_candidate(_candidate_checks(repair_operations))
            preflight_data = repair_journal_data or data
            preflight_raw = (
                json.dumps(preflight_data, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            _resume_terminal_candidate(
                repo,
                path,
                preflight_data,
                preflight_raw,
                candidate_overlay={
                    operation.relative_path: operation.content
                    for operation in repair_operations
                    if operation.content is not None
                },
            )
        except CoordinatorError as error:
            return _blocked(
                "recover", inspection, error.blocker, slug=slug, run_id=run_id
            )

    authority = data["authority"]
    operations = data["planned_operations"]
    receipts = {
        item["relative_path"]: item
        for item in data["file_hashes"]
        if isinstance(item, dict) and isinstance(item.get("relative_path"), str)
    }
    report_path = data["report_path"]
    current_hashes = _current_operation_hashes(repo, data)
    if action is RecoveryAction.SUPERSEDE:
        applied = [
            item["relative_path"]
            for item in operations
            if item.get("action") != "git-init"
            and current_hashes.get(item["relative_path"]) == item.get("after_sha256")
        ]
        if applied:
            return _blocked(
                "recover",
                inspection,
                Blocker(
                    "supersede_would_orphan_writes",
                    "The interrupted run still has applied file hashes.",
                    "Rollback when listed safe or use a reviewed repair before superseding.",
                    tuple(applied),
                ),
                slug=slug,
                run_id=run_id,
            )

    for operation in (operations if action is RecoveryAction.ROLLBACK else ()):
        relative = operation["relative_path"]
        if operation["action"] == "git-init" or relative == ".git":
            continue
        current = read_regular_file(
            repo, repo / relative, max_bytes=64 * 1024 * 1024
        )
        current_hash = sha256_bytes(current) if current is not None else None
        if current_hash == operation.get("before_sha256"):
            continue
        delete_new = (
            operation.get("reversal", {}).get("kind") == "delete-new"
            and relative == report_path
            and relative in receipts
            and receipts[relative].get("after_sha256")
            == operation.get("after_sha256")
        )
        recovery_report = (
            relative == report_path
            and current_hashes.get(relative) == data.get("report_sha256")
            and data.get("status") in {RunStatus.FAILED.value, RunStatus.BLOCKED.value}
        )
        reconstructive = reconstruct_preimage(repo, data, operation) is not None
        if (
            relative not in authority["allowed_paths"]
            or not _hard_allowed_recovery_path(relative, operation["action"], report_path)
            or not (delete_new or recovery_report or reconstructive)
        ):
            return _blocked(
                "recover",
                inspection,
                Blocker(
                    "rollback_authority_mismatch",
                    "Rollback evidence does not intersect the hard allowlist, authority, plan, and file receipt.",
                    "Inspect the run and choose a reviewed repair without automatic deletion.",
                    (relative,),
                ),
                slug=slug,
                run_id=run_id,
            )

    lock_path = repo / "docs/codex/MIGRATIONS/.coordinator.lock"
    journal = RunJournal(repo, path, data)
    lock_blocker, stale_lock_hash = _prepare_recovery_lock(repo, path, data)
    if lock_blocker is not None:
        return _blocked(
            "recover",
            inspection,
            lock_blocker,
            slug=slug,
            run_id=run_id,
        )
    timestamp = _utc_text(_utc_now())
    lock = ExclusiveRunLock(
        repo,
        lock_path,
        {
            "run_id": run_id,
            "host_id_sha256": hashlib.sha256(str(getnode()).encode("ascii")).hexdigest(),
            "pid": os.getpid(),
            "created_at": timestamp,
            "journal_path": f"docs/codex/MIGRATIONS/{path.name}",
        },
    )
    journal.visibility_guard = lock.assert_visible
    changed_operations: list[dict[str, Any]] = []
    try:
        if stale_lock_hash is None:
            lock.acquire()
        else:
            lock.replace_stale(stale_lock_hash)
        lock.assert_visible()
        if action is RecoveryAction.REPAIR and repair_journal_data is not None:
            amended_content = (
                json.dumps(repair_journal_data, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            atomic_write(
                path,
                amended_content,
                root=repo,
                public=False,
                expected_sha256=sha256_bytes(raw),
            )
            data = repair_journal_data
            raw = amended_content
            journal.data = data
            journal.record_recovery_receipt(
                "repair-plan-amendment-complete",
                path.name,
                sha256_bytes(amended_content),
            )
        if stale_lock_hash is not None:
            journal.record_recovery_receipt(
                "stale-lock-reclaim-complete", lock_path.name, stale_lock_hash
            )
        if action is RecoveryAction.REPAIR and repair_operations is not None:
            for operation in repair_operations:
                if operation.action == "git-init" or operation.content is None:
                    continue
                lock.assert_visible()
                current = read_regular_file(
                    repo,
                    repo / operation.relative_path,
                    max_bytes=64 * 1024 * 1024,
                )
                current_hash = sha256_bytes(current) if current is not None else None
                if current_hash == operation.after_sha256:
                    continue
                expected_before = operation.before_sha256
                if (
                    operation.relative_path == report_path
                    and current_hash == data.get("report_sha256")
                ):
                    expected_before = current_hash
                if current_hash != expected_before:
                    raise CoordinatorError(
                        Blocker(
                            "repair_hash_conflict",
                            "A forward-repair target differs from both its original preimage and candidate hash.",
                            "Run reconcile again and create a reviewed manual repair plan.",
                            (operation.relative_path,),
                        )
                    )
                ensure_directory(repo, (repo / operation.relative_path).parent)
                atomic_write(
                    repo / operation.relative_path,
                    operation.content,
                    root=repo,
                    public=True,
                    expected_sha256=expected_before,
                )
                journal.record_file_write(
                    operation.relative_path,
                    operation.before_sha256,
                    operation.after_sha256,
                )
                changed_operations.append(
                    {
                        "action": "repair-forward",
                        "relative_path": operation.relative_path,
                    }
                )
            current_journal = read_regular_file(
                repo, path, max_bytes=4 * 1024 * 1024
            )
            if current_journal is None:
                raise CoordinatorError(
                    Blocker(
                        "journal_changed_during_recovery",
                        "The repair journal disappeared before finalization.",
                        "Run reconcile again from current evidence.",
                    )
                )
            current_data = strict_json_loads(current_journal)
            if not isinstance(current_data, dict):
                raise CoordinatorError(
                    Blocker(
                        "invalid_recovery_journal",
                        "The repair journal became malformed before finalization.",
                        "Preserve it and run reconcile again.",
                    )
                )
            terminal_content, terminal_checks = _resume_terminal_candidate(
                repo, path, current_data, current_journal
            )
            atomic_write(
                path,
                terminal_content,
                root=repo,
                public=False,
                expected_sha256=sha256_bytes(current_journal),
            )
            return OperationResult(
                command="recover",
                ok=True,
                changed=True,
                repository=slug,
                repo_kind=inspection.git.kind,
                run_id=run_id,
                standard_version=STANDARD_VERSION,
                operations=tuple(changed_operations),
                validation=terminal_checks,
                recommended_next_action="Continue normal coordination from the repaired checkpoint.",
                metadata={"action": action.value, "report": report_path},
            )
        if action is RecoveryAction.RESUME:
            current_journal = read_regular_file(
                repo, path, max_bytes=4 * 1024 * 1024
            )
            if current_journal is None:
                raise CoordinatorError(
                    Blocker(
                        "journal_changed_during_recovery",
                        "The recovery journal disappeared before finalization.",
                        "Run reconcile again from current evidence.",
                    )
                )
            terminal_content, terminal_checks = _resume_terminal_candidate(
                repo, path, data, current_journal
            )
            atomic_write(
                path,
                terminal_content,
                root=repo,
                public=False,
                expected_sha256=sha256_bytes(current_journal),
            )
            return OperationResult(
                command="recover",
                ok=True,
                changed=True,
                repository=slug,
                repo_kind=inspection.git.kind,
                run_id=run_id,
                standard_version=inspection.installed_version,
                operations=(
                    {"action": "resume-finalize", "relative_path": path.name},
                ),
                validation=terminal_checks,
                recommended_next_action="Continue normal coordination from the recovered checkpoint.",
                metadata={"action": action.value, "report": data["report_path"]},
            )

        if action is RecoveryAction.SUPERSEDE:
            lock.assert_visible()
            report = _recovery_report(run_id, action)
            report_path = data["report_path"]
            ensure_directory(repo, (repo / report_path).parent)
            atomic_write(
                repo / report_path,
                report,
                root=repo,
                public=True,
                expected_sha256=None,
            )
            current_journal = read_regular_file(
                repo, path, max_bytes=4 * 1024 * 1024
            )
            if current_journal is None:
                raise CoordinatorError(
                    Blocker(
                        "journal_changed_during_recovery",
                        "The recovery journal disappeared before supersede finalization.",
                        "Preserve the report and run reconcile again.",
                    )
                )
            prospective = json.loads(json.dumps(journal.data))
            prospective["status"] = RunStatus.SUPERSEDED.value
            prospective["report_sha256"] = sha256_bytes(report)
            prospective["next_action"] = (
                "The inactive run was superseded; run doctor before new mutation."
            )
            prospective["updated_at"] = _utc_text(_utc_now())
            terminal = (
                json.dumps(prospective, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            atomic_write(
                path,
                terminal,
                root=repo,
                public=False,
                expected_sha256=sha256_bytes(current_journal),
            )
            return OperationResult(
                command="recover",
                ok=True,
                changed=True,
                repository=slug,
                repo_kind=inspection.git.kind,
                run_id=run_id,
                standard_version=inspection.installed_version,
                operations=(
                    {"action": "supersede", "relative_path": path.name},
                ),
                recommended_next_action="Run doctor before starting a new coordinator mutation.",
                metadata={"action": action.value, "report": report_path},
            )

        existing_receipts = {
            item.get("name")
            for item in journal.data.get("validation", [])
            if isinstance(item, dict)
        }
        prior_recovery_report_hash: str | None = None
        for operation in reversed(operations):
            lock.assert_visible()
            relative = operation["relative_path"]
            if operation.get("action") == "git-init" or relative == ".git":
                continue
            after_hash = operation["after_sha256"]
            intent = f"recovery-rollback-intent:{relative}:{after_hash}"
            complete = f"recovery-rollback-complete:{relative}:{after_hash}"
            if complete in existing_receipts:
                continue
            current = read_regular_file(
                repo, repo / relative, max_bytes=64 * 1024 * 1024
            )
            current_hash = sha256_bytes(current) if current is not None else None
            if current_hash == operation.get("before_sha256"):
                continue
            reversal_kind = operation.get("reversal", {}).get("kind")
            delete_new = reversal_kind == "delete-new" and relative == report_path
            if (
                relative == report_path
                and current_hash == data.get("report_sha256")
                and data.get("status") in {RunStatus.FAILED.value, RunStatus.BLOCKED.value}
            ):
                prior_recovery_report_hash = current_hash
                continue
            if current is None and intent in existing_receipts and delete_new:
                journal.record_recovery_receipt(
                    "rollback-complete", relative, after_hash
                )
                changed_operations.append(
                    {"action": "rollback-delete", "relative_path": relative}
                )
                continue
            journal.record_recovery_receipt("rollback-intent", relative, after_hash)
            if delete_new:
                unlink_regular_file(
                    repo,
                    repo / relative,
                    expected_sha256=after_hash,
                )
                changed_action = "rollback-delete"
            else:
                preimage = reconstruct_preimage(repo, data, operation)
                if preimage is None:
                    raise CoordinatorError(
                        Blocker(
                            "rollback_preimage_changed",
                            "A reconstructive rollback preimage is no longer provable.",
                            "Run reconcile again and choose reviewed repair.",
                            (relative,),
                        )
                    )
                atomic_write(
                    repo / relative,
                    preimage,
                    root=repo,
                    public=True,
                    expected_sha256=after_hash,
                )
                changed_action = "rollback-restore"
            journal.record_recovery_receipt("rollback-complete", relative, after_hash)
            changed_operations.append(
                {"action": changed_action, "relative_path": relative}
            )
        report = _recovery_report(run_id, action)
        ensure_directory(repo, (repo / report_path).parent)
        atomic_write(
            repo / report_path,
            report,
            root=repo,
            public=True,
            expected_sha256=prior_recovery_report_hash,
        )
        report_hash = sha256_bytes(report)
        journal.finish(
            RunStatus.SUPERSEDED,
            "The interrupted run was rolled back; run doctor before new mutation.",
            report_path,
            report_hash,
        )
        return OperationResult(
            command="recover",
            ok=True,
            changed=True,
            repository=slug,
            repo_kind=inspection.git.kind,
            run_id=run_id,
            standard_version=inspection.installed_version,
            operations=tuple(changed_operations),
            recommended_next_action="Run doctor before starting another coordinator mutation.",
            metadata={"action": action.value, "report": report_path},
        )
    except CoordinatorError as error:
        return _blocked(
            "recover",
            inspection,
            error.blocker,
            slug=slug,
            run_id=run_id,
        )
    finally:
        lock.release()


__all__ = [
    "apply_operations",
    "check_current",
    "doctor",
    "initialize",
    "make_decision_token",
    "reconcile",
    "recover_run",
    "upgrade",
]
