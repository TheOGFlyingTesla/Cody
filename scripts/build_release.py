#!/usr/bin/env python3
"""Build and verify deterministic Cody Coordinator releases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import unicodedata
import zipfile
from typing import Any, Iterable, Sequence


MANIFEST_NAME = "release_manifest.json"
CHECKSUM_NAME = "SHA256SUMS"
STANDARD_NAME = "cody-coordinator"
STANDARD_VERSION = "0.1.0"
EXCLUDED_NAMES = {"__pycache__"}
IGNORED_DIRECTORIES = {".git"}
IGNORED_ROOT_PATHS = {".github", "docs/codex"}
EXECUTABLES = {
    "scripts/coordinator_standard.py",
    "scripts/build_release.py",
    "scripts/install_skill.py",
    "scripts/quick_validate.py",
    "scripts/routing_contract.py",
    "scripts/routing_live_eval.py",
}

# This is the source-to-bundle boundary.  Keep it as a literal inventory: a
# new source file must be deliberately reviewed here before it can enter a
# release.  Runtime data files are listed alongside Python modules because
# the installed skill must work without the source checkout.
RELEASE_ALLOWLIST = frozenset(
    {
        "CHANGELOG.md",
        "CODE_OF_CONDUCT.md",
        "CONTRIBUTING.md",
        "GOVERNANCE.md",
        "LICENSE",
        "MAINTAINERS.md",
        "README.md",
        "SECURITY.md",
        "SKILL.md",
        "SUPPORT.md",
        "THIRD_PARTY_NOTICES.md",
        "VERSION",
        "agents/openai.yaml",
        "assets/cody-social-preview.jpg",
        "assets/repo-template/AGENTS.managed.md",
        "assets/repo-template/docs/codex/DECISIONS.md.tmpl",
        "assets/repo-template/docs/codex/MIGRATIONS/.gitkeep",
        "assets/repo-template/docs/codex/PROJECT.md.tmpl",
        "assets/repo-template/docs/codex/ROADMAP.md.tmpl",
        "assets/repo-template/docs/codex/STANDARD.json.tmpl",
        "assets/repo-template/docs/codex/STATUS.md.tmpl",
        "assets/repo-template/docs/codex/WORK_ITEMS/.gitkeep",
        "assets/repo-template/docs/codex/WORK_ITEMS/WORK_ITEM_TEMPLATE.md.tmpl",
        "assets/schema/journal.schema.json",
        "assets/schema/standard.schema.json",
        "docs/CONFIGURATION.md",
        "docs/ADOPTION.md",
        "docs/BEHAVIORAL_CHECKS.md",
        "docs/CODEX_FOR_OSS.md",
        "docs/INSTALLATION.md",
        "docs/LIMITATIONS.md",
        "docs/PORTABILITY.md",
        "docs/QUICKSTART.md",
        "docs/RELEASES.md",
        "docs/SAFETY.md",
        "references/authority-matrix.md",
        "references/completion-report.md",
        "references/execution-efficiency.md",
        "references/model-routing-contract.json",
        "references/operating-model.md",
        "references/orchestration-policy.md",
        "references/repository-contract.md",
        "scripts/build_release.py",
        "scripts/coordinator_standard.py",
        "scripts/coordinator_standard/__init__.py",
        "scripts/coordinator_standard/cli.py",
        "scripts/coordinator_standard/git_state.py",
        "scripts/coordinator_standard/inspector.py",
        "scripts/coordinator_standard/journal.py",
        "scripts/coordinator_standard/markers.py",
        "scripts/coordinator_standard/migrate_v30.py",
        "scripts/coordinator_standard/model.py",
        "scripts/coordinator_standard/operations.py",
        "scripts/coordinator_standard/safety.py",
        "scripts/coordinator_standard/templates.py",
        "scripts/coordinator_standard/validator.py",
        "scripts/install_skill.py",
        "scripts/quick_validate.py",
        "scripts/routing_contract.py",
        "scripts/routing_live_eval.py",
    }
)
_ALLOWLIST_DIRECTORIES = frozenset(
    {
        "assets",
        "assets/repo-template",
        "assets/repo-template/docs",
        "assets/repo-template/docs/codex",
        "assets/repo-template/docs/codex/MIGRATIONS",
        "assets/repo-template/docs/codex/WORK_ITEMS",
        "assets/schema",
        "agents",
        "docs",
        "references",
        "scripts",
        "scripts/coordinator_standard",
    }
)
_KNOWN_SOURCE_EXCLUSIONS = frozenset(
    {
        ".cody",
        ".agents",
        ".github",
        ".git",
        ".gitignore",
        ".gitattributes",
        ".editorconfig",
        "AGENTS.md",
        "docs/codex",
        "examples",
        "plugins",
        "scripts/sync_plugin_runtime.py",
        "tests",
        ".coverage",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "build",
        "dist",
    }
)
_KNOWN_ARTIFACT_SUFFIXES = (".pyc", ".pyo", ".tmp", ".zip")
KNOWN_TOKEN = re.compile(
    rb"(?i)\b(?:gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{12,}|"
    rb"sk-[A-Za-z0-9_-]{16,}|sk_(?:live|test)_[A-Za-z0-9_-]{12,}|"
    rb"xox[baprs]-[A-Za-z0-9-]{10,}|"
    rb"AKIA[0-9A-Z]{16})\b"
)
KNOWN_TOKEN_TEXT = re.compile(KNOWN_TOKEN.pattern.decode("ascii"))
SECRET_ASSIGNMENT_TEXT = re.compile(
    r"(?i)(?<![A-Za-z0-9_-])((?:[A-Za-z0-9]+[_-])*(?:api[_-]?key|"
    r"access[_-]?(?:key|token)|client[_-]?secret|refresh[_-]?token|"
    r"private[_-]?key|token|secret|password)(?:[_-][A-Za-z0-9]+)*)"
    r"(\s*[:=]\s*)(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;]+)"
)
URL_USERINFO_TEXT = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^/@\s]+@")
SCP_USER_TEXT = re.compile(r"(?<![/\w])[^@\s/:]+@([A-Za-z0-9.-]+):")
AUTH_HEADER_TEXT = re.compile(r"(?i)(authorization\s*:\s*(?:bearer|basic)\s+)[^\s]+")
SECRET_QUERY_TEXT = re.compile(
    r"(?i)([?&](?:access_token|auth|client_secret|key|oauth_token|password|"
    r"refresh_token|secret|token)=)[^&#\s]+"
)
PRIVATE_KEY = re.compile(
    rb"(?s)-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----.*?"
    rb"-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"
)
PRIVATE_KEY_TEXT = re.compile(PRIVATE_KEY.pattern.decode("ascii"))
SECRET_ASSIGNMENT = re.compile(
    rb"(?m)^(?:"
    rb"(?:[ \t]*export[ \t]+)?(?:[A-Z0-9]+_)*(?:API_KEY|PASSWORD|"
    rb"CLIENT_SECRET|ACCESS_TOKEN|REFRESH_TOKEN|PRIVATE_KEY|SECRET|TOKEN)"
    rb"[ \t]*=[ \t]*(?!re\.compile\()[^\s,;]+|"
    rb"[ \t]*(?i:(?:[a-z0-9]+[_-])*(?:api[_-]?key|password|client[_-]?secret|"
    rb"access[_-]?token|refresh[_-]?token|private[_-]?key|secret|token))"
    rb"[ \t]*:[ \t]*(?!(?:str|bytes|int|float|bool|None)(?:[ \t,]|$))"
    rb"[^\s,;]+)"
)
AUTH_HEADER = re.compile(AUTH_HEADER_TEXT.pattern.encode("ascii"))


def redact_release_text(value: str) -> str:
    redacted = PRIVATE_KEY_TEXT.sub("[PRIVATE KEY REDACTED]", value)
    redacted = URL_USERINFO_TEXT.sub(r"\1[REDACTED]@", redacted)
    redacted = SCP_USER_TEXT.sub(r"[REDACTED]@\1:", redacted)
    redacted = AUTH_HEADER_TEXT.sub(r"\1[REDACTED]", redacted)
    redacted = SECRET_QUERY_TEXT.sub(r"\1[REDACTED]", redacted)
    redacted = SECRET_ASSIGNMENT_TEXT.sub(r"\1\2[REDACTED]", redacted)
    return KNOWN_TOKEN_TEXT.sub("[REDACTED]", redacted)


class ReleaseError(RuntimeError):
    pass


def _sort_paths(values: Iterable[str]) -> list[str]:
    return sorted(values, key=lambda value: value.encode("utf-8"))


def _safe_name(value: str) -> bool:
    if not value or value.startswith("/") or "\\" in value or "\x00" in value:
        return False
    if unicodedata.normalize("NFC", value) != value or re.match(r"^[A-Za-z]:", value):
        return False
    path = PurePosixPath(value)
    return (
        path.as_posix() == value
        and ".." not in path.parts
        and "." not in path.parts
        and all(ord(character) >= 32 for character in value)
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_release_content(relative: str, content: bytes) -> None:
    if KNOWN_TOKEN.search(content):
        raise ReleaseError(f"credential-shaped value in {relative}")
    if PRIVATE_KEY.search(content):
        raise ReleaseError(f"private-key block in {relative}")
    if not relative.startswith("tests/") and (
        SECRET_ASSIGNMENT.search(content) or AUTH_HEADER.search(content)
    ):
        raise ReleaseError(f"credential-bearing assignment or header in {relative}")
    if relative.endswith(".py"):
        try:
            compile(content.decode("utf-8"), relative, "exec")
        except (UnicodeError, SyntaxError) as error:
            raise ReleaseError(f"invalid Python source: {relative}") from error
    if relative.endswith((".md", ".json", ".yaml", ".yml")) and not relative.startswith("tests/"):
        text = content.decode("utf-8")
        if any(marker in text for marker in ("/Users/", "/Volumes/", "C:\\Users\\")):
            raise ReleaseError(f"personal absolute path in {relative}")
        if not relative.endswith(".tmpl") and re.search(
            r"(?:\$PROJECT_|\$STANDARD_|<PROJECT|\{\{[^}]+\}\})", text
        ):
            raise ReleaseError(f"unresolved placeholder in {relative}")


def _known_source_exclusion(relative: str) -> bool:
    if relative in _KNOWN_SOURCE_EXCLUSIONS:
        return True
    if any(part == "__pycache__" for part in PurePosixPath(relative).parts):
        return True
    if relative.rsplit("/", 1)[-1] == ".DS_Store":
        return True
    name = relative.rsplit("/", 1)[-1]
    if name in {MANIFEST_NAME, CHECKSUM_NAME} or name.endswith(_KNOWN_ARTIFACT_SUFFIXES):
        return True
    return any(
        relative.startswith(f"{excluded}/")
        for excluded in _KNOWN_SOURCE_EXCLUSIONS
        if excluded in {
            ".cody",
            ".agents",
            ".github",
            ".git",
            "docs/codex",
            "examples",
            "plugins",
            "tests",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "build",
            "dist",
        }
    )


def _source_files(root: Path) -> list[str]:
    """Return the literal source allowlist after rejecting unknown paths."""

    root = root.resolve(strict=True)
    found: list[str] = []
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        base = Path(directory)
        directory_names.sort(key=lambda value: value.encode("utf-8"))
        file_names.sort(key=lambda value: value.encode("utf-8"))
        for name in tuple(directory_names):
            path = base / name
            relative = path.relative_to(root).as_posix()
            info = path.lstat()
            if _known_source_exclusion(relative):
                directory_names.remove(name)
                continue
            if relative not in _ALLOWLIST_DIRECTORIES:
                raise ReleaseError(f"unknown source path: {relative}")
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise ReleaseError(f"unsafe source directory: {relative}")
        for name in file_names:
            path = base / name
            relative = path.relative_to(root).as_posix()
            if _known_source_exclusion(relative):
                continue
            if relative not in RELEASE_ALLOWLIST:
                raise ReleaseError(f"unknown source path: {relative}")
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise ReleaseError(f"unsafe source file: {relative}")
            content = path.read_bytes()
            _validate_release_content(relative, content)
            found.append(relative)
    missing = _sort_paths(RELEASE_ALLOWLIST - set(found))
    if missing:
        raise ReleaseError(f"allowlisted source file is missing: {missing[0]}")
    return _sort_paths(found)


def inventory_release(root: Path) -> list[str]:
    root = root.resolve(strict=True)
    files: list[str] = []
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in tuple(directory_names):
            path = base / name
            info = path.lstat()
            relative = path.relative_to(root).as_posix()
            if name in IGNORED_DIRECTORIES or relative in IGNORED_ROOT_PATHS:
                directory_names.remove(name)
                continue
            if name in EXCLUDED_NAMES:
                raise ReleaseError(f"excluded generated path present: {relative}")
            if stat.S_ISLNK(info.st_mode):
                raise ReleaseError(f"symlink in release tree: {relative}")
            if not stat.S_ISDIR(info.st_mode):
                raise ReleaseError(f"special directory entry: {relative}")
        for name in file_names:
            path = base / name
            relative = path.relative_to(root).as_posix()
            info = path.lstat()
            if name in IGNORED_DIRECTORIES:
                continue
            # Finder may recreate this file while the release directory is open.
            # It is never inventoried, checksummed, copied, or archived.
            if name == ".DS_Store":
                continue
            if name in EXCLUDED_NAMES or name.endswith((".pyc", ".pyo", ".tmp")):
                raise ReleaseError(f"excluded generated file present: {relative}")
            if relative == CHECKSUM_NAME:
                continue
            if not _safe_name(relative):
                raise ReleaseError(f"unsafe release path: {relative}")
            if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise ReleaseError(f"non-regular release file: {relative}")
            _validate_release_content(relative, path.read_bytes())
            files.append(relative)
    if len(files) != len(set(files)):
        raise ReleaseError("duplicate release path")
    return _sort_paths(files)


def _manifest_inventory(files: list[str]) -> list[str]:
    return [path for path in files if path != MANIFEST_NAME]


def _source_content_sha256(root: Path, paths: Iterable[str]) -> str:
    """Hash release source bytes without making the manifest self-referential."""

    digest = hashlib.sha256()
    for relative in _sort_paths(paths):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256(root / relative).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _manifest(files: list[str], source_content_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "standard_name": STANDARD_NAME,
        "standard_version": STANDARD_VERSION,
        "runtime": "python>=3.11; git>=2.39",
        "archive": "deterministic-zip-stored-v1",
        "source_content_sha256": source_content_sha256,
        "files": _manifest_inventory(files),
    }


def _manifest_bytes(data: dict[str, Any]) -> bytes:
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _load_manifest(root: Path) -> dict[str, Any]:
    try:
        data = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReleaseError("release manifest is missing or malformed") from error
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ReleaseError("release manifest identity is unsupported")
    required_identity = {
        "standard_name": STANDARD_NAME,
        "standard_version": STANDARD_VERSION,
        "runtime": "python>=3.11; git>=2.39",
        "archive": "deterministic-zip-stored-v1",
    }
    if any(data.get(key) != value for key, value in required_identity.items()):
        raise ReleaseError("release manifest identity is unsupported")
    files = data.get("files")
    if not isinstance(files, list) or not all(isinstance(item, str) for item in files):
        raise ReleaseError("release manifest file list is malformed")
    if files != _sort_paths(files) or len(files) != len(set(files)):
        raise ReleaseError("release manifest file list is not sorted and unique")
    if not files or any(not _safe_name(item) for item in files):
        raise ReleaseError("release manifest contains an unsafe file path")
    source_content_sha256 = data.get("source_content_sha256")
    if not isinstance(source_content_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", source_content_sha256
    ):
        raise ReleaseError("release manifest source content hash is malformed")
    return data


def _checksum_bytes(root: Path, paths: list[str]) -> bytes:
    lines = [f"{_sha256(root / relative)}  {relative}" for relative in paths]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _parse_checksums(text: str) -> dict[str, str]:
    if not text.endswith("\n") or "\n\n" in text:
        raise ReleaseError("SHA256SUMS has invalid line termination")
    checksums: dict[str, str] = {}
    for line in text.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None or not _safe_name(match.group(2)):
            raise ReleaseError("SHA256SUMS has invalid grammar")
        if match.group(2) == CHECKSUM_NAME or match.group(2) in checksums:
            raise ReleaseError("SHA256SUMS has a self-entry or duplicate")
        checksums[match.group(2)] = match.group(1)
    if list(checksums) != _sort_paths(checksums):
        raise ReleaseError("SHA256SUMS is not sorted")
    return checksums


def load_checksums(root: Path) -> dict[str, str]:
    try:
        text = (root / CHECKSUM_NAME).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ReleaseError("SHA256SUMS is missing or unreadable") from error
    return _parse_checksums(text)


def load_archive_checksums(archive_path: Path) -> dict[str, str]:
    """Read only the archive checksum inventory before safe extraction."""

    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            entries = [item for item in archive.infolist() if item.filename == CHECKSUM_NAME]
            if len(entries) != 1:
                raise ReleaseError("archive has no unique checksum inventory")
            entry = entries[0]
            if (
                entry.is_dir()
                or entry.compress_type != zipfile.ZIP_STORED
                or entry.compress_size != entry.file_size
                or entry.file_size > 4 * 1024 * 1024
                or entry.flag_bits & 0x1
            ):
                raise ReleaseError("archive checksum inventory has unsafe metadata")
            text = archive.read(entry).decode("utf-8")
    except (OSError, UnicodeError, zipfile.BadZipFile) as error:
        raise ReleaseError("archive checksum inventory is unreadable") from error
    return _parse_checksums(text)


def verify_checksums(root: Path) -> dict[str, str]:
    checksums = load_checksums(root)
    for relative, expected in checksums.items():
        path = root / relative
        if not path.is_file() or path.is_symlink() or _sha256(path) != expected:
            raise ReleaseError(f"checksum mismatch: {relative}")
    return checksums


def verify_source_content(root: Path, manifest: dict[str, Any] | None = None) -> str:
    """Verify the manifest's source content identity for its listed files."""

    loaded = manifest if manifest is not None else _load_manifest(root)
    actual = _source_content_sha256(root, loaded["files"])
    if actual != loaded["source_content_sha256"]:
        raise ReleaseError("release source content hash differs from its manifest")
    return actual


