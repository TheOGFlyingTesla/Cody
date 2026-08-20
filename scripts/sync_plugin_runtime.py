#!/usr/bin/env python3
"""Materialize or verify the Cody plugin's runtime skill mirror."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
from typing import Sequence

PLUGIN_SKILL_ROOT = "plugins/cody-codex-coordinator/skills/cody-coordinator"
PLUGIN_RUNTIME_PATHS = frozenset(
    {
        "SKILL.md",
        "VERSION",
        "agents/openai.yaml",
        "assets/repo-template/AGENTS.managed.md",
        "assets/repo-template/docs/codex/DECISIONS.md.tmpl",
        "assets/repo-template/docs/codex/PROJECT.md.tmpl",
        "assets/repo-template/docs/codex/ROADMAP.md.tmpl",
        "assets/repo-template/docs/codex/STANDARD.json.tmpl",
        "assets/repo-template/docs/codex/STATUS.md.tmpl",
        "assets/repo-template/docs/codex/WORK_ITEMS/WORK_ITEM_TEMPLATE.md.tmpl",
        "assets/schema/journal.schema.json",
        "assets/schema/dispatch-packet.schema.json",
        "assets/schema/standard.schema.json",
        "references/authority-matrix.md",
        "references/completion-report.md",
        "references/execution-efficiency.md",
        "references/model-routing-contract.json",
        "references/operating-model.md",
        "references/orchestration-policy.md",
        "references/repository-contract.md",
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
        "scripts/dispatch_packet.py",
        "scripts/routing_contract.py",
        "scripts/routing_live_eval.py",
    }
)


class PluginRuntimeError(RuntimeError):
    pass


def sync_plugin_runtime(source_root: Path, destination: Path, *, check: bool) -> list[str]:
    source_root = source_root.resolve(strict=True)
    expected = set(PLUGIN_RUNTIME_PATHS)

    if check:
        actual = (
            {
                path.relative_to(destination).as_posix()
                for path in destination.rglob("*")
                if path.is_file()
            }
            if destination.is_dir()
            else set()
        )
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise PluginRuntimeError(
                f"plugin runtime inventory differs (missing={missing}, extra={extra})"
            )

    changed: list[str] = []
    for relative in sorted(expected):
        source = source_root / relative
        target = destination / relative
        if not source.is_file():
            raise PluginRuntimeError(f"canonical runtime file is missing: {relative}")
        if target.is_file() and target.read_bytes() == source.read_bytes():
            continue
        if check:
            raise PluginRuntimeError(f"plugin runtime differs: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        changed.append(relative)

    if not check and destination.is_dir():
        for target in sorted(destination.rglob("*"), reverse=True):
            if target.is_file() and target.relative_to(destination).as_posix() not in expected:
                target.unlink()
            elif target.is_dir():
                try:
                    target.rmdir()
                except OSError:
                    pass
    return changed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Cody repository root",
    )
    arguments = parser.parse_args(argv)
    destination = arguments.repo / PLUGIN_SKILL_ROOT
    try:
        changed = sync_plugin_runtime(arguments.repo, destination, check=arguments.check)
    except (OSError, PluginRuntimeError) as error:
        print(f"plugin runtime: FAIL: {error}")
        return 1
    status = "current" if arguments.check or not changed else f"updated {len(changed)} files"
    print(f"plugin runtime: PASS ({status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
