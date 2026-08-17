"""Stable command-line interface for Cody Coordinator."""

from __future__ import annotations

import argparse
from dataclasses import fields, is_dataclass
from enum import Enum
import json
from pathlib import Path
import traceback
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from . import STANDARD_VERSION
from .inspector import inspect_repository
from .model import (
    Blocker,
    CoordinatorError,
    ExitCode,
    OperationResult,
    RecoveryAction,
)
from .operations import (
    check_current,
    doctor,
    initialize,
    reconcile,
    recover_run,
    upgrade,
)
from .safety import redact_text, require_secure_mutation_support
from .templates import derive_project_slug


def _jsonable(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return value.name
    if isinstance(value, (Mapping, MappingProxyType)):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if is_dataclass(value):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in fields(value)
        }
    return value


def _result_payload(result: OperationResult) -> dict[str, Any]:
    return _jsonable(result)


def _inspection_result(repo: Path) -> OperationResult:
    inspection = inspect_repository(repo)
    repository = "."
    if inspection.installed_version is not None:
        try:
            repository = derive_project_slug(repo.name)
        except CoordinatorError:
            repository = "."
    return OperationResult(
        command="inspect",
        ok=not inspection.blockers,
        changed=False,
        repository=repository,
        repo_kind=inspection.git.kind,
        run_id=None,
        standard_version=inspection.installed_version,
        blockers=inspection.blockers,
        warnings=inspection.warnings,
        recommended_next_action=(
            "Run check-current before any coordinator mutation."
            if not inspection.blockers
            else inspection.blockers[0].recovery
        ),
        metadata={
            "applicable_instructions": list(inspection.applicable_instructions),
            "discovered_commands": {
                key: list(value) for key, value in inspection.discovered_commands.items()
            },
            "git": {
                "kind": inspection.git.kind.value,
                "head": inspection.git.head,
                "explicit_base": inspection.git.explicit_base,
                "branch": inspection.git.branch,
                "is_detached": inspection.git.is_detached,
                "staged": list(inspection.git.staged),
                "unstaged": list(inspection.git.unstaged),
                "untracked": list(inspection.git.untracked),
                "remote_identities": list(inspection.git.remote_identities),
            },
        },
    )


def _exit_code(result: OperationResult) -> ExitCode:
    if result.ok:
        return ExitCode.OK
    invalid_markers = (
        "validation",
        "malformed",
        "schema",
        "marker",
        "candidate",
        "credential",
        "unsafe",
        "invalid",
    )
    if any(marker in blocker.code for blocker in result.blockers for marker in invalid_markers):
        return ExitCode.INVALID
    return ExitCode.BLOCKED


def _render_human(result: OperationResult) -> str:
    if result.ok:
        outcome = "OK — changes applied." if result.changed else "OK — no changes."
    else:
        outcome = "BLOCKED — no completion claimed."
    lines = [outcome, f"Command: {result.command}"]
    if result.standard_version:
        lines.append(f"Standard: {result.standard_version}")
    for blocker in result.blockers:
        lines.append(f"Blocker [{blocker.code}]: {blocker.message}")
        if blocker.paths:
            lines.append("Paths: " + ", ".join(blocker.paths))
    for warning in result.warnings:
        lines.append(f"Warning: {warning}")
    if result.recommended_next_action:
        lines.append(f"Next action: {result.recommended_next_action}")
    return redact_text("\n".join(lines))


def _emit(result: OperationResult, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(_result_payload(result), sort_keys=True, ensure_ascii=False))
    else:
        print(_render_human(result))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coordinator_standard.py",
        description="Inspect, initialize, upgrade, validate, and recover Coordinator Standard repositories.",
    )
    parser.add_argument("--repo", required=True, type=Path, help="Explicit repository root")
    parser.add_argument("--format", choices=("human", "json"), default="human")
    parser.add_argument("--debug", action="store_true", help="Emit a redacted traceback on internal errors")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inspect", help="Read-only repository inspection")
    init = commands.add_parser("init", help="Set up the current coordinator standard")
    init.add_argument("--check", action="store_true")
    init.add_argument("--project-slug")
    init.add_argument("--approve-repository-boundary")
    upgrade_command = commands.add_parser("upgrade", help="Upgrade an existing repository")
    upgrade_command.add_argument("--check", action="store_true")
    commands.add_parser("doctor", help="Validate the complete repository contract")
    commands.add_parser("reconcile", help="Read-only interrupted-run recovery picture")
    recover = commands.add_parser("recover", help="Perform one explicitly selected recovery action")
    recover.add_argument("--run-id", required=True)
    recover.add_argument(
        "--action",
        required=True,
        choices=("resume", "rollback", "repair", "supersede"),
    )
    recover.add_argument("--decision-token")
    commands.add_parser("check-current", help="Report current-version and structural status")
    return parser


def _dispatch(arguments: argparse.Namespace) -> OperationResult:
    repo = arguments.repo
    if arguments.command == "inspect":
        return _inspection_result(repo)
    if arguments.command == "init":
        if not arguments.check:
            require_secure_mutation_support()
        return initialize(
            repo,
            check=arguments.check,
            project_slug=arguments.project_slug,
            repository_boundary_token=arguments.approve_repository_boundary,
        )
    if arguments.command == "upgrade":
        if not arguments.check:
            require_secure_mutation_support()
        return upgrade(repo, check=arguments.check)
    if arguments.command == "doctor":
        return doctor(repo)
    if arguments.command == "reconcile":
        return reconcile(repo)
    if arguments.command == "recover":
        require_secure_mutation_support()
        return recover_run(
            repo,
            run_id=arguments.run_id,
            action=RecoveryAction(arguments.action),
            decision_token=arguments.decision_token,
        )
    return check_current(repo)


def _internal_result(command: str, message: str) -> OperationResult:
    from .model import RepoKind

    return OperationResult(
        command=command,
        ok=False,
        changed=False,
        repository=".",
        repo_kind=RepoKind.UNSAFE_GIT,
        run_id=None,
        standard_version=STANDARD_VERSION,
        blockers=(
            Blocker(
                "internal_error",
                f"Coordinator command failed internally: {redact_text(message)}",
                "Preserve the repository and rerun with --debug for a redacted diagnostic.",
            ),
        ),
        recommended_next_action="Preserve the repository and inspect the redacted diagnostic.",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        result = _dispatch(arguments)
    except CoordinatorError as error:
        from .model import RepoKind

        blocker = Blocker(
            redact_text(error.blocker.code),
            redact_text(error.blocker.message),
            redact_text(error.blocker.recovery),
            tuple(redact_text(path) for path in error.blocker.paths),
        )
        result = OperationResult(
            command=arguments.command,
            ok=False,
            changed=False,
            repository=".",
            repo_kind=RepoKind.UNSAFE_GIT,
            run_id=None,
            standard_version=None,
            blockers=(blocker,),
            recommended_next_action=blocker.recovery,
        )
    except Exception as error:  # outer trust boundary
        result = _internal_result(arguments.command, str(error))
        if arguments.debug:
            print(redact_text(traceback.format_exc()))
    _emit(result, arguments.format)
    if any(blocker.code == "internal_error" for blocker in result.blockers):
        return int(ExitCode.INTERNAL_ERROR)
    return int(_exit_code(result))


__all__ = ["main"]
