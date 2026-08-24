#!/usr/bin/env python3
"""Resolve Cody's declared task-routing contract without contacting Codex."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence


CONTRACT_PATH = Path(__file__).resolve().parents[1] / "references/model-routing-contract.json"


class ContractError(RuntimeError):
    pass


def _validate_contract(contract: Any) -> dict[str, Any]:
    if not isinstance(contract, dict) or contract.get("schema_version") != 2:
        raise ContractError("routing contract identity is unsupported")
    roles = contract.get("roles")
    routes = contract.get("routes")
    boundaries = contract.get("authority_boundaries")
    task_mesh = contract.get("task_mesh")
    policy = contract.get("unavailable_named_model_policy")
    effort_profiles = contract.get("effort_profiles")
    repair_chain = contract.get("default_repair_chain")
    selection_rules = contract.get("selection_rules")
    measurement = contract.get("measurement")
    evidence_boundary = contract.get("evidence_boundary")
    if (
        not isinstance(roles, list)
        or not isinstance(routes, dict)
        or not isinstance(boundaries, dict)
        or not isinstance(task_mesh, dict)
        or not isinstance(policy, dict)
        or not isinstance(effort_profiles, dict)
        or not isinstance(repair_chain, list)
        or not isinstance(selection_rules, dict)
        or not isinstance(measurement, list)
        or not isinstance(evidence_boundary, dict)
        or not all(
            isinstance(role, dict)
            and isinstance(role.get("id"), str)
            and isinstance(role.get("model"), str)
            and isinstance(role.get("label"), str)
            and isinstance(role.get("default_reasoning_effort"), str)
            and isinstance(role.get("allowed_reasoning_efforts"), list)
            and role["allowed_reasoning_efforts"]
            and all(
                isinstance(effort, str)
                for effort in role["allowed_reasoning_efforts"]
            )
            and isinstance(role.get("authority"), str)
            for role in roles
        )
    ):
        raise ContractError("routing contract structure is unsupported")
    for key in (
        "retained_by_sol",
        "forbidden_for_terra",
        "forbidden_for_luna",
        "terra_scope_change_triggers",
    ):
        values = boundaries.get(key)
        if (
            not isinstance(values, list)
            or not values
            or not all(isinstance(value, str) for value in values)
        ):
            raise ContractError("routing authority boundaries are unsupported")
    identifiers = [role["id"] for role in roles]
    models = [role["model"] for role in roles]
    role_by_id = {role["id"]: role for role in roles}
    expected_role_efforts = {
        "primary_coordinator": ("medium", ["low", "medium", "high", "xhigh", "max"]),
        "junior_coordinator": ("medium", ["low", "medium", "high", "xhigh", "max"]),
        "bounded_worker": ("medium", ["low", "medium", "high", "max"]),
    }
    if (
        len(set(identifiers)) != len(roles)
        or len(set(models)) != len(roles)
        or set(identifiers)
        != {"primary_coordinator", "junior_coordinator", "bounded_worker"}
        or set(effort_profiles) != set(identifiers)
        or any(
            role["default_reasoning_effort"] != expected_role_efforts[role["id"]][0]
            or role["allowed_reasoning_efforts"] != expected_role_efforts[role["id"]][1]
            for role in roles
        )
    ):
        raise ContractError("routing routes are unsupported")
    for role_id, profile in effort_profiles.items():
        role = role_by_id[role_id]
        if (
            not isinstance(profile, dict)
            or set(profile) != set(role["allowed_reasoning_efforts"])
            or not all(
                isinstance(tasks, list)
                and tasks
                and all(isinstance(task, str) and task for task in tasks)
                for tasks in profile.values()
            )
        ):
            raise ContractError("routing effort profiles are unsupported")
    expected_routes = {
        "compact-synthesis": (["primary_coordinator"], ["low"]),
        "routine-operations": (
            ["primary_coordinator", "bounded_worker"],
            ["medium", "medium"],
        ),
        "simple": (
            ["primary_coordinator", "bounded_worker"],
            ["medium", "high"],
        ),
        "multi-stage": (
            ["primary_coordinator", "junior_coordinator", "bounded_worker"],
            ["medium", "medium", "high"],
        ),
        "complex-repair": (
            ["primary_coordinator", "junior_coordinator", "bounded_worker"],
            ["medium", "high", "high"],
        ),
        "high-risk-judgment": (["primary_coordinator"], ["high"]),
    }
    if set(routes) != set(expected_routes):
        raise ContractError("routing routes are unsupported")
    for route_name, (expected_roles, expected_efforts) in expected_routes.items():
        route = routes[route_name]
        if (
            not isinstance(route, dict)
            or route.get("role_ids") != expected_roles
            or route.get("reasoning_efforts") != expected_efforts
            or any(
                effort not in role_by_id[role_id]["allowed_reasoning_efforts"]
                for role_id, effort in zip(expected_roles, expected_efforts)
            )
        ):
            raise ContractError("routing routes are unsupported")
    if (
        len(repair_chain) != 5
        or not all(
            isinstance(stage, dict)
            and isinstance(stage.get("stage"), str)
            and stage.get("role_id") in role_by_id
            and stage.get("reasoning_effort")
            in role_by_id[stage["role_id"]]["allowed_reasoning_efforts"]
            for stage in repair_chain
        )
        or selection_rules
        != {
            "skip_unnecessary_layers": True,
            "explicit_model_and_reasoning_effort": True,
            "cheaper_worker_repair_round_is_not_saving": True,
            "exact_quota_when_unexposed": "unavailable",
            "api_price_ratios": "directional-only-not-subscription-quota",
        }
        or measurement
        != [
            "first_pass_acceptance",
            "repeated_causal_failures",
            "repair_rounds",
            "elapsed_time",
            "escaped_defects",
            "coordinator_rework",
        ]
        or evidence_boundary
        != {
            "proof_failure": "useful execution evidence is not proof that the worker damaged code",
            "unavailable_model_identity": "cannot support a model-capability conclusion",
            "policy_basis": "task-shape risk and repeated-repair economics, not a blanket claim that Luna is incapable",
        }
    ):
        raise ContractError("routing selection policy is unsupported")
    if not isinstance(policy.get("code"), str) or not isinstance(policy.get("action"), str):
        raise ContractError("routing unavailable-model policy is unsupported")
    if task_mesh != {
        "critical_delivery_owner": "visible-task",
        "hidden_subagents": "bounded-support-only",
        "dispatch_edges": [
            ["root_coordinator", "primary_coordinator"],
            ["primary_coordinator", "junior_coordinator"],
            ["primary_coordinator", "bounded_worker"],
            ["junior_coordinator", "bounded_worker"],
        ],
        "required_parent_fields": ["task_id", "host"],
        "typed_events": [
            "READY",
            "READY_FOR_REVIEW",
            "BLOCKED",
            "SCOPE_CHANGE",
            "FAILED",
            "LIVE_TERMINAL",
            "COMPLETE",
        ],
        "unchanged_state": "silent",
        "terminal_callback_required": True,
        "missing_callback_reconciliation": {
            "owner": "immediate-parent",
            "attempts": 1,
        },
    }:
        raise ContractError("routing task mesh is unsupported")
    return contract


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ContractError("routing contract is unavailable or malformed") from error
    return _validate_contract(contract)


def resolve_route(
    route_name: str, available_models: Sequence[str], contract: dict[str, Any] | None = None
) -> dict[str, Any]:
    active = _validate_contract(contract) if contract is not None else load_contract()
    route = active["routes"].get(route_name)
    if not isinstance(route, dict):
        raise ContractError("requested route is not declared")
    available = set(available_models)
    role_by_id = {role["id"]: role for role in active["roles"]}
    selected = [role_by_id[role_id] for role_id in route["role_ids"]]
    efforts = route["reasoning_efforts"]
    unavailable = [role for role in selected if role["model"] not in available]
    if unavailable:
        policy = active["unavailable_named_model_policy"]
        return {
            "ok": False,
            "code": policy["code"],
            "route": route_name,
            "required_models": [role["model"] for role in selected],
            "unavailable_models": [
                f"{role['label']} {effort.title()}"
                for role, effort in zip(selected, efforts)
                if role["model"] not in available
            ],
            "unavailable_model_ids": [role["model"] for role in unavailable],
            "action": policy["action"],
            "substitution": "none-selected",
        }
    return {
        "ok": True,
        "action": "route-resolved",
        "route": route_name,
        "assignments": [
            {
                "role": role["id"],
                "model": f"{role['label']} {effort.title()}",
                "model_id": role["model"],
                "reasoning_effort": effort,
                "authority": role["authority"],
            }
            for role, effort in zip(selected, efforts)
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve the declared Cody model-routing contract")
    parser.add_argument("--route", required=True)
    parser.add_argument(
        "--available",
        action="append",
        default=None,
        metavar="MODEL",
        help="Observed available model name; repeat once for each model.",
    )
    arguments = parser.parse_args(argv)
    try:
        contract = load_contract()
        if arguments.route not in contract["routes"]:
            raise ContractError("requested route is not declared")
        if arguments.available is None:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "code": "availability_evidence_required",
                        "route": arguments.route,
                        "action": "report-missing-evidence-and-return-scope-change",
                    },
                    sort_keys=True,
                )
            )
            return 2
        result = resolve_route(arguments.route, arguments.available, contract)
    except ContractError as error:
        print(json.dumps({"ok": False, "code": "invalid_routing_contract", "message": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