def _zip_mode(relative: str) -> int:
    return 0o755 if relative in EXECUTABLES else 0o644


def _write_zip(root: Path, output: Path, members: list[str]) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.comment = b""
        for relative in members:
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.flag_bits = 0x800
            info.extra = b""
            info.comment = b""
            info.external_attr = (stat.S_IFREG | _zip_mode(relative)) << 16
            archive.writestr(info, (root / relative).read_bytes())


def _validate_archive_handle(
    archive: zipfile.ZipFile, checksums: dict[str, str]
) -> None:
    expected = set(checksums) | {CHECKSUM_NAME}
    if archive.comment:
        raise ReleaseError("archive comment is not deterministic")
    names = [item.filename for item in archive.infolist()]
    if len(names) != len(set(names)) or set(names) != expected:
        raise ReleaseError("archive member table does not match checksums")
    if names != _sort_paths(names):
        raise ReleaseError("archive members are not sorted")
    total_size = 0
    for item in archive.infolist():
        if not _safe_name(item.filename) or item.is_dir():
            raise ReleaseError("archive contains unsafe member name")
        if item.compress_type != zipfile.ZIP_STORED or item.compress_size != item.file_size:
            raise ReleaseError("archive member is not stored-only")
        if item.file_size > 64 * 1024 * 1024:
            raise ReleaseError("archive member exceeds size limit")
        total_size += item.file_size
        if total_size > 256 * 1024 * 1024:
            raise ReleaseError("archive exceeds total size limit")
        if item.extra or item.comment or item.flag_bits & 0x1:
            raise ReleaseError("archive member has unsupported metadata")
        if (
            item.date_time != (1980, 1, 1, 0, 0, 0)
            or item.create_system != 3
            or item.flag_bits != 0
            or item.internal_attr != 0
        ):
            raise ReleaseError("archive member metadata is not deterministic")
        mode = (item.external_attr >> 16) & 0xFFFF
        if not stat.S_ISREG(mode) or stat.S_IMODE(mode) != _zip_mode(item.filename):
            raise ReleaseError("archive contains non-regular or wrong-mode member")
        content = archive.read(item)
        if item.filename in checksums and hashlib.sha256(content).hexdigest() != checksums[item.filename]:
            raise ReleaseError("archive checksum mismatch")
        if item.filename == CHECKSUM_NAME:
            expected_checksums = (
                "".join(
                    f"{checksums[name]}  {name}\n"
                    for name in _sort_paths(checksums)
                )
            ).encode("utf-8")
            if content != expected_checksums:
                raise ReleaseError("archive checksum inventory bytes differ")


