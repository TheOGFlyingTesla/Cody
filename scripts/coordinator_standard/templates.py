"""Deterministic rendering for the thin repository coordinator contract."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from string import Template
from uuid import UUID

from . import SCHEMA_VERSION, STANDARD_NAME, STANDARD_VERSION
from .git_state import read_tracked_preimage
from .markers import parse_managed_block, upsert_managed_block
from .model import Blocker, CoordinatorError, Inspection, Operation, ReversalEvidence
from .safety import read_regular_file, sha256_bytes


SKILL_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = SKILL_ROOT / "assets/repo-template"
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_project_slug(value: str) -> str:
    if not 2 <= len(value) <= 63 or _SLUG.fullmatch(value) is None:
        raise CoordinatorError(
            Blocker(
                "invalid_project_slug",
                "The project slug must be 2-63 lowercase letters, digits, or single hyphens.",
                "Choose a slug such as project-one and retry.",
            )
        )
    return value


def derive_project_slug(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    normalized = re.sub(r"-+", "-", normalized)[:63].rstrip("-")
    return validate_project_slug(normalized)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        raise CoordinatorError(
            Blocker(
                "naive_timestamp",
                "Coordinator timestamps must include a timezone.",
                "Use a timezone-aware UTC timestamp.",
            )
        )
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_template(relative_path: str) -> Template:
    path = TEMPLATE_ROOT / relative_path
    return Template(path.read_text(encoding="utf-8"))


def render_standard_json(
    project_slug: str,
    project_id: UUID,
    installed_at: datetime,
    validated_at: datetime,
    risk_profiles: tuple[str, ...],
    migrations: tuple[dict[str, object], ...],
) -> bytes:
    validate_project_slug(project_slug)
    rendered = _load_template("docs/codex/STANDARD.json.tmpl").substitute(
        SCHEMA_VERSION=str(SCHEMA_VERSION),
        STANDARD_NAME=STANDARD_NAME,
        STANDARD_VERSION=STANDARD_VERSION,
        PROJECT_ID=str(project_id),
        PROJECT_SLUG=project_slug,
        INSTALLED_AT=_utc_text(installed_at),
        LAST_VALIDATED_AT=_utc_text(validated_at),
        RISK_PROFILES_JSON=json.dumps(list(risk_profiles), ensure_ascii=False),
        MIGRATIONS_JSON=json.dumps(list(migrations), ensure_ascii=False),
    )
    parsed = json.loads(rendered)
    return (json.dumps(parsed, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _command_markdown(inspection: Inspection) -> str:
    order = ("setup", "test", "lint", "typecheck", "build", "manual")
    lines: list[str] = []
    for category in order:
        for command in inspection.discovered_commands.get(category, ()):
            lines.append(f"- **{category}:** `{command}`")
    for category in sorted(set(inspection.discovered_commands) - set(order)):
        for command in inspection.discovered_commands[category]:
            lines.append(f"- **{category}:** `{command}`")
    return "\n".join(lines) if lines else "- Unknown — inspect before relying on this field."


def _operation(
    inspection: Inspection, relative_path: str, content: bytes, before: bytes | None
) -> Operation:
    if before is not None:
        before_hash = sha256_bytes(before)
        reversal = ReversalEvidence("unavailable", None)
        if relative_path == "AGENTS.md":
            prior_block = parse_managed_block(before)
            rendered_block = parse_managed_block(content)
            restored = None
            if prior_block is None and rendered_block is not None:
                candidate = content[: rendered_block.start] + content[rendered_block.end :]
                if sha256_bytes(candidate) == before_hash:
                    restored = candidate
                elif candidate.endswith(b"\n") and sha256_bytes(candidate[:-1]) == before_hash:
                    restored = candidate[:-1]
            if restored is not None:
                reversal = ReversalEvidence(
                    "remove-inserted-block",
                    None,
                    (("before_sha256", before_hash),),
                )
        if (
            reversal.kind == "unavailable"
            and inspection.git.head is not None
            and read_tracked_preimage(
                inspection.repo,
                inspection.git.head,
                relative_path,
                before_hash,
            )
            is not None
        ):
            reversal = ReversalEvidence(
                "restore-git-base",
                inspection.git.head,
                (("before_sha256", before_hash),),
            )
        action = "replace"
    else:
        before_hash = None
        reversal = ReversalEvidence("delete-new", None)
        action = "create"
    return Operation(
        action=action,
        relative_path=relative_path,
        before_sha256=before_hash,
        after_sha256=sha256_bytes(content),
        content=content,
        reversal=reversal,
    )


def render_new_project(
    inspection: Inspection,
    project_slug: str,
    now: datetime,
    project_id: UUID,
    *,
    risk_profiles: tuple[str, ...] = (),
    risk_rules: tuple[str, ...] = (),
) -> tuple[Operation, ...]:
    validate_project_slug(project_slug)
    if any(_SLUG.fullmatch(profile) is None for profile in risk_profiles):
        raise CoordinatorError(
            Blocker(
                "invalid_risk_profile",
                "A project risk profile identifier is malformed.",
                "Use lowercase hyphenated risk profile identifiers.",
            )
        )
    target_paths = (
        "AGENTS.md",
        "docs/codex/STANDARD.json",
        "docs/codex/PROJECT.md",
        "docs/codex/STATUS.md",
        "docs/codex/ROADMAP.md",
        "docs/codex/DECISIONS.md",
        "docs/codex/WORK_ITEMS/.gitkeep",
        "docs/codex/MIGRATIONS/.gitkeep",
    )
    snapshots = {
        relative: read_regular_file(inspection.repo, inspection.repo / relative)
        for relative in target_paths
    }
    timestamp = _utc_text(now)
    commands = _command_markdown(inspection)
    branch = inspection.git.branch or "detached or unborn"
    head = inspection.git.head or "unborn"
    risk_lines = [f"- Risk profile: `{profile}`" for profile in risk_profiles]
    risk_lines.extend(f"- {rule}" for rule in risk_rules if rule.strip())
    risk_text = (
        "\n".join(risk_lines)
        if risk_lines
        else "- No project-specific elevated risk profile was discovered."
    )
    substitutions = {
        "PROJECT_SLUG": project_slug,
        "STANDARD_VERSION": STANDARD_VERSION,
        "TIMESTAMP": timestamp,
        "VALIDATION_COMMANDS": commands,
        "BRANCH": branch,
        "HEAD": head,
        "RISK_RULES": risk_text,
    }
    agents_body = _load_template("AGENTS.managed.md").substitute(substitutions).encode(
        "utf-8"
    )
    existing_agents = snapshots["AGENTS.md"] or b""

    existing_standard_bytes = snapshots["docs/codex/STANDARD.json"]
    if existing_standard_bytes is not None:
        try:
            existing_standard = json.loads(existing_standard_bytes.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise CoordinatorError(
                Blocker(
                    "malformed_standard",
                    "The existing coordinator identity record is malformed.",
                    "Repair or explicitly supersede the record before setup.",
                    ("docs/codex/STANDARD.json",),
                )
            ) from error
        if not isinstance(existing_standard, dict) or (
            existing_standard.get("project_id") != str(project_id)
            or existing_standard.get("project_slug") != project_slug
        ):
            raise CoordinatorError(
                Blocker(
                    "project_identity_collision",
                    "The existing coordinator identity belongs to a different project identity.",
                    "Reconcile or explicitly supersede the conflicting identity before setup.",
                    ("docs/codex/STANDARD.json",),
                )
            )
    rendered: dict[str, bytes] = {
        "AGENTS.md": upsert_managed_block(existing_agents, agents_body),
        "docs/codex/STANDARD.json": render_standard_json(
            project_slug, project_id, now, now, risk_profiles, ()
        ),
        "docs/codex/PROJECT.md": _load_template("docs/codex/PROJECT.md.tmpl")
        .substitute(substitutions)
        .encode("utf-8"),
        "docs/codex/STATUS.md": _load_template("docs/codex/STATUS.md.tmpl")
        .substitute(substitutions)
        .encode("utf-8"),
        "docs/codex/ROADMAP.md": _load_template("docs/codex/ROADMAP.md.tmpl")
        .substitute(substitutions)
        .encode("utf-8"),
        "docs/codex/DECISIONS.md": _load_template("docs/codex/DECISIONS.md.tmpl")
        .substitute(substitutions)
        .encode("utf-8"),
        "docs/codex/WORK_ITEMS/.gitkeep": b"",
        "docs/codex/MIGRATIONS/.gitkeep": b"",
    }
    return tuple(
        _operation(inspection, path, content, snapshots[path])
        for path, content in rendered.items()
    )


__all__ = [
    "CoordinatorError",
    "derive_project_slug",
    "render_new_project",
    "render_standard_json",
    "validate_project_slug",
]
