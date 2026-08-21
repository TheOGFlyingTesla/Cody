#!/usr/bin/env python3
"""Generate and validate Cody visible-task dispatch packets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "assets/schema/dispatch-packet.schema.json"
EVENTS = (
    "READY",
    "READY_FOR_REVIEW",
    "BLOCKED",
    "SCOPE_CHANGE",
    "FAILED",
    "LIVE_TERMINAL",
    "COMPLETE",
)
WORK_FIELDS = (
    "owned_paths",
    "forbidden_paths",
    "non_goals",
    "authority_boundary",
    "base_identity",
    "acceptance_criteria",
    "validation_requirements",
    "stop_conditions",
    "report_format",
)
ALLOWED_EDGES = {
    "root-to-sol": {("root_coordinator", "primary_coordinator")},
    "simple": {("primary_coordinator", "bounded_worker")},
    "multi-stage": {
        ("primary_coordinator", "junior_coordinator"),
        ("junior_coordinator", "bounded_worker"),
    },
}


class DispatchPacketError(RuntimeError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DispatchPacketError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _load_json_unique(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_reject_duplicate_keys)


def _validate_schema_contract() -> None:
    try:
        schema = _load_json_unique(SCHEMA_PATH.read_text(encoding="utf-8"))
        reporting = schema["properties"]["reporting"]["properties"]
        visibility = schema["properties"]["visibility"]["properties"]
        work = schema["properties"]["work"]
        event_values = reporting["events"]["items"]["enum"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise DispatchPacketError("dispatch packet schema is unavailable or malformed") from error
    if (
        schema.get("type") != "object"
        or event_values != list(EVENTS)
        or reporting.get("terminal_callback_required", {}).get("const") is not True
        or reporting.get("direct_upward", {}).get("const") is not True
        or visibility.get("child_task", {}).get("const") != "visible"
        or visibility.get("hidden_subagents", {}).get("const") != "bounded-support-only"
        or work.get("required") != list(WORK_FIELDS)
    ):
        raise DispatchPacketError("dispatch packet schema violates the canonical callback contract")


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nonempty_list(label: str, value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)) or not value:
        raise DispatchPacketError(f"{label} must contain at least one item")
    normalized = list(value)
    if not all(_nonempty(item) for item in normalized):
        raise DispatchPacketError(f"{label} must contain only non-empty strings")
    if len(set(normalized)) != len(normalized):
        raise DispatchPacketError(f"{label} must not contain duplicate items")
    return normalized


def build_packet(
    *,
    route: str,
    parent_role: str,
    parent_task_id: str,
    parent_host: str,
    child_role: str,
    child_task_id: str,
    child_host: str,
    outcome: str,
    owned_paths: Sequence[str],
    forbidden_paths: Sequence[str],
    non_goals: Sequence[str],
    authority_boundary: str,
    base_identity: str,
    acceptance_criteria: Sequence[str],
    validation_requirements: Sequence[str],
    stop_conditions: Sequence[str],
    report_format: str,
) -> dict[str, Any]:
    _validate_schema_contract()
    if not all(_nonempty(value) for value in (route, parent_role, child_role)):
        raise DispatchPacketError("route and parent/child roles must be non-empty strings")
    edge = (parent_role, child_role)
    if route not in ALLOWED_EDGES or edge not in ALLOWED_EDGES[route]:
        raise DispatchPacketError("parent/child roles are not allowed for the selected route")
    for label, value in (
        ("parent task ID", parent_task_id),
        ("parent host", parent_host),
        ("child task ID", child_task_id),
        ("child host", child_host),
        ("outcome", outcome),
        ("authority boundary", authority_boundary),
        ("base identity", base_identity),
        ("report format", report_format),
    ):
        if not _nonempty(value):
            raise DispatchPacketError(f"{label} is required")
    if parent_task_id == child_task_id and parent_host == child_host:
        raise DispatchPacketError("parent and child task identity must be distinct")
    work = {
        "owned_paths": _nonempty_list("owned paths", owned_paths),
        "forbidden_paths": _nonempty_list("forbidden paths", forbidden_paths),
        "non_goals": _nonempty_list("non-goals", non_goals),
        "authority_boundary": authority_boundary,
        "base_identity": base_identity,
        "acceptance_criteria": _nonempty_list("acceptance criteria", acceptance_criteria),
        "validation_requirements": _nonempty_list(
            "validation requirements", validation_requirements
        ),
        "stop_conditions": _nonempty_list("stop conditions", stop_conditions),
        "report_format": report_format,
    }
    return {
        "schema_version": 1,
        "route": route,
        "parent": {
            "role": parent_role,
            "task_id": parent_task_id,
            "host": parent_host,
        },
        "child": {
            "role": child_role,
            "task_id": child_task_id,
            "host": child_host,
        },
        "outcome": outcome,
        "work": work,
        "reporting": {
            "destination_task_id": parent_task_id,
            "destination_host": parent_host,
            "events": list(EVENTS),
            "unchanged_state": "silent",
            "direct_upward": True,
            "terminal_callback_required": True,
            "missing_callback_reconciliation": {
                "owner": "immediate-parent",
                "attempts": 1,
            },
        },
        "visibility": {
            "child_task": "visible",
            "critical_milestone_owner": "visible-task",
            "hidden_subagents": "bounded-support-only",
        },
    }


def validate_packet(packet: Any) -> dict[str, Any]:
    if (
        not isinstance(packet, dict)
        or type(packet.get("schema_version")) is not int
        or packet.get("schema_version") != 1
    ):
        raise DispatchPacketError("dispatch packet identity is unsupported")
    route = packet.get("route")
    parent = packet.get("parent")
    child = packet.get("child")
    reporting = packet.get("reporting")
    visibility = packet.get("visibility")
    work = packet.get("work")
    if not all(
        isinstance(item, dict) for item in (parent, child, work, reporting, visibility)
    ):
        raise DispatchPacketError("dispatch packet structure is unsupported")
    expected = build_packet(
        route=route,
        parent_role=parent.get("role"),
        parent_task_id=parent.get("task_id"),
        parent_host=parent.get("host"),
        child_role=child.get("role"),
        child_task_id=child.get("task_id"),
        child_host=child.get("host"),
        outcome=packet.get("outcome"),
        owned_paths=work.get("owned_paths"),
        forbidden_paths=work.get("forbidden_paths"),
        non_goals=work.get("non_goals"),
        authority_boundary=work.get("authority_boundary"),
        base_identity=work.get("base_identity"),
        acceptance_criteria=work.get("acceptance_criteria"),
        validation_requirements=work.get("validation_requirements"),
        stop_conditions=work.get("stop_conditions"),
        report_format=work.get("report_format"),
    )
    if packet != expected:
        raise DispatchPacketError("dispatch packet violates the canonical callback contract")
    return packet


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", type=Path)
    parser.add_argument("--route", choices=sorted(ALLOWED_EDGES))
    parser.add_argument("--parent-role")
    parser.add_argument("--parent-task-id")
    parser.add_argument("--parent-host")
    parser.add_argument("--child-role")
    parser.add_argument("--child-task-id")
    parser.add_argument("--child-host")
    parser.add_argument("--outcome")
    parser.add_argument("--owned-path", action="append")
    parser.add_argument("--forbidden-path", action="append")
    parser.add_argument("--non-goal", action="append")
    parser.add_argument("--authority-boundary")
    parser.add_argument("--base-identity")
    parser.add_argument("--acceptance-criterion", action="append")
    parser.add_argument("--validation-requirement", action="append")
    parser.add_argument("--stop-condition", action="append")
    parser.add_argument("--report-format")
    arguments = parser.parse_args(argv)
    try:
        if arguments.validate is not None:
            if any(
                value is not None
                for value in (
                    arguments.route,
                    arguments.parent_role,
                    arguments.parent_task_id,
                    arguments.parent_host,
                    arguments.child_role,
                    arguments.child_task_id,
                    arguments.child_host,
                    arguments.outcome,
                    arguments.owned_path,
                    arguments.forbidden_path,
                    arguments.non_goal,
                    arguments.authority_boundary,
                    arguments.base_identity,
                    arguments.acceptance_criterion,
                    arguments.validation_requirement,
                    arguments.stop_condition,
                    arguments.report_format,
                )
            ):
                raise DispatchPacketError("--validate cannot be combined with generation options")
            packet = _load_json_unique(arguments.validate.read_text(encoding="utf-8"))
            validate_packet(packet)
            result = {"ok": True, "action": "dispatch-packet-valid"}
        else:
            packet = build_packet(
                route=arguments.route,
                parent_role=arguments.parent_role,
                parent_task_id=arguments.parent_task_id,
                parent_host=arguments.parent_host,
                child_role=arguments.child_role,
                child_task_id=arguments.child_task_id,
                child_host=arguments.child_host,
                outcome=arguments.outcome,
                owned_paths=arguments.owned_path,
                forbidden_paths=arguments.forbidden_path,
                non_goals=arguments.non_goal,
                authority_boundary=arguments.authority_boundary,
                base_identity=arguments.base_identity,
                acceptance_criteria=arguments.acceptance_criterion,
                validation_requirements=arguments.validation_requirement,
                stop_conditions=arguments.stop_condition,
                report_format=arguments.report_format,
            )
            result = packet
    except (DispatchPacketError, OSError, UnicodeError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "code": "invalid_dispatch_packet", "message": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