def validate_archive(archive_path: Path, checksums: dict[str, str]) -> None:
    with zipfile.ZipFile(archive_path, "r") as archive:
        _validate_archive_handle(archive, checksums)


def _extract_directory_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _write_extracted_member(root_fd: int, relative: str, content: bytes, mode: int) -> None:
    parts = PurePosixPath(relative).parts
    current_fd = os.dup(root_fd)
    target_fd: int | None = None
    try:
        for component in parts[:-1]:
            try:
                os.mkdir(component, mode=0o755, dir_fd=current_fd)
            except FileExistsError:
                pass
            try:
                next_fd = os.open(
                    component, _extract_directory_flags(), dir_fd=current_fd
                )
            except OSError as error:
                raise ReleaseError("extraction parent is unsafe") from error
            os.close(current_fd)
            current_fd = next_fd
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        try:
            target_fd = os.open(parts[-1], flags, mode, dir_fd=current_fd)
        except OSError as error:
            raise ReleaseError("extraction target already exists or is unsafe") from error
        view = memoryview(content)
        while view:
            written = os.write(target_fd, view)
            view = view[written:]
        os.fchmod(target_fd, mode)
        os.fsync(target_fd)
        os.fsync(current_fd)
    finally:
        if target_fd is not None:
            os.close(target_fd)
        os.close(current_fd)


