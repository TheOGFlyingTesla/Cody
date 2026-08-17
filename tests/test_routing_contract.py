from __future__ import annotations

import json
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from support import SKILL_ROOT


SCRIPTS = SKILL_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import routing_contract
import routing_live_eval


class RoutingContractTests(unittest.TestCase):
    def test_duplicate_native_model_ids_fail_closed(self) -> None:
        contract = copy.deepcopy(routing_contract.load_contract())
        contract["roles"][2]["model"] = contract["roles"][0]["model"]

        with self.assertRaises(routing_contract.ContractError):
            routing_contract.resolve_route("simple", ["gpt-5.6-sol"], contract)

    def test_route_topology_drift_fails_closed(self) -> None:
        contract = copy.deepcopy(routing_contract.load_contract())
        contract["routes"]["simple"]["role_ids"] = ["primary_coordinator"]

        with self.assertRaises(routing_contract.ContractError):
            routing_contract.resolve_route("simple", ["gpt-5.6-sol"], contract)

    def test_contract_structures_sol_and_terra_authority_boundaries(self) -> None:
        boundaries = routing_contract.load_contract()["authority_boundaries"]
        self.assertIn("privacy_security_and_identity", boundaries["retained_by_sol"])
        self.assertIn("destructive_decisions", " ".join(boundaries["forbidden_for_terra"]))
        self.assertEqual(
            ["red_work", "authority_drift", "risk_drift", "inseparable_judgment"],
            boundaries["terra_scope_change_triggers"],
        )

    def test_cli_requires_route_and_availability_evidence(self) -> None:
        missing_route = subprocess.run(
            [sys.executable, str(SCRIPTS / "routing_contract.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(2, missing_route.returncode)

        missing_evidence = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "routing_contract.py"),
                "--route",
                "simple",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(2, missing_evidence.returncode)
        self.assertEqual(
            "availability_evidence_required",
            json.loads(missing_evidence.stdout)["code"],
        )

    def test_literal_skill_example_resolves_simple_route(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "routing_contract.py"),
                "--route",
                "simple",
                "--available",
                "gpt-5.6-sol",
                "--available",
                "gpt-5.6-luna",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertEqual("route-resolved", json.loads(completed.stdout)["action"])

    def test_declared_multi_stage_route_assigns_exact_named_roles(self) -> None:
        result = routing_contract.resolve_route(
            "multi-stage", ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"]
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            [
                ("primary_coordinator", "Sol Medium"),
                ("junior_coordinator", "Terra Extra High"),
                ("bounded_worker", "Luna High"),
            ],
            [(item["role"], item["model"]) for item in result["assignments"]],
        )
        self.assertIn("release", result["assignments"][0]["authority"])
        self.assertIn("fixed Green/Amber", result["assignments"][1]["authority"])
        self.assertEqual(
            ["medium", "xhigh", "high"],
            [item["reasoning_effort"] for item in result["assignments"]],
        )

    def test_missing_named_model_returns_scope_change_without_substitution(self) -> None:
        result = routing_contract.resolve_route(
            "multi-stage", ["gpt-5.6-sol", "gpt-5.6-luna"]
        )

        self.assertFalse(result["ok"])
        self.assertEqual("named_model_unavailable", result["code"])
        self.assertEqual(["Terra Extra High"], result["unavailable_models"])
        self.assertEqual("report-unavailable-and-return-scope-change", result["action"])
        self.assertEqual("none-selected", result["substitution"])

    def test_live_observation_harness_checks_assignments_without_external_command(self) -> None:
        observation = {
            "route": "simple",
            "available_models": ["gpt-5.6-sol", "gpt-5.6-luna"],
            "assignments": {
                "primary_coordinator": "Sol Medium",
                "bounded_worker": "Luna High",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observation.json"
            path.write_text(json.dumps(observation), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "routing_live_eval.py"),
                    "--observation",
                    str(path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual("routing-observation-conforms-to-contract", result["action"])

    def test_live_observation_harness_reports_assignment_mismatch(self) -> None:
        result = routing_live_eval.evaluate(
            {
                "route": "simple",
                "available_models": ["gpt-5.6-sol", "gpt-5.6-luna"],
                "assignments": {
                    "primary_coordinator": "Luna High",
                    "bounded_worker": "Sol Medium",
                },
            }
        )

        self.assertFalse(result["ok"])
        self.assertEqual("role_assignment_mismatch", result["code"])


if __name__ == "__main__":
    unittest.main()
