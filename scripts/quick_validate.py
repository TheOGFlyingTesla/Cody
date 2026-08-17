#!/usr/bin/env python3
"""Exercise the installable Cody skill from a deterministic release ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Sequence

import build_release


class QuickValidationError(RuntimeError):
    pass


def _pin_archive(source: Path, destination: Path) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as source_handle, destination.open("xb") as destination_handle:
        while chunk := source_handle.read(1024 * 1024):
            digest.update(chunk)
            destination_handle.write(chunk)
    return digest.hexdigest()


def _run_json(command: list[str], environment: dict[str, str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        check=False,
    )
    if completed.returncode != 0:
        raise QuickValidationError("archive-only validation command failed")
    try:
        payload = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise QuickValidationError("archive-only validation command returned invalid JSON") from error
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise QuickValidationError("archive-only validation command did not report success")
    return payload


def validate(
    *,
    release_root: Path | None,
    archive_path: Path | None,
    expected_sha256: str | None,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="cody-quick-validate-") as directory:
        temporary = Path(directory)
        if archive_path is None:
            if release_root is None:
                raise QuickValidationError("a release root or archive is required")
            source_root = release_root.resolve(strict=True)
            archive = temporary / "cody-coordinator.zip"
            build = build_release.build_release(source_root, archive, check=False)
        else:
            source_archive = archive_path.resolve(strict=True)
            archive = temporary / "pinned-candidate.zip"
            archive_sha256 = _pin_archive(source_archive, archive)
            if archive_sha256 != expected_sha256:
                raise QuickValidationError("candidate archive SHA-256 does not match")
            build = {"archive_sha256": archive_sha256}
        checksums = build_release.load_archive_checksums(archive)
        bundle = temporary / "bundle"
        build_release.safe_extract(archive, bundle, checksums)
        manifest = build_release._load_manifest(bundle)
        build_release.verify_source_content(bundle, manifest)
        build["source_content_sha256"] = manifest["source_content_sha256"]

        user_home = temporary / "user-home"
        user_home.mkdir(mode=0o700)
        environment = {
            **os.environ,
            "HOME": str(user_home),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        installer = bundle / "scripts/install_skill.py"
        installer_base = ["python3", str(installer), "--release-root", str(bundle)]
        preview = _run_json([*installer_base, "--check"], environment)
        if preview.get("action") != "install-planned" or preview.get("installation_scope") != "user-agents-home":
            raise QuickValidationError("archive installer did not produce the expected user-scoped plan")
        installed = _run_json(installer_base, environment)
        if installed.get("action") != "installed":
            raise QuickValidationError("archive installer did not install the skill")
        discovery = _run_json([*installer_base, "--verify-discovery"], environment)
        if discovery.get("action") != "discovery-path-verified":
            raise QuickValidationError("archive installer did not verify the skill discovery path")

        stable_skill = user_home / ".agents/skills/cody-coordinator"
        if not stable_skill.is_symlink() or not (stable_skill / "SKILL.md").is_file():
            raise QuickValidationError("installed skill is not discoverable at the verified stable path")

        project = temporary / "project"
        project.mkdir(mode=0o700)
        initialized = subprocess.run(
            ["git", "init", "--quiet", "--initial-branch=main", str(project)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=environment,
        )
        if initialized.returncode != 0:
            raise QuickValidationError("temporary validation repository could not be initialized")
        inspection = _run_json(
            [
                "python3",
                str(stable_skill.resolve(strict=True) / "scripts/coordinator_standard.py"),
                "--repo",
                str(project),
                "--format",
                "json",
                "inspect",
            ],
            environment,
        )
        if inspection.get("command") != "inspect":
            raise QuickValidationError("installed skill inspection did not run")
        return {
            "ok": True,
            "action": "archive-only-quick-validation-passed",
            "archive_sha256": build["archive_sha256"],
            "source_content_sha256": build["source_content_sha256"],
        }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an installed Cody skill from its release ZIP")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--release-root", type=Path)
    source.add_argument("--archive", type=Path)
    parser.add_argument("--expected-sha256")
    arguments = parser.parse_args(argv)
    try:
        if arguments.archive is not None and arguments.expected_sha256 is None:
            raise QuickValidationError("--archive requires --expected-sha256")
        if arguments.expected_sha256 is not None and (
            arguments.archive is None
            or not re.fullmatch(r"[0-9a-f]{64}", arguments.expected_sha256)
        ):
            raise QuickValidationError("--expected-sha256 requires --archive and 64 lowercase hex characters")
        result = validate(
            release_root=arguments.release_root,
            archive_path=arguments.archive,
            expected_sha256=arguments.expected_sha256,
        )
    except (OSError, build_release.ReleaseError, QuickValidationError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