def _open_or_create_extraction_root(destination: Path) -> int:
    absolute = Path(os.path.abspath(destination))
    if len(absolute.parts) > 1 and absolute.parts[1] in {"var", "tmp"}:
        system_alias = Path(absolute.anchor) / absolute.parts[1]
        if system_alias.is_symlink():
            absolute = system_alias.resolve(strict=True).joinpath(*absolute.parts[2:])
    anchor = Path(absolute.anchor)
    current_fd = os.open(anchor, _extract_directory_flags())
    try:
        for component in absolute.parts[1:]:
            try:
                os.mkdir(component, mode=0o700, dir_fd=current_fd)
            except FileExistsError:
                pass
            try:
                next_fd = os.open(
                    component, _extract_directory_flags(), dir_fd=current_fd
                )
            except OSError as error:
                raise ReleaseError("extraction destination ancestor is unsafe") from error
            os.close(current_fd)
            current_fd = next_fd
        result = current_fd
        current_fd = -1
        return result
    finally:
        if current_fd >= 0:
            os.close(current_fd)


def safe_extract(archive_path: Path, destination: Path, checksums: dict[str, str]) -> None:
    _require_secure_extraction_support()
    with zipfile.ZipFile(archive_path, "r") as archive:
        _validate_archive_handle(archive, checksums)
        root_fd = _open_or_create_extraction_root(destination)
        try:
            for relative in _sort_paths(set(checksums) | {CHECKSUM_NAME}):
                _write_extracted_member(
                    root_fd, relative, archive.read(relative), _zip_mode(relative)
                )
        finally:
            os.close(root_fd)


