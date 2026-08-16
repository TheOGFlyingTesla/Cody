#!/usr/bin/env python3
"""Verify and install the Cody Coordinator skill into a content-addressed store."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Sequence

from build_release import (
    MANIFEST_NAME,
    ReleaseError,
    _load_manifest,
    inventory_release,
    redact_release_text,
    verify_checksums,
)


SKILL_NAME = "cody-coordinator"
VERSION = "0.1.0"


class InstallError(RuntimeError):
    def __init__(self, code: str, message: str, *, token: str | None = None):
        super().__init__(message)
        self.code = code
        self.token = token


def _result(ok: bool, changed: bool, action: str, **metadata: Any) -> dict[str, Any]:
    return {
        "ok": ok,
        "changed": changed,
        "action": action,
        "standard_version": VERSION,
        **metadata,
    }


def _codex_home() -> Path:
    raw = os.environ.get("CODEX_HOME")
    path = Path(raw).expanduser() if raw else Path.home() / ".codex"
    if not path.is_absolute():
        raise InstallError("unsafe_codex_home", "Codex home must be an absolute path.")
    return path


def _safe_owned_directory(path: Path, *, may_be_absent: bool) -> None:
    _require_secure_filesystem_support()
    if path.is_symlink():
        raise InstallError("unsafe_codex_home", "Codex home must not be a symlink.")
    probe = path if path.exists() else path.parent
    if not probe.is_dir() or probe.is_symlink():
        raise InstallError("unsafe_codex_home", "Codex home parent must be a real directory.")
    info = probe.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise InstallError(
            "unsafe_codex_home",
            "Codex home or its parent must be user-owned and not group/world writable.",
        )
    if path.exists():
        info = path.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise InstallError(
                "unsafe_codex_home",
                "Codex home must be a user-owned, non-group/world-writable directory.",
            )
    elif not may_be_absent:
        raise InstallError("unsafe_codex_home", "Codex home does not exist.")


def _skill_checksums(release_root: Path) -> dict[str, str]:
    manifest = _load_manifest(release_root)
    inventory = inventory_release(release_root)
    checksums = verify_checksums(release_root)
    if manifest["files"] != [path for path in inventory if path != MANIFEST_NAME]:
        raise InstallError("invalid_release", "Release inventory differs from its manifest.")
    if list(checksums) != inventory:
        raise InstallError("invalid_release", "Release checksums differ from its inventory.")
    selected = {
        relative: digest
        for relative, digest in checksums.items()
        if relative not in {MANIFEST_NAME, "SHA256SUMS"}
    }
    if not selected or "SKILL.md" not in selected or "VERSION" not in selected:
        raise InstallError("invalid_release", "Release checksums omit the coordinator skill.")
    version_path = release_root / "VERSION"
    if version_path.is_symlink() or version_path.read_bytes() != (VERSION + "\n").encode("ascii"):
        raise InstallError("invalid_release", "Skill VERSION does not match the installer.")
    return selected


def _require_secure_filesystem_support() -> None:
    """Reject native platforms whose secure descriptor operations are unproved."""

    if os.name == "nt" or not hasattr(os, "getuid"):
        raise InstallError(
            "unsupported_platform",
            "Native Windows secure filesystem installation is unsupported.",
        )
    required = (
        "O_NOFOLLOW",
        "O_DIRECTORY",
        "supports_dir_fd",
    )
    if any(not hasattr(os, name) for name in required):
        raise InstallError(
            "unsupported_platform",
            "Secure filesystem installation is unsupported on this platform.",
        )
    dir_fd_functions = (
        os.open,
        os.mkdir,
        os.stat,
        os.unlink,
        os.rmdir,
        os.rename,
    )
    if not all(function in os.supports_dir_fd for function in dir_fd_functions):
        raise InstallError(
            "unsupported_platform",
            "Secure filesystem installation is unsupported on this platform.",
        )


def _content_hash(checksums: dict[str, str]) -> str:
    canonical = "".join(
        f"{checksums[path]}  {path}\n" for path in sorted(checksums, key=lambda value: value.encode())
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _directory_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _open_home_fd(home: Path) -> tuple[int, tuple[int, int]]:
    try:
        before = home.lstat()
        descriptor = os.open(home, _directory_flags())
    except OSError as error:
        raise InstallError("unsafe_codex_home", "Codex home could not be opened safely.") from error
    opened = os.fstat(descriptor)
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISDIR(before.st_mode)
        or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
    ):
        os.close(descriptor)
        raise InstallError("unsafe_codex_home", "Codex home changed while opening.")
    return descriptor, (opened.st_dev, opened.st_ino)


def _validate_open_directory(info: os.stat_result) -> None:
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o022
    ):
        raise InstallError(
            "unsafe_install_parent",
            "Coordinator install parents must be user-owned and not group/world writable.",
        )


def _open_chain_fd(
    root_fd: int,
    components: tuple[str, ...],
    *,
    create: bool,
) -> tuple[int | None, tuple[tuple[int, int], ...]]:
    current_fd = os.dup(root_fd)
    identities: list[tuple[int, int]] = []
    try:
        for component in components:
            try:
                next_fd = os.open(component, _directory_flags(), dir_fd=current_fd)
            except FileNotFoundError:
                if not create:
                    os.close(current_fd)
                    current_fd = -1
                    return None, tuple(identities)
                try:
                    os.mkdir(component, mode=0o700, dir_fd=current_fd)
                    next_fd = os.open(
                        component, _directory_flags(), dir_fd=current_fd
                    )
                except OSError as error:
                    raise InstallError(
                        "unsafe_install_parent",
                        "A coordinator install parent could not be created safely.",
                    ) from error
            except OSError as error:
                raise InstallError(
                    "unsafe_install_parent",
                    "A coordinator install parent is a symlink or non-directory.",
                ) from error
            info = os.fstat(next_fd)
            _validate_open_directory(info)
            identities.append((info.st_dev, info.st_ino))
            os.close(current_fd)
            current_fd = next_fd
        result = current_fd
        current_fd = -1
        return result, tuple(identities)
    finally:
        if current_fd >= 0:
            os.close(current_fd)


def _verify_named_chain_fd(
    root_fd: int,
    components: tuple[str, ...],
    identities: tuple[tuple[int, int], ...],
) -> bool:
    current_fd = os.dup(root_fd)
    try:
        for index, component in enumerate(components):
            try:
                next_fd = os.open(component, _directory_flags(), dir_fd=current_fd)
            except OSError:
                return False
            info = os.fstat(next_fd)
            os.close(current_fd)
            current_fd = next_fd
            if index >= len(identities) or (info.st_dev, info.st_ino) != identities[index]:
                return False
        return len(identities) == len(components)
    finally:
        os.close(current_fd)


def _verify_home_identity(home: Path, identity: tuple[int, int]) -> bool:
    try:
        info = home.lstat()
    except FileNotFoundError:
        return False
    return (
        stat.S_ISDIR(info.st_mode)
        and not stat.S_ISLNK(info.st_mode)
        and (info.st_dev, info.st_ino) == identity
    )


def _hash_fd(descriptor: int) -> str:
    digest = hashlib.sha256()
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def _tree_hashes_fd(root_fd: int, prefix: str = "") -> dict[str, str] | None:
    actual: dict[str, str] = {}
    try:
        names = sorted(os.listdir(root_fd), key=lambda value: value.encode("utf-8"))
    except OSError:
        return None
    for name in names:
        relative = f"{prefix}/{name}" if prefix else name
        try:
            info = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        except OSError:
            return None
        if stat.S_ISDIR(info.st_mode):
            try:
                child_fd = os.open(name, _directory_flags(), dir_fd=root_fd)
            except OSError:
                return None
            try:
                child = _tree_hashes_fd(child_fd, relative)
            finally:
                os.close(child_fd)
            if child is None:
                return None
            actual.update(child)
        elif stat.S_ISREG(info.st_mode):
            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                file_fd = os.open(name, flags, dir_fd=root_fd)
            except OSError:
                return None
            try:
                actual[relative] = _hash_fd(file_fd)
            finally:
                os.close(file_fd)
        else:
            return None
    return actual


def _open_directory_at(parent_fd: int, name: str) -> int | None:
    try:
        return os.open(name, _directory_flags(), dir_fd=parent_fd)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise InstallError(
            "content_address_conflict",
            "The content-addressed target is not a safe directory.",
        ) from error


def _verify_tree_at(parent_fd: int, name: str, checksums: dict[str, str]) -> bool:
    descriptor = _open_directory_at(parent_fd, name)
    if descriptor is None:
        return False
    try:
        actual = _tree_hashes_fd(descriptor)
        return actual == checksums
    finally:
        os.close(descriptor)


def _open_relative_parent_fd(root_fd: int, relative: str) -> tuple[int, str]:
    parts = Path(relative).parts
    current_fd = os.dup(root_fd)
    try:
        for component in parts[:-1]:
            try:
                os.mkdir(component, mode=0o755, dir_fd=current_fd)
            except FileExistsError:
                pass
            next_fd = os.open(component, _directory_flags(), dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        result = current_fd
        current_fd = -1
        return result, parts[-1]
    except OSError as error:
        raise InstallError("copy_failed", "A copied skill directory became unsafe.") from error
    finally:
        if current_fd >= 0:
            os.close(current_fd)


def _remove_tree_at(parent_fd: int, name: str) -> None:
    descriptor = _open_directory_at(parent_fd, name)
    if descriptor is None:
        return
    try:
        for child in os.listdir(descriptor):
            info = os.stat(child, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                _remove_tree_at(descriptor, child)
            else:
                os.unlink(child, dir_fd=descriptor)
    finally:
        os.close(descriptor)
    os.rmdir(name, dir_fd=parent_fd)


def _copy_skill_fd(
    release_root: Path,
    store_fd: int,
    target_name: str,
    checksums: dict[str, str],
) -> None:
    temporary_name = f".{target_name}.{os.getpid()}-{secrets.token_hex(8)}"
    try:
        os.mkdir(temporary_name, mode=0o700, dir_fd=store_fd)
        temporary_fd = os.open(temporary_name, _directory_flags(), dir_fd=store_fd)
    except OSError as error:
        raise InstallError("copy_failed", "The temporary skill store could not be created.") from error
    renamed = False
    try:
        for relative in sorted(checksums, key=lambda value: value.encode("utf-8")):
            source = release_root / relative
            if source.is_symlink() or not source.is_file():
                raise InstallError("invalid_release", "Skill source is not a regular file.")
            content = source.read_bytes()
            if hashlib.sha256(content).hexdigest() != checksums[relative]:
                raise InstallError("source_changed", "Skill source changed during installation.")
            parent_fd, file_name = _open_relative_parent_fd(temporary_fd, relative)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            mode = 0o755 if relative in {
                "scripts/coordinator_standard.py",
                "scripts/build_release.py",
                "scripts/install_skill.py",
            } else 0o644
            file_fd: int | None = None
            try:
                file_fd = os.open(file_name, flags, mode, dir_fd=parent_fd)
                view = memoryview(content)
                while view:
                    written = os.write(file_fd, view)
                    view = view[written:]
                os.fchmod(file_fd, mode)
                os.fsync(file_fd)
            finally:
                if file_fd is not None:
                    os.close(file_fd)
                os.close(parent_fd)
        if _tree_hashes_fd(temporary_fd) != checksums:
            raise InstallError("copy_verification_failed", "Copied skill failed verification.")
        try:
            os.rename(
                temporary_name,
                target_name,
                src_dir_fd=store_fd,
                dst_dir_fd=store_fd,
            )
            renamed = True
        except FileExistsError:
            if not _verify_tree_at(store_fd, target_name, checksums):
                raise InstallError(
                    "content_address_conflict",
                    "Existing content-addressed target does not match the release.",
                )
    finally:
        os.close(temporary_fd)
        if not renamed:
            try:
                _remove_tree_at(store_fd, temporary_name)
            except (InstallError, OSError):
                pass


def _entry_token_fd(parent_fd: int, name: str, expected_hash: str, action: str) -> str:
    info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    link = os.readlink(name, dir_fd=parent_fd) if stat.S_ISLNK(info.st_mode) else "non-symlink"
    material = {
        "action": action,
        "expected_content_hash": expected_hash,
        "kind": stat.S_IFMT(info.st_mode),
        "device": info.st_dev,
        "inode": info.st_ino,
        "link": link,
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _stable_state_fd(
    skills_fd: int, stable_name: str, expected_link: str, target_ok: bool
) -> str:
    try:
        info = os.stat(stable_name, dir_fd=skills_fd, follow_symlinks=False)
    except FileNotFoundError:
        return "absent"
    if not stat.S_ISLNK(info.st_mode):
        return "unknown"
    return (
        "current"
        if target_ok and os.readlink(stable_name, dir_fd=skills_fd) == expected_link
        else "different-link"
    )


def _switch_link_fd(
    skills_fd: int,
    stable_name: str,
    expected_link: str,
    approval: str | None,
    content_hash: str,
) -> None:
    state = _stable_state_fd(skills_fd, stable_name, expected_link, True)
    if state == "current":
        return
    if state != "absent":
        action = "replace-link" if state == "different-link" else "unknown-stable-path"
        token = _entry_token_fd(skills_fd, stable_name, content_hash, action)
        if state == "unknown":
            raise InstallError(
                "unknown_stable_path",
                "The stable coordinator path is unknown and was not replaced.",
                token=token,
            )
        if approval != token:
            raise InstallError(
                "stable_link_conflict",
                "A different coordinator skill link already exists.",
                token=token,
            )
    temporary = f".{stable_name}.link-{os.getpid()}-{secrets.token_hex(6)}"
    try:
        os.symlink(expected_link, temporary, dir_fd=skills_fd)
        os.replace(
            temporary,
            stable_name,
            src_dir_fd=skills_fd,
            dst_dir_fd=skills_fd,
        )
    finally:
        try:
            os.unlink(temporary, dir_fd=skills_fd)
        except FileNotFoundError:
            pass


def install(
    release_root: Path,
    *,
    check: bool,
    approval: str | None,
) -> dict[str, Any]:
    _require_secure_filesystem_support()
    root = release_root.resolve(strict=True)
    checksums = _skill_checksums(root)
    digest = _content_hash(checksums)
    home = _codex_home()
    _safe_owned_directory(home, may_be_absent=True)
    if not home.exists():
        if check:
            return _result(True, True, "install-planned", content_hash=digest)
        home.mkdir(mode=0o700)
    _safe_owned_directory(home, may_be_absent=False)
    home_fd, home_identity = _open_home_fd(home)
    store_components = ("coordinator-standards", SKILL_NAME)
    skills_components = ("skills",)
    store_fd: int | None = None
    skills_fd: int | None = None
    try:
        store_fd, store_identities = _open_chain_fd(
            home_fd, store_components, create=not check
        )
        skills_fd, skills_identities = _open_chain_fd(
            home_fd, skills_components, create=not check
        )
        target_name = f"{VERSION}-{digest}"
        expected_link = f"../coordinator-standards/{SKILL_NAME}/{target_name}"
        target_ok = (
            _verify_tree_at(store_fd, target_name, checksums)
            if store_fd is not None
            else False
        )
        if store_fd is not None:
            try:
                target_info = os.stat(
                    target_name, dir_fd=store_fd, follow_symlinks=False
                )
            except FileNotFoundError:
                target_info = None
            if target_info is not None and not target_ok:
                raise InstallError(
                    "content_address_conflict",
                    "The expected content-addressed target exists with different bytes.",
                )
        stable_state = (
            _stable_state_fd(skills_fd, SKILL_NAME, expected_link, target_ok)
            if skills_fd is not None
            else "absent"
        )
        if stable_state == "current":
            return _result(True, False, "already-installed", content_hash=digest)
        if stable_state != "absent" and skills_fd is not None:
            action = (
                "replace-link"
                if stable_state == "different-link"
                else "unknown-stable-path"
            )
            token = _entry_token_fd(
                skills_fd, SKILL_NAME, digest, action
            )
            if stable_state == "unknown":
                raise InstallError(
                    "unknown_stable_path",
                    "The stable coordinator path is unknown and was not replaced.",
                    token=token,
                )
            if approval != token:
                raise InstallError(
                    "stable_link_conflict",
                    "A different coordinator skill link already exists.",
                    token=token,
                )
        if check:
            return _result(True, True, "install-planned", content_hash=digest)
        if store_fd is None or skills_fd is None:
            raise InstallError("unsafe_install_parent", "Install parents are unavailable.")
        if not target_ok:
            _copy_skill_fd(root, store_fd, target_name, checksums)
        if not _verify_tree_at(store_fd, target_name, checksums):
            raise InstallError(
                "copy_verification_failed", "Installed skill hash verification failed."
            )
        _switch_link_fd(
            skills_fd,
            SKILL_NAME,
            expected_link,
            approval,
            digest,
        )
        if (
            _stable_state_fd(
                skills_fd, SKILL_NAME, expected_link, True
            )
            != "current"
            or not _verify_tree_at(store_fd, target_name, checksums)
            or not _verify_named_chain_fd(
                home_fd, store_components, store_identities
            )
            or not _verify_named_chain_fd(
                home_fd, skills_components, skills_identities
            )
            or not _verify_home_identity(home, home_identity)
        ):
            raise InstallError(
                "link_verification_failed",
                "Installed path identities changed before verification completed.",
            )
        return _result(True, True, "installed", content_hash=digest)
    finally:
        if store_fd is not None:
            os.close(store_fd)
        if skills_fd is not None:
            os.close(skills_fd)
        os.close(home_fd)


def uninstall(*, check: bool, approval: str | None, release_root: Path) -> dict[str, Any]:
    _require_secure_filesystem_support()
    checksums = _skill_checksums(release_root.resolve(strict=True))
    digest = _content_hash(checksums)
    home = _codex_home()
    _safe_owned_directory(home, may_be_absent=False)
    home_fd, home_identity = _open_home_fd(home)
    skills_fd: int | None = None
    try:
        skills_fd, skills_identities = _open_chain_fd(
            home_fd, ("skills",), create=False
        )
        if skills_fd is None:
            return _result(True, False, "already-uninstalled", content_hash=digest)
        try:
            info = os.stat(
                SKILL_NAME, dir_fd=skills_fd, follow_symlinks=False
            )
        except FileNotFoundError:
            return _result(True, False, "already-uninstalled", content_hash=digest)
        if not stat.S_ISLNK(info.st_mode):
            raise InstallError(
                "unknown_stable_path",
                "The stable coordinator path is not a symlink and was not removed.",
            )
        token = _entry_token_fd(
            skills_fd, SKILL_NAME, digest, "remove-link"
        )
        if check or approval != token:
            raise InstallError(
                "removal_decision_required",
                "Removing the stable coordinator link requires the current decision token.",
                token=token,
            )
        os.unlink(SKILL_NAME, dir_fd=skills_fd)
        if (
            not _verify_named_chain_fd(
                home_fd, ("skills",), skills_identities
            )
            or not _verify_home_identity(home, home_identity)
        ):
            raise InstallError(
                "install_parent_changed", "Install parents changed during uninstall."
            )
        return _result(True, True, "uninstalled", content_hash=digest)
    finally:
        if skills_fd is not None:
            os.close(skills_fd)
        os.close(home_fd)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install the verified Cody Coordinator skill")
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--approve-replacement")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--approve-removal")
    arguments = parser.parse_args(argv)
    try:
        result = (
            uninstall(
                check=arguments.check,
                approval=arguments.approve_removal,
                release_root=arguments.release_root,
            )
            if arguments.uninstall
            else install(
                arguments.release_root,
                check=arguments.check,
                approval=arguments.approve_replacement,
            )
        )
    except (InstallError, ReleaseError) as error:
        payload = {
            "ok": False,
            "changed": False,
            "code": getattr(error, "code", "invalid_release"),
            "message": redact_release_text(str(error)),
        }
        token = getattr(error, "token", None)
        if token:
            payload["decision_token"] = token
        print(json.dumps(payload, sort_keys=True))
        return 2
    except OSError:
        print(
            json.dumps(
                {
                    "ok": False,
                    "changed": False,
                    "code": "install_io_failure",
                    "message": "A local install path changed or became unavailable.",
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
