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


def _validate_schema_contract() -> None:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        reporting = schema["properties"]["reporting"]["properties"]
        visibility = schema["properties"]["visibility"]["properties"]
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
    ):
        raise DispatchPacketError("dispatch packet schema violates the canonical callback contract")


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


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
) -> dict[str, Any]:
    _validate_schema_contract()
    edge = (parent_role, child_role)
    if route not in ALLOWED_EDGES or edge not in ALLOWED_EDGES[route]:
        raise DispatchPacketError("parent/child roles are not allowed for the selected route")
    for label, value in (
        ("parent task ID", parent_task_id),
        ("parent host", parent_host),
        ("child task ID", child_task_id),
        ("child host", child_host),
        ("outcome", outcome),
    ):
        if not _nonempty(value):
            raise DispatchPacketError(f"{label} is required")
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
    if not isinstance(packet, dict) or packet.get("schema_version") != 1:
        raise DispatchPacketError("dispatch packet identity is unsupported")
    route = packet.get("route")
    parent = packet.get("parent")
    child = packet.get("child")
    reporting = packet.get("reporting")
    visibility = packet.get("visibility")
    if not all(isinstance(item, dict) for item in (parent, child, reporting, visibility)):
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
                )
            ):
                raise DispatchPacketError("--validate cannot be combined with generation options")
            packet = json.loads(arguments.validate.read_text(encoding="utf-8"))
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
            )
            result = packet
    except (DispatchPacketError, OSError, UnicodeError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "code": "invalid_dispatch_packet", "message": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