def _require_secure_extraction_support() -> None:
    """Reject platforms whose filesystem primitives are not validated here."""

    required = (
        "O_NOFOLLOW",
        "O_DIRECTORY",
        "supports_dir_fd",
    )
    if os.name == "nt" or any(not hasattr(os, name) for name in required):
        raise ReleaseError(
            "secure archive extraction is unsupported on this platform"
        )
    dir_fd_functions = (os.open, os.mkdir)
    if not all(function in os.supports_dir_fd for function in dir_fd_functions):
        raise ReleaseError(
            "secure archive extraction is unsupported on this platform"
        )


def _stage_release(source_root: Path, staging_root: Path) -> dict[str, str]:
    """Create one verified bundle tree without modifying the source checkout."""

    source_files = _source_files(source_root)
    for relative in source_files:
        source = source_root / relative
        destination = staging_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination, follow_symlinks=False)

    source_content_sha256 = _source_content_sha256(staging_root, source_files)
    manifest = _manifest(source_files + [MANIFEST_NAME], source_content_sha256)
    (staging_root / MANIFEST_NAME).write_bytes(_manifest_bytes(manifest))
    inventory = inventory_release(staging_root)
    if manifest["files"] != _manifest_inventory(inventory):
        raise ReleaseError("staged release differs from its manifest")
    (staging_root / CHECKSUM_NAME).write_bytes(
        _checksum_bytes(staging_root, inventory)
    )
    checksums = verify_checksums(staging_root)
    verify_source_content(staging_root, manifest)
    if list(checksums) != inventory:
        raise ReleaseError("staged checksums differ from release inventory")
    return checksums


