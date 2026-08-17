"""Credential-safe, side-effect-minimized Git repository inspection."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
from urllib.parse import unquote, urlsplit

from .model import Blocker, CoordinatorError, GitSnapshot, RepoKind
from .safety import contains_credential, redact_text, sha256_bytes


_REPOSITORY_ENVIRONMENT = {
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_WORK_TREE",
}


def _reject_environment_overrides() -> None:
    unsafe = sorted(
        name
        for name in os.environ
        if name in _REPOSITORY_ENVIRONMENT or name.startswith("GIT_CONFIG_")
    )
    if unsafe:
        raise CoordinatorError(
            Blocker(
                "git_environment_override",
                "Repository-selecting Git environment variables are active.",
                "Unset the Git environment overrides and retry repository inspection.",
                tuple(unsafe),
            )
        )


def sterile_git_environment() -> dict[str, str]:
    _reject_environment_overrides()
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_PAGER": "cat",
            "PAGER": "cat",
            "LC_ALL": "C",
            "LANG": "C",
        }
    )
    return environment


def _run_git(
    repo: Path,
    arguments: list[str],
    *,
    allowed_codes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[bytes]:
    command = [
        "git",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        "-c",
        "core.hooksPath=/dev/null",
        *arguments,
    ]
    result = subprocess.run(
        command,
        cwd=repo,
        env=sterile_git_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode not in allowed_codes:
        message = redact_text(result.stderr.decode("utf-8", errors="replace")).strip()
        raise CoordinatorError(
            Blocker(
                "git_inspection_failed",
                f"Git inspection failed: {message or 'no diagnostic'}",
                "Repair Git metadata or select a valid repository and retry.",
            )
        )
    return result


def _output(result: subprocess.CompletedProcess[bytes]) -> str:
    return result.stdout.decode("utf-8", errors="surrogateescape").strip()


def _path_from_output(repo: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo / path
    return path.resolve(strict=True)


def _parse_status(data: bytes) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    records = data.split(b"\0")
    staged: set[str] = set()
    unstaged: set[str] = set()
    untracked: set[str] = set()
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if len(record) < 4:
            continue
        x = chr(record[0])
        y = chr(record[1])
        path = record[3:].decode("utf-8", errors="surrogateescape")
        if x == "?" and y == "?":
            untracked.add(path)
            continue
        if x not in {" ", "?"}:
            staged.add(path)
        if y not in {" ", "?"}:
            unstaged.add(path)
        if x in {"R", "C"} or y in {"R", "C"}:
            if index < len(records) and records[index]:
                original_path = records[index].decode(
                    "utf-8", errors="surrogateescape"
                )
                if x not in {" ", "?"}:
                    staged.add(original_path)
                if y not in {" ", "?"}:
                    unstaged.add(original_path)
                index += 1
    return tuple(sorted(staged)), tuple(sorted(unstaged)), tuple(sorted(untracked))


def _parse_worktrees(data: bytes) -> list[dict[str, str | bool]]:
    records: list[dict[str, str | bool]] = []
    current: dict[str, str | bool] = {}
    for token_bytes in data.split(b"\0"):
        token = token_bytes.decode("utf-8", errors="surrogateescape")
        if not token:
            if current:
                records.append(current)
                current = {}
            continue
        if " " in token:
            key, value = token.split(" ", 1)
            current[key] = value
        else:
            current[token] = True
    if current:
        records.append(current)
    return records


def _remote_identity(value: str) -> str:
    value = value.strip()
    if "://" in value:
        parsed = urlsplit(value)
        if parsed.scheme.lower() == "file" or not parsed.hostname:
            digest = hashlib.sha256(value.encode("utf-8", errors="surrogateescape")).hexdigest()
            return f"local/{digest[:16]}"
        host = parsed.hostname.lower().rstrip(".")
        if re.fullmatch(r"[a-z0-9.-]+", host) is None:
            digest = hashlib.sha256(value.encode("utf-8", errors="surrogateescape")).hexdigest()
            return f"remote/{digest[:16]}"
        path = unquote(parsed.path).lstrip("/")
        if contains_credential(path) or any(ord(character) < 32 for character in path):
            digest = hashlib.sha256(value.encode("utf-8", errors="surrogateescape")).hexdigest()
            path = f"redacted-{digest[:16]}"
        return f"{host}/{path}" if path else host
    scp = re.match(r"^(?:[^@/:]+@)?([^:/]+):(.+)$", value)
    if scp:
        host = scp.group(1).lower()
        path = scp.group(2).lstrip("/")
        if (
            re.fullmatch(r"[a-z0-9.-]+", host) is None
            or contains_credential(path)
            or any(ord(character) < 32 for character in path)
        ):
            digest = hashlib.sha256(value.encode("utf-8", errors="surrogateescape")).hexdigest()
            return f"remote/{digest[:16]}"
        return f"{host}/{path}"
    digest = hashlib.sha256(value.encode("utf-8", errors="surrogateescape")).hexdigest()
    return f"local/{digest[:16]}"


def _read_remote_identities(repo: Path) -> tuple[str, ...]:
    result = _run_git(
        repo,
        [
            "config",
            "--local",
            "--no-includes",
            "--null",
            "--get-regexp",
            r"^remote\..*\.url$",
        ],
        allowed_codes=(0, 1),
    )
    identities: set[str] = set()
    for entry in result.stdout.split(b"\0"):
        if not entry:
            continue
        if b"\n" in entry:
            _key, raw = entry.split(b"\n", 1)
        else:
            parts = entry.split(None, 1)
            if len(parts) != 2:
                continue
            _key, raw = parts
        value = raw.decode("utf-8", errors="surrogateescape")
        identities.add(_remote_identity(value))
    return tuple(sorted(identities))


def _non_git_snapshot(repo: Path) -> GitSnapshot:
    entries = list(repo.iterdir())
    kind = RepoKind.EMPTY_NON_GIT if not entries else RepoKind.NONEMPTY_NON_GIT
    return GitSnapshot(
        kind=kind,
        worktree=repo.resolve(strict=True),
        git_dir=None,
        common_dir=None,
        main_worktree=None,
        head=None,
        explicit_base=None,
        branch=None,
        is_detached=False,
        superproject=None,
        staged=(),
        unstaged=(),
        untracked=(),
        remote_identities=(),
    )


def inspect_git(repo: Path) -> GitSnapshot:
    """Classify one directory without printing or retaining credential-bearing URLs."""

    _reject_environment_overrides()
    if not repo.is_dir():
        raise CoordinatorError(
            Blocker(
                "repository_missing",
                "The repository path is not a directory.",
                "Restore or select the repository directory and retry.",
            )
        )
    repo = repo.resolve(strict=True)
    git_entry = repo / ".git"
    try:
        git_entry_info = git_entry.lstat()
    except FileNotFoundError:
        git_entry_info = None
    if git_entry_info is not None and stat.S_ISLNK(git_entry_info.st_mode):
        raise CoordinatorError(
            Blocker(
                "unsafe_git_metadata",
                "The .git entry is a symbolic link.",
                "Use a normal checkout or a Git-managed worktree with a regular .git file.",
                (".git",),
            )
        )
    has_git_entry = git_entry_info is not None
    probe = _run_git(
        repo,
        ["rev-parse", "--is-bare-repository"],
        allowed_codes=(0, 128),
    )
    if probe.returncode != 0:
        return _non_git_snapshot(repo)
    is_bare = _output(probe) == "true"
    if not is_bare and not has_git_entry:
        top_probe = _run_git(
            repo,
            ["rev-parse", "--show-toplevel"],
            allowed_codes=(0, 128),
        )
        if top_probe.returncode == 0 and _path_from_output(repo, _output(top_probe)) != repo:
            raise CoordinatorError(
                Blocker(
                    "nested_repository_boundary",
                    "The selected directory is nested inside another Git checkout.",
                    "Open the intended repository root or explicitly choose a separate non-nested folder.",
                )
            )
        if top_probe.returncode != 0:
            return _non_git_snapshot(repo)
    if is_bare:
        return GitSnapshot(
            kind=RepoKind.BARE_GIT,
            worktree=repo,
            git_dir=repo,
            common_dir=repo,
            main_worktree=None,
            head=None,
            explicit_base=None,
            branch=None,
            is_detached=False,
            superproject=None,
            staged=(),
            unstaged=(),
            untracked=(),
            remote_identities=_read_remote_identities(repo),
        )

    worktree = _path_from_output(
        repo, _output(_run_git(repo, ["rev-parse", "--show-toplevel"]))
    )
    git_dir = _path_from_output(
        repo, _output(_run_git(repo, ["rev-parse", "--absolute-git-dir"]))
    )
    common_dir = _path_from_output(
        repo, _output(_run_git(repo, ["rev-parse", "--git-common-dir"]))
    )
    head_result = _run_git(
        repo, ["rev-parse", "--verify", "HEAD"], allowed_codes=(0, 128)
    )
    head = _output(head_result) if head_result.returncode == 0 else None
    branch_result = _run_git(
        repo,
        ["symbolic-ref", "--quiet", "--short", "HEAD"],
        allowed_codes=(0, 1),
    )
    branch = _output(branch_result) if branch_result.returncode == 0 else None
    superproject_result = _run_git(
        repo,
        ["rev-parse", "--show-superproject-working-tree"],
        allowed_codes=(0,),
    )
    superproject_text = _output(superproject_result)
    superproject = (
        _path_from_output(repo, superproject_text) if superproject_text else None
    )
    if superproject is not None:
        raise CoordinatorError(
            Blocker(
                "git_superproject_state",
                "The repository is a submodule of another checkout.",
                "Run coordinator setup from the intended superproject boundary.",
            )
        )
    status = _run_git(
        repo, ["status", "--porcelain=v1", "-z", "--untracked-files=all"]
    )
    staged, unstaged, untracked = _parse_status(status.stdout)
    worktrees = _parse_worktrees(
        _run_git(repo, ["worktree", "list", "--porcelain", "-z"]).stdout
    )
    if any(record.get("prunable") or record.get("locked") for record in worktrees):
        raise CoordinatorError(
            Blocker(
                "git_worktree_state",
                "Git reports a locked or prunable worktree record.",
                "Repair or confirm the worktree registry before coordinator mutation.",
            )
        )
    main_worktree = None
    if worktrees and isinstance(worktrees[0].get("worktree"), str):
        main_worktree = Path(str(worktrees[0]["worktree"])).resolve(strict=True)
    registered = [
        Path(str(record["worktree"])).resolve(strict=False)
        for record in worktrees
        if isinstance(record.get("worktree"), str)
    ]
    if worktree not in registered:
        raise CoordinatorError(
            Blocker(
                "unsafe_git_metadata",
                "The selected checkout is not registered as a Git worktree.",
                "Use a normal checkout or create the worktree through Git/Codex.",
                (".git",),
            )
        )
    kind = (
        RepoKind.LINKED_WORKTREE
        if git_dir != common_dir
        else (RepoKind.UNBORN_GIT if head is None else RepoKind.ESTABLISHED_GIT)
    )
    return GitSnapshot(
        kind=kind,
        worktree=worktree,
        git_dir=git_dir,
        common_dir=common_dir,
        main_worktree=main_worktree,
        head=head,
        explicit_base=head,
        branch=branch,
        is_detached=head is not None and branch is None,
        superproject=None,
        staged=staged,
        unstaged=unstaged,
        untracked=untracked,
        remote_identities=_read_remote_identities(repo),
    )


def recovery_git_picture(repo: Path) -> dict[str, object]:
    """Return a path-safe Git operating picture for reconciliation."""

    snapshot = inspect_git(repo)
    base: dict[str, object] = {
        "kind": snapshot.kind.value,
        "head": snapshot.head,
        "branch": redact_text(snapshot.branch) if snapshot.branch else None,
        "detached": snapshot.is_detached,
        "staged": [redact_text(item) for item in snapshot.staged],
        "unstaged": [redact_text(item) for item in snapshot.unstaged],
        "untracked": [redact_text(item) for item in snapshot.untracked],
        "branches": [],
        "worktrees": [],
        "recent_commits": [],
    }
    if snapshot.kind in {RepoKind.EMPTY_NON_GIT, RepoKind.NONEMPTY_NON_GIT}:
        return base
    branches = _run_git(
        repo,
        ["for-each-ref", "--format=%(refname:short)%00%(objectname)", "refs/heads"],
    )
    branch_rows: list[dict[str, str]] = []
    for line in branches.stdout.splitlines():
        if b"\0" not in line:
            continue
        name, commit = line.split(b"\0", 1)
        branch_rows.append(
            {
                "name": redact_text(name.decode("utf-8", errors="surrogateescape")),
                "head": commit.decode("ascii", errors="replace"),
            }
        )
    base["branches"] = branch_rows
    commits = _run_git(
        repo,
        ["log", "-5", "--format=%H"],
        allowed_codes=(0, 128),
    )
    if commits.returncode == 0:
        base["recent_commits"] = [
            line.decode("ascii", errors="replace")
            for line in commits.stdout.splitlines()
            if line
        ]
    worktrees = _parse_worktrees(
        _run_git(repo, ["worktree", "list", "--porcelain", "-z"]).stdout
    )
    rows: list[dict[str, object]] = []
    for record in worktrees:
        raw_path = record.get("worktree")
        path_identity = None
        if isinstance(raw_path, str):
            path_identity = hashlib.sha256(
                raw_path.encode("utf-8", errors="surrogateescape")
            ).hexdigest()
        row: dict[str, object] = {
            "path_identity_sha256": path_identity,
            "head": record.get("HEAD") if isinstance(record.get("HEAD"), str) else None,
            "branch": (
                redact_text(str(record["branch"]))
                if isinstance(record.get("branch"), str)
                else None
            ),
            "detached": bool(record.get("detached")),
            "bare": bool(record.get("bare")),
            "locked": bool(record.get("locked")),
            "prunable": bool(record.get("prunable")),
        }
        rows.append(row)
    base["worktrees"] = rows
    return base


def read_tracked_preimage(
    repo: Path, head: str, relative: str, expected_sha256: str
) -> bytes | None:
    """Read one bounded base-tree blob only when its exact expected hash matches."""

    path = PurePosixPath(relative)
    if (
        re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", head) is None
        or path.as_posix() != relative
        or relative.startswith("/")
        or ".." in path.parts
        or ":" in relative
        or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
    ):
        return None
    object_name = f"{head}:{relative}"
    size_result = _run_git(
        repo, ["cat-file", "-s", object_name], allowed_codes=(0, 128)
    )
    if size_result.returncode != 0:
        return None
    try:
        size = int(_output(size_result))
    except ValueError:
        return None
    if size < 0 or size > 64 * 1024 * 1024:
        return None
    content_result = _run_git(
        repo, ["cat-file", "blob", object_name], allowed_codes=(0, 128)
    )
    if content_result.returncode != 0 or len(content_result.stdout) != size:
        return None
    return (
        content_result.stdout
        if sha256_bytes(content_result.stdout) == expected_sha256
        else None
    )


__all__ = [
    "CoordinatorError",
    "inspect_git",
    "read_tracked_preimage",
    "recovery_git_picture",
    "sterile_git_environment",
]
