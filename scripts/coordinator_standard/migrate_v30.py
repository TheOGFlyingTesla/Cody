"""Byte-preserving sequential coordinator 3.x migration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from uuid import UUID

from . import STANDARD_VERSION
from .markers import format_managed_block, parse_managed_block
from .model import Blocker, CoordinatorError, Inspection, Operation, ReversalEvidence
from .safety import read_regular_file, sha256_bytes
from .templates import render_standard_json, validate_project_slug
from .validator import strict_json_loads


LEGACY_VERSION = "3.0.0"
SUPPORTED_SOURCE_VERSIONS = (
    "3.0.0",
    "3.1.0",
    "3.2.0",
    "3.2.1",
    "3.2.2",
    "3.2.3",
    "3.2.4",
    "3.2.5",
    "3.2.6",
)
STATUS_GUIDANCE = (
    b"At meaningful state transitions, keep `docs/codex/STATUS.md` concise and current "
    b"so replacement coordinators can recover verified "
    b"project truth. Do not create heartbeat-only updates.\n\n"
)
VALIDATION_ANCHOR = b"Discovered validation entry points:"
RISK_ANCHOR = b"Project-specific exceptional risk rules:"
MANAGED_TEMPLATE = (
    Path(__file__).resolve().parents[2] / "assets/repo-template/AGENTS.managed.md"
)


@dataclass(frozen=True)
class MigrationPlan:
    source_version: str
    operations: tuple[Operation, ...]
    mapping_rows: tuple[tuple[str, str, str], ...]
    retained_sources: tuple[str, ...]
    warnings: tuple[str, ...]


def _replace_operation(inspection: Inspection, relative: str, content: bytes) -> Operation:
    before = read_regular_file(inspection.repo, inspection.repo / relative)
    if before is None:
        raise CoordinatorError(
            Blocker(
                "missing_v30_source",
                "A required Standard 3.0 coordinator file is missing.",
                "Restore the verified 3.0 coordinator file before upgrading.",
                (relative,),
            )
        )
    return Operation(
        action="replace",
        relative_path=relative,
        before_sha256=sha256_bytes(before),
        after_sha256=sha256_bytes(content),
        content=content,
        reversal=ReversalEvidence(
            "restore-git-base",
            inspection.git.head,
            (("before_sha256", sha256_bytes(before)),),
        ),
    )


def plan_v30_migration(inspection: Inspection, *, now: datetime) -> MigrationPlan:
    repo = inspection.repo
    standard_bytes = read_regular_file(repo, repo / "docs/codex/STANDARD.json")
    agents = read_regular_file(repo, repo / "AGENTS.md")
    if standard_bytes is None or agents is None:
        raise CoordinatorError(
            Blocker(
                "incomplete_v30_installation",
                "The Standard 3.0 installation is incomplete.",
                "Restore AGENTS.md and STANDARD.json before upgrading.",
            )
        )
    try:
        standard = strict_json_loads(standard_bytes)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CoordinatorError(
            Blocker(
                "malformed_v30_standard",
                "The Standard 3.0 installation record is malformed.",
                "Repair the verified identity record before upgrading.",
                ("docs/codex/STANDARD.json",),
            )
        ) from error
    source_version = standard.get("standard_version") if isinstance(standard, dict) else None
    if source_version not in SUPPORTED_SOURCE_VERSIONS:
        raise CoordinatorError(
            Blocker(
                "unsupported_standard_version",
                "The installed coordinator is not a supported sequential Standard 3.x source.",
                "Use a supported sequential migration.",
                ("docs/codex/STANDARD.json",),
            )
        )
    try:
        project_id = UUID(str(standard["project_id"]))
        project_slug = validate_project_slug(str(standard["project_slug"]))
        installed_at = datetime.fromisoformat(
            str(standard["installed_at"]).replace("Z", "+00:00")
        )
        risk_profiles = tuple(str(item) for item in standard.get("risk_profiles", ()))
        migrations = tuple(standard.get("migrations", ()))
    except (KeyError, TypeError, ValueError) as error:
        raise CoordinatorError(
            Blocker(
                "malformed_v30_standard",
                "The Standard 3.0 identity fields are invalid.",
                "Repair the verified identity record before upgrading.",
                ("docs/codex/STANDARD.json",),
            )
        ) from error

    block = parse_managed_block(agents)
    if block is None or block.version != source_version:
        raise CoordinatorError(
            Blocker(
                "invalid_v30_managed_block",
                "AGENTS.md does not contain one managed block matching the installed Standard version.",
                "Repair the managed block before upgrading.",
                ("AGENTS.md",),
            )
        )
    managed_body = agents[block.body_start : block.body_end]
    validation_anchor = managed_body.find(VALIDATION_ANCHOR)
    risk_anchor = managed_body.find(RISK_ANCHOR)
    if validation_anchor < 0 or risk_anchor < validation_anchor:
        raise CoordinatorError(
            Blocker(
                "invalid_v30_managed_block",
                "The Standard 3.x managed guidance is not safely recognizable.",
                "Restore the verified managed block before upgrading.",
                ("AGENTS.md",),
            )
        )
    validation_commands = managed_body[
        validation_anchor + len(VALIDATION_ANCHOR) : risk_anchor
    ].strip()
    risk_rules = managed_body[risk_anchor + len(RISK_ANCHOR) :].strip()
    managed_body = (
        MANAGED_TEMPLATE.read_bytes()
        .replace(b"$VALIDATION_COMMANDS", validation_commands)
        .replace(b"$RISK_RULES", risk_rules)
    )
    upgraded_agents = (
        agents[: block.start]
        + format_managed_block(managed_body, version=STANDARD_VERSION)
        + agents[block.end :]
    )
    upgraded_standard = render_standard_json(
        project_slug,
        project_id,
        installed_at,
        now,
        risk_profiles,
        migrations,
    )
    operations = (
        _replace_operation(inspection, "AGENTS.md", upgraded_agents),
        _replace_operation(inspection, "docs/codex/STANDARD.json", upgraded_standard),
    )
    return MigrationPlan(
        source_version=str(source_version),
        operations=operations,
        mapping_rows=(
            ("AGENTS.md", "AGENTS.md", "managed policy and marker updated; all bytes outside the managed block preserved"),
            (
                "docs/codex/STANDARD.json",
                "docs/codex/STANDARD.json",
                "identity preserved; sequential migration appended",
            ),
        ),
        retained_sources=(
            "docs/codex/PROJECT.md",
            "docs/codex/STATUS.md",
            "docs/codex/ROADMAP.md",
            "docs/codex/DECISIONS.md",
        ),
        warnings=(),
    )


__all__ = [
    "LEGACY_VERSION",
    "SUPPORTED_SOURCE_VERSIONS",
    "MigrationPlan",
    "plan_v30_migration",
]
