"""Read-only repository and coordinator-installation discovery."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shlex
import tomllib

from . import SCHEMA_VERSION, STANDARD_NAME
from .git_state import inspect_git
from .model import Blocker, Inspection


def _discover_instructions(repo: Path) -> tuple[str, ...]:
    instructions: list[str] = []
    root_agents = repo / "AGENTS.md"
    if root_agents.is_file() and not root_agents.is_symlink():
        instructions.append("AGENTS.md")
    return tuple(instructions)


def _discover_package_json(repo: Path, warnings: list[str]) -> dict[str, tuple[str, ...]]:
    path = repo / "package.json"
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        warnings.append("package.json is malformed; JavaScript commands were not inferred.")
        return {}
    scripts = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(scripts, dict):
        scripts = {}
    commands: dict[str, tuple[str, ...]] = {}
    if (repo / "pnpm-lock.yaml").is_file():
        runner = "pnpm"
        setup = "pnpm install --frozen-lockfile"
    elif (repo / "yarn.lock").is_file():
        runner = "yarn"
        setup = "yarn install --frozen-lockfile"
    else:
        runner = "npm"
        setup = "npm ci" if (repo / "package-lock.json").is_file() else "npm install"
    commands["setup"] = (setup,)
    names = {
        "test": "test",
        "lint": "lint",
        "typecheck": "typecheck",
        "build": "build",
    }
    for category, script_name in names.items():
        if script_name not in scripts:
            continue
        if runner == "npm" and script_name == "test":
            command = "npm test"
        elif runner == "yarn":
            command = f"yarn {script_name}"
        else:
            command = f"{runner} run {script_name}"
        commands[category] = (command,)
    return commands


def _discover_pyproject(repo: Path, warnings: list[str]) -> dict[str, tuple[str, ...]]:
    path = repo / "pyproject.toml"
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        warnings.append("pyproject.toml is malformed; Python commands were not inferred.")
        return {}
    tool = data.get("tool", {}) if isinstance(data, dict) else {}
    commands: dict[str, tuple[str, ...]] = {}
    if (repo / "requirements.txt").is_file():
        commands["setup"] = ("python3 -m pip install -r requirements.txt",)
    if "pytest" in tool or (repo / "tests").is_dir():
        commands["test"] = ("python3 -m pytest",)
    if "ruff" in tool:
        commands["lint"] = ("python3 -m ruff check .",)
    if "mypy" in tool:
        commands["typecheck"] = ("python3 -m mypy .",)
    if "build-system" in data:
        commands["build"] = ("python3 -m build",)
    return commands


def _discover_makefile(repo: Path) -> dict[str, tuple[str, ...]]:
    path = repo / "Makefile"
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {}
    targets = set(re.findall(r"(?m)^([A-Za-z0-9_.-]+)\s*:(?!=)", text))
    return {
        category: (f"make {category}",)
        for category in ("test", "lint", "typecheck", "build")
        if category in targets
    }


def _discover_swift(repo: Path) -> dict[str, tuple[str, ...]]:
    commands: dict[str, list[str]] = {}
    if (repo / "Package.swift").is_file() and not (repo / "Package.swift").is_symlink():
        commands.setdefault("setup", []).append("swift package resolve")
        commands.setdefault("test", []).append("swift test")
        commands.setdefault("build", []).append("swift build")
    containers = [
        *sorted(repo.glob("*.xcworkspace")),
        *sorted(repo.glob("*.xcodeproj")),
    ]
    for container in containers:
        if container.is_symlink() or not container.is_dir():
            continue
        schemes = sorted(
            (container / "xcshareddata/xcschemes").glob("*.xcscheme")
        )
        for scheme in schemes:
            if scheme.is_symlink() or not scheme.is_file():
                continue
            selector = "-workspace" if container.suffix == ".xcworkspace" else "-project"
            command = (
                f"xcodebuild {selector} {shlex.quote(container.name)} "
                f"-scheme {shlex.quote(scheme.stem)} test"
            )
            commands.setdefault("test", []).append(command)
        if schemes:
            break
    return {key: tuple(value) for key, value in commands.items()}


def _merge_commands(*sources: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    merged: dict[str, list[str]] = {}
    for source in sources:
        for category, commands in source.items():
            bucket = merged.setdefault(category, [])
            for command in commands:
                if command not in bucket:
                    bucket.append(command)
    return {category: tuple(commands) for category, commands in sorted(merged.items())}


def _installed_version(repo: Path) -> tuple[str | None, list[Blocker]]:
    path = repo / "docs/codex/STANDARD.json"
    if not path.exists():
        return None, []
    if not path.is_file() or path.is_symlink():
        return None, [
            Blocker(
                "unsafe_standard_path",
                "docs/codex/STANDARD.json is not a regular file.",
                "Replace it with a regular repository file and retry.",
                ("docs/codex/STANDARD.json",),
            )
        ]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, [
            Blocker(
                "malformed_standard",
                "docs/codex/STANDARD.json is not valid UTF-8 JSON.",
                "Repair the installation record before initialization or upgrade.",
                ("docs/codex/STANDARD.json",),
            )
        ]
    if not isinstance(data, dict):
        return None, [
            Blocker(
                "malformed_standard",
                "docs/codex/STANDARD.json must contain one JSON object.",
                "Repair the installation record before initialization or upgrade.",
                ("docs/codex/STANDARD.json",),
            )
        ]
    if data.get("schema_version") != SCHEMA_VERSION or data.get("standard_name") != STANDARD_NAME:
        return None, [
            Blocker(
                "unsupported_standard_identity",
                "The coordinator installation record has an unsupported identity or schema.",
                "Use a supported sequential migration or repair the record explicitly.",
                ("docs/codex/STANDARD.json",),
            )
        ]
    version = data.get("standard_version")
    if not isinstance(version, str):
        return None, [
            Blocker(
                "malformed_standard",
                "The coordinator installation record has no string standard version.",
                "Repair the installation record before initialization or upgrade.",
                ("docs/codex/STANDARD.json",),
            )
        ]
    return version, []


def inspect_repository(repo: Path) -> Inspection:
    repo = repo.resolve(strict=True)
    git = inspect_git(repo)
    warnings: list[str] = []
    version, blockers = _installed_version(repo)
    commands = _merge_commands(
        _discover_package_json(repo, warnings),
        _discover_pyproject(repo, warnings),
        _discover_makefile(repo),
        _discover_swift(repo),
    )
    return Inspection(
        repo=repo,
        git=git,
        applicable_instructions=_discover_instructions(repo),
        installed_version=version,
        discovered_commands=commands,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
    )


__all__ = ["inspect_repository"]
