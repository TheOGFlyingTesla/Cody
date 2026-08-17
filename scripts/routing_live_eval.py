#!/usr/bin/env python3
"""Validate an explicit, opt-in observation from a Codex routing exercise."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence

from routing_contract import ContractError, load_contract, resolve_route


class LiveEvaluationError(RuntimeError):
    pass


def _load_observation(raw: bytes) -> dict[str, Any]:
    try:
        observation = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise LiveEvaluationError("live observation is not valid JSON") from error
    if not isinstance(observation, dict):
        raise LiveEvaluationError("live observation is not an object")
    route = observation.get("route")
    available = observation.get("available_models")
    assignments = observation.get("assignments")
    if (
        not isinstance(route, str)
        or not isinstance(available, list)
        or not all(isinstance(model, str) for model in available)
        or not isinstance(assignments, dict)
        or not all(isinstance(role, str) and isinstance(model, str) for role, model in assignments.items())
    ):
        raise LiveEvaluationError("live observation does not match the required schema")
    return observation


def _command_observation(command: Sequence[str]) -> bytes:
    if not command:
        raise LiveEvaluationError("an external observation command is required")
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise LiveEvaluationError("external observation command could not complete") from error
    if completed.returncode != 0:
        raise LiveEvaluationError("external observation command failed")
    return completed.stdout


def evaluate(observation: dict[str, Any]) -> dict[str, Any]:
    contract = load_contract()
    expected = resolve_route(observation["route"], observation["available_models"], contract)
    if not expected["ok"]:
        return expected
    expected_assignments = {
        item["role"]: item["model"] for item in expected["assignments"]
    }
    if observation["assignments"] != expected_assignments:
        return {
            "ok": False,
            "code": "role_assignment_mismatch",
            "route": observation["route"],
            "action": "report-observed-routing-mismatch",
        }
    return {
        "ok": True,
        "action": "routing-observation-conforms-to-contract",
        "route": observation["route"],
        "assignments": expected_assignments,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check an opt-in routing observation against the contract")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--observation", type=Path)
    source.add_argument("--command", nargs=argparse.REMAINDER)
    arguments = parser.parse_args(argv)
    try:
        raw = (
            arguments.observation.read_bytes()
            if arguments.observation is not None
            else _command_observation(arguments.command)
        )
        result = evaluate(_load_observation(raw))
    except (OSError, ContractError, LiveEvaluationError) as error:
        print(json.dumps({"ok": False, "code": "live_evaluation_invalid", "message": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
