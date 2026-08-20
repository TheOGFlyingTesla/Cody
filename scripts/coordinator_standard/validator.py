"""Dependency-free validation for Coordinator Standard repositories."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Mapping
from uuid import UUID

from . import STANDARD_VERSION
from .inspector import inspect_repository
from .markers import parse_managed_block
from .model import CoordinatorError, ValidationCheck
from .safety import contains_credential, read_regular_file, sha256_bytes


_SKILL_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_DIR = _SKILL_ROOT / "assets/schema"
_REQUIRED_PATHS = (
    "AGENTS.md",
    "docs/codex/STANDARD.json",
    "docs/codex/PROJECT.md",
    "docs/codex/STATUS.md",
    "docs/codex/ROADMAP.md",
    "docs/codex/DECISIONS.md",
)
_REQUIRED_SECTIONS: dict[str, tuple[str, ...]] = {
    "PROJECT.md": (
        "Purpose",
        "Current product shape",
        "Repository map",
        "Technology and runtime",
        "Validation commands",
        "Generated files and ownership boundaries",
        "Deployment shape",
        "Authority and risk",
        "External systems",
        "Unknowns",
    ),
    "ROADMAP.md": ("Now", "Next", "Later", "Parked"),
    "DECISIONS.md": ("Decisions",),
}
_SCHEMA_KEYWORDS = {
    "$schema",
    "$id",
    "$defs",
    "$ref",
    "title",
    "description",
    "type",
    "const",
    "enum",
    "required",
    "properties",
    "additionalProperties",
    "items",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minLength",
    "maxLength",
    "pattern",
    "format",
}
_PLACEHOLDER = re.compile(r"(?:\$PROJECT_|\$STANDARD_|<PROJECT|\{\{[^}]+\}\})")
_POSIX_ABSOLUTE = re.compile(
    r"(?<![:/A-Za-z0-9._-])/(?:[A-Za-z0-9._~-]+/)+(?:[A-Za-z0-9._~-]+)?"
)
_WINDOWS_ABSOLUTE = re.compile(r"(?i)(?:\b[A-Z]:\\|\\\\[^\\\s]+\\)")
_STATUS_MAX_APPROX_TOKENS = 2_000
_STATUS_CURRENT_SECTIONS = (
    "Current exact identity and deploy truth",
    "Active task IDs",
    "Open P0/P1",
    "Authority or decision blocker",
    "One next action",
)
_STATUS_LEGACY_SECTIONS = (
    "Current outcome",
    "Last verified completed milestone",
    "Active or possibly active work",
    "Blockers",
    "Pending project owner decisions or approvals",
    "Known risks",
    "Recommended next action",
    "Confidence and unknowns",
)
_JOURNAL_NAME = re.compile(
    r"^(?P<stamp>[0-9]{8}T[0-9]{6}Z)-"
    r"(?P<run>[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})"
    r"\.journal\.json$"
)


class DuplicateJsonKey(ValueError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKey("duplicate JSON object key")
        result[key] = value
    return result


def strict_json_loads(value: str | bytes) -> Any:
    """Decode JSON while rejecting duplicate object keys."""

    return json.loads(value, object_pairs_hook=_strict_object)


def _check(name: str, ok: bool, severity: str, message: str) -> ValidationCheck:
    return ValidationCheck(name=name, ok=ok, severity=severity, message=message)


def _load_schema(name: str) -> dict[str, Any]:
    data = strict_json_loads((_SCHEMA_DIR / name).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("schema root must be an object")
    return data


def _schema_subset_errors(schema: Any, location: str = "$") -> list[str]:
    errors: list[str] = []
    if not isinstance(schema, dict):
        return [f"{location}: schema must be an object"]
    unsupported = sorted(set(schema) - _SCHEMA_KEYWORDS)
    if unsupported:
        errors.append(f"{location}: unsupported keyword")
    properties = schema.get("properties", {})
    if isinstance(properties, dict):
        for name, child in properties.items():
            errors.extend(_schema_subset_errors(child, f"{location}.properties.{name}"))
    definitions = schema.get("$defs", {})
    if isinstance(definitions, dict):
        for name, child in definitions.items():
            errors.extend(_schema_subset_errors(child, f"{location}.$defs.{name}"))
    if "items" in schema:
        errors.extend(_schema_subset_errors(schema["items"], f"{location}.items"))
    pattern = schema.get("pattern")
    if isinstance(pattern, str):
        try:
            re.compile(pattern)
        except re.error:
            errors.append(f"{location}: invalid pattern")
    format_name = schema.get("format")
    if format_name is not None and format_name not in {"uuid", "date-time"}:
        errors.append(f"{location}: unsupported format")
    reference = schema.get("$ref")
    if reference is not None and (
        not isinstance(reference, str) or not reference.startswith("#/$defs/")
    ):
        errors.append(f"{location}: unsupported reference")
    return errors


def _resolve_reference(root: dict[str, Any], reference: str) -> dict[str, Any] | None:
    current: Any = root
    for raw in reference[2:].split("/"):
        component = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or component not in current:
            return None
        current = current[component]
    return current if isinstance(current, dict) else None


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return False


def _format_ok(value: str, format_name: str) -> bool:
    if format_name == "uuid":
        try:
            UUID(value)
            return True
        except ValueError:
            return False
    if format_name == "date-time":
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.tzinfo is not None
        except ValueError:
            return False
    return False


def _validate_instance(
    value: Any,
    schema: dict[str, Any],
    root: dict[str, Any],
    location: str,
    errors: list[str],
    depth: int = 0,
) -> None:
    if depth > 100:
        errors.append(f"{location}: schema reference depth exceeded")
        return
    reference = schema.get("$ref")
    if isinstance(reference, str):
        resolved = _resolve_reference(root, reference)
        if resolved is None:
            errors.append(f"{location}: unresolved reference")
            return
        _validate_instance(value, resolved, root, location, errors, depth + 1)

    expected = schema.get("type")
    if expected is not None:
        options = expected if isinstance(expected, list) else [expected]
        if not options or not all(isinstance(item, str) for item in options):
            errors.append(f"{location}: invalid schema type")
            return
        if not any(_matches_type(value, item) for item in options):
            errors.append(f"{location}: wrong type")
            return
    if "const" in schema and value != schema["const"]:
        errors.append(f"{location}: const mismatch")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{location}: enum mismatch")

    if isinstance(value, dict):
        required = schema.get("required", [])
        if isinstance(required, list):
            for name in required:
                if name not in value:
                    errors.append(f"{location}: missing property")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for name, child in properties.items():
                if name in value and isinstance(child, dict):
                    _validate_instance(
                        value[name], child, root, f"{location}.{name}", errors, depth + 1
                    )
            if schema.get("additionalProperties") is False:
                if set(value) - set(properties):
                    errors.append(f"{location}: additional property")
    if isinstance(value, list):
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
            errors.append(f"{location}: too few items")
        if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
            errors.append(f"{location}: too many items")
        if schema.get("uniqueItems") is True:
            rendered = [
                json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                for item in value
            ]
            if len(rendered) != len(set(rendered)):
                errors.append(f"{location}: duplicate items")
        items = schema.get("items")
        if isinstance(items, dict):
            for index, item in enumerate(value):
                _validate_instance(
                    item, items, root, f"{location}[{index}]", errors, depth + 1
                )
    if isinstance(value, str):
        minimum = schema.get("minLength")
        maximum = schema.get("maxLength")
        if isinstance(minimum, int) and len(value) < minimum:
            errors.append(f"{location}: string too short")
        if isinstance(maximum, int) and len(value) > maximum:
            errors.append(f"{location}: string too long")
        pattern = schema.get("pattern")
        if isinstance(pattern, str):
            try:
                if re.search(pattern, value) is None:
                    errors.append(f"{location}: pattern mismatch")
            except re.error:
                errors.append(f"{location}: invalid pattern")
        format_name = schema.get("format")
        if isinstance(format_name, str) and not _format_ok(value, format_name):
            errors.append(f"{location}: format mismatch")


def validate_json(instance: Any, schema: dict[str, Any]) -> tuple[str, ...]:
    """Validate JSON using the release's documented schema subset."""

    subset_errors = _schema_subset_errors(schema)
    if subset_errors:
        return tuple(subset_errors)
    errors: list[str] = []
    _validate_instance(instance, schema, schema, "$", errors)
    return tuple(errors)


