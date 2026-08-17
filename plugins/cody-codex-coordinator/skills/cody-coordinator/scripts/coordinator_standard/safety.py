"""Fail-closed filesystem, redaction, hashing, and locking primitives."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import hashlib
import json
import errno
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any
from uuid import UUID

from .model import Blocker, CoordinatorError


_URL_USERINFO = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^/@\s]+@")
_SCP_USER = re.compile(r"(?<![/:\w])[^@\s/:]+@([A-Za-z0-9.-]+):")
_AUTH_HEADER = re.compile(r"(?i)(authorization\s*:\s*(?:bearer|basic)\s+)[^\s]+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?<![A-Za-z0-9_-])((?:[A-Za-z0-9]+[_-])*"
    r"(?:api[_-]?key|access[_-]?(?:key|token)|client[_-]?secret|"
    r"refresh[_-]?token|private[_-]?key|token|secret|password)"
    r"(?:[_-][A-Za-z0-9]+)*)(\s*[:=]\s*)"
    r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;]+)"
)
_SECRET_QUERY = re.compile(
    r"(?i)([?&](?:access_token|auth|client_secret|key|oauth_token|password|"
    r"refresh_token|secret|token)=)[^&#\s]+"
)
_KNOWN_TOKEN = re.compile(
    r"(?i)\b(?:gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{12,}|"
    r"sk-[A-Za-z0-9_-]{16,}|sk_(?:live|test)_[A-Za-z0-9_-]{12,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16})\b"
)
_PRIVATE_KEY_BLOCK = re.compile(
    r"(?s)-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----.*?"
    r"-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"
)
_UNSPECIFIED = object()


def secure_mutation_supported() -> bool:
    """Return whether the native descriptor primitives used for writes exist."""

    if os.name == "nt":
        return False
    required = (os.open, os.mkdir, os.stat, os.unlink, os.rename)
    return all(function in os.supports_dir_fd for function in required)


def require_secure_mutation_support() -> None:
    """Fail explicitly before any mutation on an unproved native platform."""

    if secure_mutation_supported():
        return
    raise CoordinatorError(
        Blocker(
            "unsupported_platform",
            "Secure coordinator mutation is unsupported on this platform.",
            "Use inspect and other read-only commands, or run mutation from a supported macOS or Linux environment.",
        )
    )


def redact_text(value: str) -> str:
    """Return text with credential-bearing shapes replaced."""

    redacted = _PRIVATE_KEY_BLOCK.sub("[PRIVATE KEY REDACTED]", value)
    redacted = _URL_USERINFO.sub(r"\1[REDACTED]@", redacted)
    redacted = _SCP_USER.sub(r"[REDACTED]@\1:", redacted)
    redacted = _AUTH_HEADER.sub(r"\1[REDACTED]", redacted)
    redacted = _SECRET_ASSIGNMENT.sub(r"\1\2[REDACTED]", redacted)
    redacted = _SECRET_QUERY.sub(r"\1[REDACTED]", redacted)
    return _KNOWN_TOKEN.sub("[REDACTED]", redacted)


def contains_credential(value: str) -> bool:
    """Return whether redaction would alter the supplied text."""

    return redact_text(value) != value


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_display_path(repo: Path, path: Path) -> str:
    """Render a repository-relative path without exposing its absolute root."""

    root = repo.resolve(strict=True)
    candidate = path.resolve(strict=False)
    try:
        relative = candidate.relative_to(root)
    except ValueError as error:
        raise CoordinatorError(
            Blocker(
                "path_escape",
                "A path resolves outside the repository.",
                "Move the target inside the repository and retry inspection.",
            )
        ) from error
    rendered = relative.as_posix()
    return rendered if rendered else "."


def _lexical_relative(root: Path, target: Path) -> Path:
    root_absolute = Path(os.path.abspath(root))
    target_absolute = Path(os.path.abspath(target))
    try:
        return target_absolute.relative_to(root_absolute)
    except ValueError as error:
        raise CoordinatorError(
            Blocker(
                "path_escape",
                "A managed path is outside the repository boundary.",
                "Choose a path beneath the verified repository root.",
            )
        ) from error


def assert_contained(root: Path, target: Path, *, reject_symlinks: bool = True) -> Path:
    """Validate lexical containment and reject symlinks in managed components."""

    if not root.is_dir():
        raise CoordinatorError(
            Blocker(
                "repository_missing",
                "The repository root is not a directory.",
                "Restore or select the repository directory and retry.",
            )
        )
    relative = _lexical_relative(root, target)
    current = Path(os.path.abspath(root))
    for component in relative.parts:
        current = current / component
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if reject_symlinks and stat.S_ISLNK(info.st_mode):
            raise CoordinatorError(
                Blocker(
                    "path_symlink",
                    "A managed path contains a symbolic link.",
                    "Replace the symlink with a real in-repository directory or file.",
                    (relative.as_posix(),),
                )
            )
    resolved_root = root.resolve(strict=True)
    existing = Path(os.path.abspath(root))
    remaining: list[str] = []
    for index, component in enumerate(relative.parts):
        candidate = existing / component
        if candidate.exists() or candidate.is_symlink():
            existing = candidate
            continue
        remaining = list(relative.parts[index:])
        break
    resolved_existing = existing.resolve(strict=True)
    try:
        resolved_existing.relative_to(resolved_root)
    except ValueError as error:
        raise CoordinatorError(
            Blocker(
                "path_escape",
                "A managed path resolves outside the repository.",
                "Remove the redirecting path component and retry.",
                (relative.as_posix(),),
            )
        ) from error
    return resolved_existing.joinpath(*remaining)


def _directory_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _open_root(root: Path) -> tuple[int, os.stat_result]:
    try:
        root_info = root.lstat()
    except FileNotFoundError as error:
        raise CoordinatorError(
            Blocker(
                "repository_missing",
                "The repository root does not exist.",
                "Restore the repository directory and retry.",
            )
        ) from error
    if stat.S_ISLNK(root_info.st_mode):
        raise CoordinatorError(
            Blocker(
                "path_symlink",
                "The repository root is a symbolic link.",
                "Open the real repository path before coordinator mutation.",
            )
        )
    if not stat.S_ISDIR(root_info.st_mode):
        raise CoordinatorError(
            Blocker(
                "repository_missing",
                "The repository root is not a directory.",
                "Restore the repository directory and retry.",
            )
        )
    descriptor = os.open(root, _directory_flags())
    opened_info = os.fstat(descriptor)
    if (
        root_info.st_dev != opened_info.st_dev
        or root_info.st_ino != opened_info.st_ino
    ):
        os.close(descriptor)
        raise CoordinatorError(
            Blocker(
                "path_race",
                "The repository root changed during path verification.",
                "Restore the repository path and retry after confirming no concurrent writer.",
            )
        )
    return descriptor, opened_info


def _open_verified_parent(root: Path, target: Path) -> tuple[int, str, os.stat_result, os.stat_result]:
    relative = _lexical_relative(root, target)
    if not relative.parts or relative.name in {"", ".", ".."}:
        raise CoordinatorError(
            Blocker(
                "unsafe_target_name",
                "The managed target has no safe file name.",
                "Choose a regular file beneath the repository root.",
            )
        )
    root_fd, root_info = _open_root(root)
    current_fd = root_fd
    try:
        for component in relative.parts[:-1]:
            if component in {"", ".", ".."}:
                raise CoordinatorError(
                    Blocker(
                        "path_escape",
                        "A managed path contains an unsafe component.",
                        "Use a normalized repository-relative path.",
                        (relative.as_posix(),),
                    )
                )
            try:
                next_fd = os.open(component, _directory_flags(), dir_fd=current_fd)
            except OSError as error:
                code = "path_symlink" if error.errno in {errno.ELOOP, errno.ENOTDIR} else "parent_missing"
                message = (
                    "A managed path contains a symbolic link."
                    if code == "path_symlink"
                    else "A managed parent directory does not exist."
                )
                recovery = (
                    "Replace the symlink with a real in-repository directory."
                    if code == "path_symlink"
                    else "Create the coordinator directory safely before writing files."
                )
                raise CoordinatorError(
                    Blocker(code, message, recovery, (relative.as_posix(),))
                ) from error
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
        if current_fd == root_fd:
            parent_fd = os.dup(root_fd)
        else:
            parent_fd = current_fd
            current_fd = root_fd
        return parent_fd, relative.name, root_info, os.fstat(parent_fd)
    finally:
        if current_fd != root_fd:
            os.close(current_fd)
        os.close(root_fd)


def ensure_directory(root: Path, target: Path, *, mode: int = 0o755) -> None:
    """Create a repository-contained directory without following symlinks."""

    relative = _lexical_relative(root, target)
    root_fd, _root_info = _open_root(root)
    current_fd = root_fd
    try:
        for component in relative.parts:
            if component in {"", ".", ".."}:
                raise CoordinatorError(
                    Blocker(
                        "path_escape",
                        "A managed directory contains an unsafe component.",
                        "Use a normalized repository-relative directory.",
                    )
                )
            try:
                os.mkdir(component, mode=mode, dir_fd=current_fd)
                os.fsync(current_fd)
            except FileExistsError:
                pass
            try:
                next_fd = os.open(component, _directory_flags(), dir_fd=current_fd)
            except OSError as error:
                raise CoordinatorError(
                    Blocker(
                        "path_symlink",
                        "A managed directory path is not a real directory.",
                        "Replace symlinks or non-directory entries before retrying.",
                        (relative.as_posix(),),
                    )
                ) from error
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
    finally:
        if current_fd != root_fd:
            os.close(current_fd)
        os.close(root_fd)


def read_regular_file(
    root: Path, target: Path, *, max_bytes: int | None = None
) -> bytes | None:
    """Read a contained regular file through verified directory descriptors."""

    try:
        directory_fd, target_name, _root_info, _parent_info = _open_verified_parent(
            root, target
        )
    except CoordinatorError as error:
        if error.blocker.code == "parent_missing":
            return None
        raise
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        try:
            descriptor = os.open(target_name, flags, dir_fd=directory_fd)
        except FileNotFoundError:
            return None
        except OSError as error:
            code = "path_symlink" if error.errno == errno.ELOOP else "unsafe_target_type"
            raise CoordinatorError(
                Blocker(
                    code,
                    "A coordinator-managed read target is unsafe.",
                    "Replace it with a regular repository file before retrying.",
                    (_lexical_relative(root, target).as_posix(),),
                )
            ) from error
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise CoordinatorError(
                Blocker(
                    "unsafe_target_type",
                    "A coordinator-managed read target is not a regular file.",
                    "Replace it with a regular repository file before retrying.",
                    (_lexical_relative(root, target).as_posix(),),
                )
            )
        if max_bytes is not None and (max_bytes < 0 or info.st_size > max_bytes):
            raise CoordinatorError(
                Blocker(
                    "file_size_limit",
                    "A coordinator-managed read target exceeds its size limit.",
                    "Reduce or preserve the oversized file as manual evidence before retrying.",
                    (_lexical_relative(root, target).as_posix(),),
                )
            )
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory_fd)


def unlink_regular_file(
    root: Path,
    target: Path,
    *,
    expected_sha256: str,
) -> None:
    """Unlink one contained regular file only when its verified bytes match."""

    directory_fd, target_name, _root_info, _parent_info = _open_verified_parent(
        root, target
    )
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        try:
            descriptor = os.open(target_name, flags, dir_fd=directory_fd)
        except FileNotFoundError as error:
            raise CoordinatorError(
                Blocker(
                    "rollback_target_missing",
                    "A rollback target is no longer present.",
                    "Reconcile the interrupted run without deleting any replacement.",
                    (_lexical_relative(root, target).as_posix(),),
                )
            ) from error
        except OSError as error:
            raise CoordinatorError(
                Blocker(
                    "rollback_target_unsafe",
                    "A rollback target is not a safe regular file.",
                    "Replace or reconcile the unsafe target before recovery.",
                    (_lexical_relative(root, target).as_posix(),),
                )
            ) from error
        opened_before = os.fstat(descriptor)
        if not stat.S_ISREG(opened_before.st_mode):
            raise CoordinatorError(
                Blocker(
                    "rollback_target_unsafe",
                    "A rollback target is not a regular file.",
                    "Reconcile the target without automatic deletion.",
                    (_lexical_relative(root, target).as_posix(),),
                )
            )
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        opened_after = os.fstat(descriptor)
        named = os.stat(target_name, dir_fd=directory_fd, follow_symlinks=False)
        identity = (opened_before.st_dev, opened_before.st_ino)
        if identity != (opened_after.st_dev, opened_after.st_ino) or identity != (
            named.st_dev,
            named.st_ino,
        ):
            raise CoordinatorError(
                Blocker(
                    "rollback_target_changed",
                    "A rollback target changed during verification.",
                    "Retry only after concurrent filesystem changes stop.",
                    (_lexical_relative(root, target).as_posix(),),
                )
            )
        if digest.hexdigest() != expected_sha256:
            raise CoordinatorError(
                Blocker(
                    "recovery_hash_conflict",
                    "A rollback target no longer matches the interrupted run hash.",
                    "Inspect the replacement and choose repair or a new explicit decision.",
                    (_lexical_relative(root, target).as_posix(),),
                )
            )
        os.unlink(target_name, dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory_fd)


def atomic_write(
    target: Path,
    content: bytes,
    *,
    root: Path,
    public: bool,
    before_replace: Callable[[Path], None] | None = None,
    expected_sha256: str | None | object = _UNSPECIFIED,
) -> None:
    """Atomically replace one regular file using a stable parent descriptor."""

    directory_fd, target_name, root_before, parent_before = _open_verified_parent(root, target)
    temporary_name = f".{target.name}.coordinator-tmp-{secrets.token_hex(10)}"
    temporary_fd: int | None = None
    temporary_exists = False
    try:
        mode = 0o644 if public else 0o600
        try:
            target_info = os.stat(target_name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            target_info = None
        if target_info is not None:
            if not stat.S_ISREG(target_info.st_mode):
                raise CoordinatorError(
                    Blocker(
                        "unsafe_target_type",
                        "The managed target is not a regular file.",
                        "Replace it with a regular file or choose a different repository.",
                        (safe_display_path(root, target),),
                    )
                )
            mode = stat.S_IMODE(target_info.st_mode)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        temporary_fd = os.open(temporary_name, flags, mode, dir_fd=directory_fd)
        temporary_exists = True
        view = memoryview(content)
        while view:
            written = os.write(temporary_fd, view)
            view = view[written:]
        os.fchmod(temporary_fd, mode)
        os.fsync(temporary_fd)
        os.close(temporary_fd)
        temporary_fd = None

        if before_replace is not None:
            before_replace(target)

        if expected_sha256 is not _UNSPECIFIED:
            verification_fd: int | None = None
            current_hash: str | None = None
            current_info: os.stat_result | None = None
            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            try:
                try:
                    verification_fd = os.open(
                        target_name, flags, dir_fd=directory_fd
                    )
                except FileNotFoundError:
                    verification_fd = None
                if verification_fd is not None:
                    current_info = os.fstat(verification_fd)
                    if not stat.S_ISREG(current_info.st_mode):
                        raise CoordinatorError(
                            Blocker(
                                "concurrent_managed_change",
                                "A managed target changed type after planning.",
                                "Reconcile the current target and rerun the operation.",
                                (_lexical_relative(root, target).as_posix(),),
                            )
                        )
                    digest = hashlib.sha256()
                    while True:
                        chunk = os.read(verification_fd, 1024 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
                    current_hash = digest.hexdigest()
                if expected_sha256 is None:
                    matches = current_info is None
                else:
                    matches = current_info is not None and current_hash == expected_sha256
                if target_info is not None and current_info is not None:
                    matches = matches and (
                        target_info.st_dev,
                        target_info.st_ino,
                    ) == (current_info.st_dev, current_info.st_ino)
                if not matches:
                    raise CoordinatorError(
                        Blocker(
                            "concurrent_managed_change",
                            "A managed target changed after planning.",
                            "Reconcile the current bytes and rerun the operation.",
                            (_lexical_relative(root, target).as_posix(),),
                        )
                    )
            finally:
                if verification_fd is not None:
                    os.close(verification_fd)

        try:
            current_root = root.lstat()
            current_parent = target.parent.resolve(strict=True).stat()
        except (FileNotFoundError, OSError) as error:
            raise CoordinatorError(
                Blocker(
                    "path_race",
                    "The managed parent changed during an atomic write.",
                    "Restore the repository path and retry after confirming no concurrent writer.",
                    (target.name,),
                )
            ) from error
        if stat.S_ISLNK(current_root.st_mode) or (
            current_root.st_dev != root_before.st_dev
            or current_root.st_ino != root_before.st_ino
            or current_parent.st_dev != parent_before.st_dev
            or current_parent.st_ino != parent_before.st_ino
        ):
            raise CoordinatorError(
                Blocker(
                    "path_race",
                    "The managed parent changed during an atomic write.",
                    "Restore the repository path and retry after confirming no concurrent writer.",
                    (target.name,),
                )
            )
        os.replace(
            temporary_name,
            target_name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        temporary_exists = False
        os.fsync(directory_fd)
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)
        if temporary_exists:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
        os.close(directory_fd)


class ExclusiveRunLock:
    """Small exclusive lock with safe, non-content-bearing metadata."""

    def __init__(self, root: Path, path: Path, metadata: dict[str, Any]):
        self.root = root
        self.path = path
        self.metadata = metadata
        self._held = False
        self._directory_fd: int | None = None
        self._name: str | None = None
        self._lock_identity: tuple[int, int] | None = None
        self._lock_payload_sha256: str | None = None

    def _validated_payload(self) -> bytes:
        allowed = {"run_id", "host_id_sha256", "pid", "created_at", "journal_path"}
        if set(self.metadata) != allowed:
            raise CoordinatorError(
                Blocker(
                    "unsafe_lock_metadata",
                    "Coordinator lock metadata contains unsupported fields.",
                    "Use only the documented non-sensitive lock metadata fields.",
                )
            )
        run_id = self.metadata.get("run_id")
        host_id = self.metadata.get("host_id_sha256")
        pid = self.metadata.get("pid")
        created_at = self.metadata.get("created_at")
        journal_path = self.metadata.get("journal_path")
        try:
            parsed_run_id = str(UUID(run_id)) if isinstance(run_id, str) else ""
        except ValueError:
            parsed_run_id = ""
        timestamp_valid = False
        if isinstance(created_at, str) and re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
            created_at,
        ):
            try:
                datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")
                timestamp_valid = True
            except ValueError:
                timestamp_valid = False
        expected_journal = (
            re.compile(
                r"^docs/codex/MIGRATIONS/[0-9]{8}T[0-9]{6}Z-"
                + re.escape(parsed_run_id)
                + r"\.journal\.json$"
            )
            if parsed_run_id
            else None
        )
        typed = (
            parsed_run_id == run_id
            and isinstance(host_id, str)
            and re.fullmatch(r"[0-9a-f]{64}", host_id) is not None
            and isinstance(pid, int)
            and not isinstance(pid, bool)
            and pid > 0
            and timestamp_valid
            and isinstance(journal_path, str)
            and expected_journal is not None
            and expected_journal.fullmatch(journal_path) is not None
        )
        if not typed:
            raise CoordinatorError(
                Blocker(
                    "unsafe_lock_metadata",
                    "Coordinator lock metadata is incomplete or malformed.",
                    "Use a UUID run ID, hashed host ID, positive PID, UTC timestamp, and matching relative journal path.",
                )
            )
        payload_text = json.dumps(
            self.metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        if redact_text(payload_text) != payload_text or any(
            ord(character) < 32 for character in payload_text if character not in "\n\r\t"
        ):
            raise CoordinatorError(
                Blocker(
                    "unsafe_lock_metadata",
                    "Coordinator lock metadata contains sensitive or control content.",
                    "Use only non-sensitive run identity and process metadata.",
                )
            )
        if isinstance(journal_path, str) and (
            journal_path.startswith(("/", "\\"))
            or re.match(r"^[A-Za-z]:", journal_path)
            or "\\" in journal_path
            or ".." in Path(journal_path).parts
        ):
            raise CoordinatorError(
                Blocker(
                    "unsafe_lock_metadata",
                    "Coordinator lock metadata contains an unsafe journal path.",
                    "Use a repository-relative migration journal path.",
                )
            )
        return payload_text.encode("utf-8") + b"\n"

    def acquire(self) -> None:
        payload = self._validated_payload()
        directory_fd, name, _root_info, _parent_info = _open_verified_parent(
            self.root, self.path
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
        except FileExistsError as error:
            os.close(directory_fd)
            raise CoordinatorError(
                Blocker(
                    "active_coordinator_run",
                    "Another coordinator run lock already exists.",
                    "Run reconcile and classify the existing lock before mutation.",
                )
            ) from error
        except OSError as error:
            os.close(directory_fd)
            raise CoordinatorError(
                Blocker(
                    "lock_create_failed",
                    "The coordinator run lock could not be created safely.",
                    "Repair the migration directory and retry after confirming no active run.",
                )
            ) from error
        try:
            lock_info = os.fstat(descriptor)
            os.write(descriptor, payload)
            os.fsync(descriptor)
        except BaseException:
            os.close(descriptor)
            try:
                os.unlink(name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            os.close(directory_fd)
            raise
        os.close(descriptor)
        os.fsync(directory_fd)
        self._directory_fd = directory_fd
        self._name = name
        self._lock_identity = (lock_info.st_dev, lock_info.st_ino)
        self._lock_payload_sha256 = sha256_bytes(payload)
        self._held = True

    def replace_stale(self, expected_sha256: str) -> None:
        """Acquire a proven-stale lock with one hash-bound atomic replacement."""

        if self._held:
            raise CoordinatorError(
                Blocker(
                    "lock_already_held",
                    "The coordinator lock object is already held.",
                    "Release the current lock before another acquisition.",
                )
            )
        payload = self._validated_payload()
        atomic_write(
            self.path,
            payload,
            root=self.root,
            public=False,
            expected_sha256=expected_sha256,
        )
        directory_fd, name, _root_info, _parent_info = _open_verified_parent(
            self.root, self.path
        )
        descriptor: int | None = None
        try:
            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(name, flags, dir_fd=directory_fd)
            opened = os.fstat(descriptor)
            named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            content = bytearray()
            while True:
                chunk = os.read(descriptor, 4096)
                if not chunk:
                    break
                content.extend(chunk)
            if (
                not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
                or bytes(content) != payload
            ):
                raise CoordinatorError(
                    Blocker(
                        "lock_identity_changed",
                        "The coordinator lock changed during stale-lock acquisition.",
                        "Run reconcile again and preserve the conflicting lock evidence.",
                    )
                )
            self._directory_fd = directory_fd
            self._name = name
            self._lock_identity = (opened.st_dev, opened.st_ino)
            self._lock_payload_sha256 = sha256_bytes(payload)
            self._held = True
            directory_fd = -1
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if directory_fd >= 0:
                os.close(directory_fd)

    def release(self) -> None:
        if self._held and self._directory_fd is not None and self._name is not None:
            descriptor: int | None = None
            quarantine_name = (
                f".{self._name}.coordinator-release-{secrets.token_hex(10)}"
            )
            try:
                try:
                    os.rename(
                        self._name,
                        quarantine_name,
                        src_dir_fd=self._directory_fd,
                        dst_dir_fd=self._directory_fd,
                    )
                except FileNotFoundError as error:
                    raise CoordinatorError(
                        Blocker(
                            "lock_identity_changed",
                            "The coordinator lock disappeared while held.",
                            "Preserve the repository and reconcile lock ownership manually.",
                        )
                    ) from error
                flags = os.O_RDONLY
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                descriptor = os.open(
                    quarantine_name, flags, dir_fd=self._directory_fd
                )
                opened = os.fstat(descriptor)
                quarantined_info = os.stat(
                    quarantine_name,
                    dir_fd=self._directory_fd,
                    follow_symlinks=False,
                )
                content = bytearray()
                while True:
                    chunk = os.read(descriptor, 4096)
                    if not chunk:
                        break
                    content.extend(chunk)
                if not stat.S_ISREG(opened.st_mode):
                    raise CoordinatorError(
                        Blocker(
                            "lock_identity_changed",
                            "The coordinator lock changed type while held.",
                            "Reconcile the lock before attempting another mutation.",
                        )
                    )
                opened_identity = (opened.st_dev, opened.st_ino)
                quarantined_identity = (
                    quarantined_info.st_dev,
                    quarantined_info.st_ino,
                )
                if (
                    self._lock_identity != opened_identity
                    or opened_identity != quarantined_identity
                    or self._lock_payload_sha256 != sha256_bytes(bytes(content))
                ):
                    raise CoordinatorError(
                        Blocker(
                            "lock_identity_changed",
                            "The coordinator lock was replaced while held; the replacement was quarantined.",
                            "Preserve the quarantined replacement and reconcile lock ownership manually.",
                        )
                    )
                os.unlink(quarantine_name, dir_fd=self._directory_fd)
                os.fsync(self._directory_fd)
            finally:
                if descriptor is not None:
                    os.close(descriptor)
                os.close(self._directory_fd)
                self._directory_fd = None
                self._name = None
                self._lock_identity = None
                self._lock_payload_sha256 = None
                self._held = False

    def assert_visible(self) -> None:
        """Require the held lock parent to remain the visible managed parent."""

        if not self._held or self._directory_fd is None:
            raise CoordinatorError(
                Blocker(
                    "lock_not_held",
                    "The coordinator lock is not held.",
                    "Acquire the current run lock before mutation.",
                )
            )
        current_fd, _name, _root_info, _parent_info = _open_verified_parent(
            self.root, self.path
        )
        try:
            held = os.fstat(self._directory_fd)
            current = os.fstat(current_fd)
            if (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino):
                raise CoordinatorError(
                    Blocker(
                        "lock_parent_changed",
                        "The visible coordinator lock parent changed while held.",
                        "Stop mutation and reconcile the competing migration directory.",
                    )
                )
        finally:
            os.close(current_fd)

    def __enter__(self) -> "ExclusiveRunLock":
        self.acquire()
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.release()


__all__ = [
    "CoordinatorError",
    "ExclusiveRunLock",
    "assert_contained",
    "atomic_write",
    "contains_credential",
    "ensure_directory",
    "read_regular_file",
    "redact_text",
    "safe_display_path",
    "sha256_bytes",
    "sha256_file",
    "unlink_regular_file",
]