def build_release(release_root: Path, output_zip: Path, *, check: bool) -> dict[str, Any]:
    source_root = release_root.resolve(strict=True)
    if release_root.is_symlink():
        raise ReleaseError("release root must not be a symlink")

    with tempfile.TemporaryDirectory(prefix="cody-release-stage-") as directory:
        staging_root = Path(directory) / STANDARD_NAME
        staging_root.mkdir(mode=0o700)
        checksums = _stage_release(source_root, staging_root)
        source_content_sha256 = _load_manifest(staging_root)["source_content_sha256"]
        candidate = Path(directory) / f"{STANDARD_NAME}-{STANDARD_VERSION}.zip"
        _write_zip(
            staging_root,
            candidate,
            _sort_paths(set(checksums) | {CHECKSUM_NAME}),
        )
        validate_archive(candidate, checksums)

        if check:
            if not output_zip.is_file() or candidate.read_bytes() != output_zip.read_bytes():
                raise ReleaseError("deterministic archive differs from checked output")
            return {
                "ok": True,
                "changed": False,
                "standard_version": STANDARD_VERSION,
                "archive_sha256": _sha256(output_zip),
                "source_content_sha256": source_content_sha256,
                "file_count": len(checksums),
            }

        output_zip.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=f".{output_zip.name}.",
            suffix=".tmp",
            dir=output_zip.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
        try:
            shutil.copyfile(candidate, temporary)
            os.replace(temporary, output_zip)
        finally:
            temporary.unlink(missing_ok=True)

    return {
        "ok": True,
        "changed": True,
        "standard_version": STANDARD_VERSION,
        "archive_sha256": _sha256(output_zip),
        "source_content_sha256": source_content_sha256,
        "file_count": len(checksums),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or verify a deterministic coordinator release")
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        result = build_release(arguments.release_root, arguments.output, check=arguments.check)
    except ReleaseError as error:
        print(json.dumps({"ok": False, "changed": False, "error": redact_release_text(str(error))}, sort_keys=True))
        return 3
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