def validate_schema_document(instance: Any, schema_name: str) -> tuple[str, ...]:
    if schema_name not in {
        "standard.schema.json",
        "journal.schema.json",
        "dispatch-packet.schema.json",
    }:
        return ("unsupported bundled schema",)
    try:
        return validate_json(instance, _load_schema(schema_name))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return ("bundled schema unavailable",)


def _safe_relative(value: str) -> bool:
    if not value or "\\" in value or value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        return False
    path = PurePosixPath(value)
    return path.as_posix() == value and ".." not in path.parts and "." not in path.parts


def _managed_operation_path(relative: str, action: str) -> bool:
    fixed = {
        "AGENTS.md",
        "docs/codex/STANDARD.json",
        "docs/codex/PROJECT.md",
        "docs/codex/STATUS.md",
        "docs/codex/ROADMAP.md",
        "docs/codex/DECISIONS.md",
        "docs/codex/WORK_ITEMS/.gitkeep",
        "docs/codex/MIGRATIONS/.gitkeep",
    }
    if relative in fixed:
        return True
    if action == "replace" and re.fullmatch(
        r"\.agents/skills/[a-z0-9][a-z0-9-]{0,63}/SKILL\.md", relative
    ):
        return True
    if action == "git-init" and relative == ".git":
        return True
    return bool(
        re.fullmatch(
            r"docs/codex/MIGRATIONS/[0-9]{8}T[0-9]{6}Z-"
            r"[0-9a-f-]{36}\.report\.md",
            relative,
        )
    )


