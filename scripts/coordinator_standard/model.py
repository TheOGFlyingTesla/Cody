"""Shared immutable models for Coordinator Standard operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from . import SCHEMA_VERSION, STANDARD_NAME, STANDARD_VERSION


class ExitCode(IntEnum):
    OK = 0
    BLOCKED = 2
    INVALID = 3
    INTERNAL_ERROR = 4


class RepoKind(str, Enum):
    EMPTY_NON_GIT = "empty-non-git"
    NONEMPTY_NON_GIT = "nonempty-non-git"
    UNBORN_GIT = "unborn-git"
    ESTABLISHED_GIT = "established-git"
    LINKED_WORKTREE = "linked-worktree"
    BARE_GIT = "bare-git"
    UNSAFE_GIT = "unsafe-git"


class RunStatus(str, Enum):
    FRESH = "fresh"
    IN_PROGRESS = "in-progress"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETE = "complete"
    SUPERSEDED = "superseded"


class Phase(str, Enum):
    INSPECT = "inspect"
    PLAN = "plan"
    APPLY = "apply"
    VALIDATE = "validate"
    FINALIZE = "finalize"


class RecoveryAction(str, Enum):
    RESUME = "resume"
    ROLLBACK = "rollback"
    REPAIR = "repair"
    SUPERSEDE = "supersede"
    MANUAL_DECISION = "manual-decision"


class EvidenceStatus(str, Enum):
    VERIFIED = "verified"
    INFERRED = "inferred"
    UNKNOWN = "unknown"
    STALE = "stale"
    CONFLICTING = "conflicting"


@dataclass(frozen=True)
class Blocker:
    code: str
    message: str
    recovery: str
    paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuthorityGrant:
    command: str
    mutation_classes: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    decisions: tuple[tuple[str, str], ...]
    created_at: str
    source_id: str


@dataclass(frozen=True)
class ReversalEvidence:
    kind: str
    reference: str | None
    metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Operation:
    action: str
    relative_path: str
    before_sha256: str | None
    after_sha256: str | None
    content: bytes | None = field(default=None, repr=False)
    reversal: ReversalEvidence = field(
        default_factory=lambda: ReversalEvidence("unavailable", None)
    )


@dataclass(frozen=True)
class GitSnapshot:
    kind: RepoKind
    worktree: Path
    git_dir: Path | None
    common_dir: Path | None
    main_worktree: Path | None
    head: str | None
    explicit_base: str | None
    branch: str | None
    is_detached: bool
    superproject: Path | None
    staged: tuple[str, ...]
    unstaged: tuple[str, ...]
    untracked: tuple[str, ...]
    remote_identities: tuple[str, ...]


@dataclass(frozen=True)
class JournalGitEvidence:
    kind: str
    head: str | None
    explicit_base: str | None
    branch: str | None
    is_detached: bool
    worktree_identity_sha256: str | None
    common_dir_identity_sha256: str | None
    staged_managed_paths: tuple[str, ...]
    unstaged_managed_paths: tuple[str, ...]
    untracked_managed_paths: tuple[str, ...]


@dataclass(frozen=True)
class ValidationCheck:
    name: str
    ok: bool
    severity: str
    message: str


@dataclass(frozen=True)
class Inspection:
    repo: Path
    git: GitSnapshot
    applicable_instructions: tuple[str, ...]
    installed_version: str | None
    discovered_commands: Mapping[str, tuple[str, ...]]
    blockers: tuple[Blocker, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "discovered_commands",
            MappingProxyType(
                {key: tuple(value) for key, value in self.discovered_commands.items()}
            ),
        )


@dataclass(frozen=True)
class Reconciliation:
    run_id: str | None
    status: RunStatus
    evidence: tuple[Mapping[str, Any], ...]
    safe_actions: tuple[RecoveryAction, ...]
    recommended_action: RecoveryAction | None
    blockers: tuple[Blocker, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evidence",
            tuple(MappingProxyType(dict(item)) for item in self.evidence),
        )


@dataclass(frozen=True)
class LockState:
    state: str
    run_id: str | None
    journal_path: str | None
    blocker: Blocker | None = None


@dataclass(frozen=True)
class OperationResult:
    command: str
    ok: bool
    changed: bool
    repository: str
    repo_kind: RepoKind
    run_id: str | None
    standard_version: str | None
    operations: tuple[Mapping[str, Any], ...] = ()
    blockers: tuple[Blocker, ...] = ()
    warnings: tuple[str, ...] = ()
    validation: tuple[Mapping[str, Any], ...] = ()
    recommended_next_action: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operations",
            tuple(MappingProxyType(dict(item)) for item in self.operations),
        )
        object.__setattr__(
            self,
            "validation",
            tuple(MappingProxyType(dict(item)) for item in self.validation),
        )
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


class CoordinatorError(RuntimeError):
    def __init__(self, blocker: Blocker):
        super().__init__(blocker.message)
        self.blocker = blocker


__all__ = [
    "SCHEMA_VERSION",
    "STANDARD_NAME",
    "STANDARD_VERSION",
    "AuthorityGrant",
    "Blocker",
    "CoordinatorError",
    "EvidenceStatus",
    "ExitCode",
    "GitSnapshot",
    "Inspection",
    "JournalGitEvidence",
    "LockState",
    "Operation",
    "OperationResult",
    "Phase",
    "Reconciliation",
    "RecoveryAction",
    "RepoKind",
    "ReversalEvidence",
    "RunStatus",
    "ValidationCheck",
]