def _personal_or_absolute(text: str) -> bool:
    return bool(
        _POSIX_ABSOLUTE.search(text)
        or _WINDOWS_ABSOLUTE.search(text)
        or "/Users/" in text
        or "/Volumes/" in text
    )


def _managed_symlinks(repo: Path) -> tuple[str, ...]:
    roots = (repo / "AGENTS.md", repo / "docs/codex")
    found: list[str] = []
    for root in roots:
        try:
            root_info = root.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(root_info.st_mode):
            found.append(root.relative_to(repo).as_posix())
            continue
        if not stat.S_ISDIR(root_info.st_mode):
            continue
        for directory, directory_names, file_names in os.walk(root, followlinks=False):
            base = Path(directory)
            for name in tuple(directory_names) + tuple(file_names):
                path = base / name
                try:
                    if stat.S_ISLNK(path.lstat().st_mode):
                        found.append(path.relative_to(repo).as_posix())
                except FileNotFoundError:
                    found.append(path.relative_to(repo).as_posix())
    return tuple(sorted(set(found)))


def _plain_checks(checks: list[ValidationCheck]) -> tuple[ValidationCheck, ...]:
    return tuple(checks)


def validate_repository(
    repo: Path,
    *,
    candidate_overlay: Mapping[str, bytes] | None = None,
) -> tuple[ValidationCheck, ...]:
    """Validate the current repository contract or an in-memory candidate overlay."""

    repo = repo.resolve(strict=True)
    overlay = dict(candidate_overlay or {})
    checks: list[ValidationCheck] = []

    overlay_paths_ok = all(
        isinstance(path, str)
        and _safe_relative(path)
        and isinstance(content, bytes)
        for path, content in overlay.items()
    )
    try:
        inspection = inspect_repository(repo)
        symlinks = _managed_symlinks(repo)
        repository_safe = not inspection.blockers and not symlinks and overlay_paths_ok
    except (CoordinatorError, OSError):
        inspection = None
        repository_safe = False
    checks.append(
        _check(
            "repository-safety",
            repository_safe,
            "P0",
            "Repository and managed paths are safe regular locations.",
        )
    )

    schemas: dict[str, dict[str, Any]] = {}
    subset_ok = True
    try:
        schemas = {
            "standard": _load_schema("standard.schema.json"),
            "journal": _load_schema("journal.schema.json"),
            "dispatch-packet": _load_schema("dispatch-packet.schema.json"),
        }
        subset_ok = not any(_schema_subset_errors(item) for item in schemas.values())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        subset_ok = False
    checks.append(
        _check(
            "supported-schema-subset",
            subset_ok,
            "P1",
            "Bundled schemas use only the documented dependency-free subset.",
        )
    )

    def content(relative: str) -> bytes | None:
        if relative in overlay:
            return overlay[relative]
        limit = (
            4 * 1024 * 1024
            if relative.startswith("docs/codex/MIGRATIONS/")
            and relative.endswith(".journal.json")
            else 64 * 1024 * 1024
        )
        return read_regular_file(repo, repo / relative, max_bytes=limit)

    standard_data: dict[str, Any] | None = None
    standard_bytes: bytes | None = None
    try:
        standard_bytes = content("docs/codex/STANDARD.json")
        parsed = strict_json_loads(standard_bytes) if standard_bytes is not None else None
        standard_data = parsed if isinstance(parsed, dict) else None
        standard_ok = (
            subset_ok
            and standard_data is not None
            and not validate_json(standard_data, schemas["standard"])
        )
    except (CoordinatorError, UnicodeError, json.JSONDecodeError, DuplicateJsonKey):
        standard_ok = False
    checks.append(
        _check(
            "standard-schema",
            standard_ok,
            "P1",
            "STANDARD.json matches the bundled identity schema.",
        )
    )

    agents: bytes | None = None
    managed_block = None
    try:
        agents = content("AGENTS.md")
        managed_block = parse_managed_block(agents or b"")
        marker_ok = managed_block is not None and managed_block.version == STANDARD_VERSION
    except (CoordinatorError, UnicodeError):
        marker_ok = False
    checks.append(
        _check(
            "managed-marker-integrity",
            marker_ok,
            "P1",
            "AGENTS.md contains one current, well-formed managed block.",
        )
    )

    managed_contents: dict[str, bytes | None] = {}
    for relative in _REQUIRED_PATHS:
        try:
            managed_contents[relative] = content(relative)
            present = managed_contents[relative] is not None
        except CoordinatorError:
            managed_contents[relative] = None
            present = False
        checks.append(
            _check(
                f"required-path:{relative}",
                present,
                "P1",
                f"Required coordinator path {relative} is present and regular.",
            )
        )

    for filename, headings in _REQUIRED_SECTIONS.items():
        relative = f"docs/codex/{filename}"
        raw = managed_contents.get(relative)
        try:
            text_value = raw.decode("utf-8") if raw is not None else ""
            found = set(re.findall(r"(?m)^##\s+(.+?)\s*$", text_value))
            sections_ok = all(heading in found for heading in headings)
        except UnicodeDecodeError:
            sections_ok = False
        checks.append(
            _check(
                f"required-sections:{filename}",
                sections_ok,
                "P1",
                f"{filename} contains every required durable section.",
            )
        )

    status_raw = managed_contents.get("docs/codex/STATUS.md")
    try:
        status_text = status_raw.decode("utf-8") if status_raw is not None else ""
        status_headings = set(re.findall(r"(?m)^##\s+(.+?)\s*$", status_text))
        current_status_contract = all(
            heading in status_headings for heading in _STATUS_CURRENT_SECTIONS
        )
        legacy_status_contract = all(
            heading in status_headings for heading in _STATUS_LEGACY_SECTIONS
        )
        status_sections_ok = current_status_contract or legacy_status_contract
        status_compact = legacy_status_contract or (
            (len(status_raw or b"") + 3) // 4 <= _STATUS_MAX_APPROX_TOKENS
        )
    except UnicodeDecodeError:
        status_sections_ok = False
        status_compact = False
    checks.append(
        _check(
            "required-sections:STATUS.md",
            status_sections_ok,
            "P1",
            "STATUS.md contains the current compact contract or the preserved 3.1 contract.",
        )
    )
    checks.append(
        _check(
            "status-compactness",
            status_compact,
            "P1",
            "STATUS.md stays at or below the approximate 2,000-token recovery target.",
        )
    )

    scan_paths = tuple(path for path in _REQUIRED_PATHS if path != "AGENTS.md") + (
        "AGENTS.md",
    )
    decoded: dict[str, str] = {}
    for relative in scan_paths:
        raw = managed_contents.get(relative)
        try:
            decoded[relative] = raw.decode("utf-8") if raw is not None else ""
            contract_text = decoded[relative]
            if relative == "AGENTS.md" and agents is not None and managed_block is not None:
                contract_text = agents[managed_block.start : managed_block.end].decode("utf-8")
            placeholder_ok = not _PLACEHOLDER.search(contract_text)
            path_ok = not _personal_or_absolute(contract_text)
        except UnicodeDecodeError:
            decoded[relative] = ""
            placeholder_ok = False
            path_ok = False
        label = Path(relative).name
        scope = "managed coordinator block in AGENTS.md" if relative == "AGENTS.md" else label
        checks.append(
            _check(
                f"template-placeholders:{label}",
                placeholder_ok,
                "P1",
                f"The {scope} has no unresolved template placeholders.",
            )
        )
        checks.append(
            _check(
                f"personal-or-absolute-path:{label}",
                path_ok,
                "P1",
                f"The {scope} has no serialized personal or absolute filesystem path.",
            )
        )

    for relative in scan_paths:
        text_value = decoded.get(relative, "")
        label = Path(relative).name
        checks.append(
            _check(
                f"credential-content:{label}",
                not contains_credential(text_value),
                "P0",
                f"Credential-shape scan completed for {label}.",
            )
        )

    migrations_dir = repo / "docs/codex/MIGRATIONS"
    journal_path_set = {
        path
        for path in (
            migrations_dir.glob("*.journal.json")
            if migrations_dir.is_dir() and not migrations_dir.is_symlink()
            else ()
        )
    }
    journal_path_set.update(
        repo / relative
        for relative in overlay
        if re.fullmatch(
            r"docs/codex/MIGRATIONS/[A-Za-z0-9._-]+\.journal\.json",
            relative,
        )
    )
    journal_paths = tuple(sorted(journal_path_set))
    parsed_journals: list[tuple[Path, dict[str, Any]]] = []
    for path in journal_paths:
        safe_journal_name = (
            path.name
            if not contains_credential(path.name)
            else "[credential-bearing-journal-name-redacted]"
        )
        schema_ok = False
        journal_data: dict[str, Any] | None = None
        raw: bytes | None = None
        try:
            relative_journal = path.relative_to(repo).as_posix()
            raw = content(relative_journal)
            parsed = strict_json_loads(raw) if raw is not None else None
            journal_data = parsed if isinstance(parsed, dict) else None
            schema_ok = (
                subset_ok
                and journal_data is not None
                and not validate_json(journal_data, schemas["journal"])
            )
        except (CoordinatorError, UnicodeError, json.JSONDecodeError, DuplicateJsonKey):
            schema_ok = False
        checks.append(
            _check(
                f"journal-schema:{safe_journal_name}",
                schema_ok,
                "P1",
                f"Journal {safe_journal_name} matches the bundled run schema.",
            )
        )
        if raw is not None:
            try:
                journal_text = raw.decode("utf-8")
            except UnicodeDecodeError:
                journal_text = ""
            checks.append(
                _check(
                    f"journal-sensitive-content:{safe_journal_name}",
                    bool(journal_text)
                    and not contains_credential(journal_text)
                    and not _personal_or_absolute(journal_text),
                    "P0",
                    f"Journal {safe_journal_name} contains no sensitive or absolute path evidence.",
                )
            )
        if schema_ok and journal_data is not None:
            parsed_journals.append((path, journal_data))

    journal_consistent = True
    managed_scope_ok = True
    complete_run_ids: set[str] = set()
    for path, data in parsed_journals:
        name_match = _JOURNAL_NAME.fullmatch(path.name)
        run_id = data.get("run_id")
        canonical_report = (
            f"docs/codex/MIGRATIONS/{name_match.group('stamp')}-{run_id}.report.md"
            if name_match is not None and isinstance(run_id, str)
            else ""
        )
        phases = [
            entry.get("phase")
            for entry in data.get("phase_history", [])
            if isinstance(entry, dict)
        ]
        allowed_prefix = ["inspect", "plan", "apply", "validate", "finalize"][: len(phases)]
        operations = data.get("planned_operations", [])
        allowed_paths = data.get("authority", {}).get("allowed_paths", [])
        operation_paths = [
            item.get("relative_path")
            for item in operations
            if isinstance(item, dict)
        ]
        receipt_paths = [
            item.get("relative_path")
            for item in data.get("file_hashes", [])
            if isinstance(item, dict)
        ]
        scope_for_run = (
            data.get("command") == data.get("authority", {}).get("command")
            and set(operation_paths).issubset(set(allowed_paths))
            and all(
                isinstance(item, dict)
                and isinstance(item.get("relative_path"), str)
                and _managed_operation_path(item["relative_path"], item.get("action", ""))
                for item in operations
            )
            and set(receipt_paths).issubset(set(operation_paths))
        )
        managed_scope_ok = managed_scope_ok and scope_for_run
        run_ok = (
            name_match is not None
            and name_match.group("run") == run_id
            and data.get("report_path") == canonical_report
            and phases == allowed_prefix
        )
        if data.get("status") == "complete":
            complete_run_ids.add(run_id)
            report_bytes = None
            try:
                report_bytes = content(canonical_report) if canonical_report else None
            except CoordinatorError:
                report_bytes = None
            validations = data.get("validation", [])
            run_ok = run_ok and (
                phases == ["inspect", "plan", "apply", "validate", "finalize"]
                and bool(validations)
                and all(isinstance(item, dict) and item.get("ok") is True for item in validations)
                and isinstance(data.get("report_sha256"), str)
                and report_bytes is not None
                and sha256_bytes(report_bytes) == data.get("report_sha256")
                and set(operation_paths) - {".git"} == set(receipt_paths)
            )
        elif data.get("status") == "superseded":
            report_bytes = None
            try:
                report_bytes = content(canonical_report) if canonical_report else None
            except CoordinatorError:
                report_bytes = None
            run_ok = run_ok and (
                isinstance(data.get("report_sha256"), str)
                and report_bytes is not None
                and sha256_bytes(report_bytes) == data.get("report_sha256")
            )
        else:
            run_ok = False
        journal_consistent = journal_consistent and run_ok

    checks.append(
        _check(
            "journal-terminal-consistency",
            bool(parsed_journals) and journal_consistent,
            "P1",
            "Every run journal is canonical, complete, and correlated with its report hash.",
        )
    )

    migration_ids = {
        item.get("run_id")
        for item in (standard_data or {}).get("migrations", [])
        if isinstance(item, dict)
    }
    status_consistent = bool(standard_data) and bool(complete_run_ids) and migration_ids.issubset(
        complete_run_ids
    )
    checks.append(
        _check(
            "status-consistency",
            status_consistent,
            "P1",
            "STANDARD migration history correlates with completed local run evidence.",
        )
    )
    checks.append(
        _check(
            "managed-scope-drift",
            bool(parsed_journals) and managed_scope_ok,
            "P1",
            "Journal authority and file receipts remain inside the coordinator allowlist.",
        )
    )

    render_ok = marker_ok and managed_block is not None and agents is not None
    if render_ok:
        try:
            body = agents[managed_block.body_start : managed_block.body_end].decode("utf-8")
            required_lines = (
                "Choose the smallest safe orientation tier:",
                "Preserve all content outside this block.",
                "Heartbeats are state-delta-only",
                "Discovered validation entry points:",
                "Project-specific exceptional risk rules:",
            )
            render_ok = all(line in body for line in required_lines)
        except UnicodeDecodeError:
            render_ok = False
    checks.append(
        _check(
            "render-idempotence",
            render_ok,
            "P1",
            "The managed instruction block matches the stable coordinator contract.",
        )
    )
    return _plain_checks(checks)


__all__ = [
    "DuplicateJsonKey",
    "strict_json_loads",
    "validate_json",
    "validate_repository",
    "validate_schema_document",
]
