from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from support import SKILL_ROOT


SCRIPTS = SKILL_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import dispatch_packet


def work_fields() -> dict[str, object]:
    return {
        "owned_paths": ["src/**"],
        "forbidden_paths": ["production/**"],
        "non_goals": ["No deployment."],
        "authority_boundary": "Implement and test only; do not push or deploy.",
        "base_identity": "origin/main@abc123; clean isolated worktree",
        "acceptance_criteria": ["Focused tests pass."],
        "validation_requirements": ["Return command and result evidence."],
        "stop_conditions": ["Return BLOCKED on identity or authority conflict."],
        "report_format": "Typed state delta followed by compact evidence.",
    }


class DispatchPacketTests(unittest.TestCase):
    def test_root_to_sol_packet_is_visible_and_reports_to_exact_root(self) -> None:
        packet = dispatch_packet.build_packet(
            route="root-to-sol",
            parent_role="root_coordinator",
            parent_task_id="root-task",
            parent_host="local",
            child_role="primary_coordinator",
            child_task_id="sol-task",
            child_host="local",
            outcome="Coordinate one bounded initiative.",
            **work_fields(),
        )

        self.assertEqual("root-task", packet["reporting"]["destination_task_id"])
        self.assertEqual("local", packet["reporting"]["destination_host"])
        self.assertEqual("visible", packet["visibility"]["child_task"])
        self.assertEqual(packet, dispatch_packet.validate_packet(packet))

    def test_simple_sol_to_luna_packet_has_direct_parent_callback(self) -> None:
        packet = dispatch_packet.build_packet(
            route="simple",
            parent_role="primary_coordinator",
            parent_task_id="sol-task",
            parent_host="local",
            child_role="bounded_worker",
            child_task_id="luna-task",
            child_host="local",
            outcome="Implement the bounded slice.",
            **work_fields(),
        )

        self.assertEqual("sol-task", packet["reporting"]["destination_task_id"])
        self.assertEqual("local", packet["reporting"]["destination_host"])
        self.assertEqual(list(dispatch_packet.EVENTS), packet["reporting"]["events"])
        self.assertTrue(packet["reporting"]["terminal_callback_required"])
        self.assertEqual("silent", packet["reporting"]["unchanged_state"])
        self.assertEqual("visible", packet["visibility"]["child_task"])
        self.assertEqual("bounded-support-only", packet["visibility"]["hidden_subagents"])
        self.assertEqual(packet, dispatch_packet.validate_packet(packet))

    def test_multi_stage_supports_sol_to_terra_and_terra_to_luna(self) -> None:
        for parent_role, child_role in (
            ("primary_coordinator", "junior_coordinator"),
            ("junior_coordinator", "bounded_worker"),
        ):
            packet = dispatch_packet.build_packet(
                route="multi-stage",
                parent_role=parent_role,
                parent_task_id="parent-task",
                parent_host="host-a",
                child_role=child_role,
                child_task_id="child-task",
                child_host="host-b",
                outcome="Return one typed state delta.",
                **work_fields(),
            )
            self.assertEqual(packet, dispatch_packet.validate_packet(packet))

    def test_hidden_or_missing_terminal_callback_fails_closed(self) -> None:
        packet = dispatch_packet.build_packet(
            route="simple",
            parent_role="primary_coordinator",
            parent_task_id="sol-task",
            parent_host="local",
            child_role="bounded_worker",
            child_task_id="luna-task",
            child_host="local",
            outcome="Bounded implementation.",
            **work_fields(),
        )
        for mutation in ("callback", "visibility"):
            broken = copy.deepcopy(packet)
            if mutation == "callback":
                broken["reporting"]["terminal_callback_required"] = False
            else:
                broken["visibility"]["child_task"] = "hidden"
            with self.assertRaises(dispatch_packet.DispatchPacketError):
                dispatch_packet.validate_packet(broken)

    def test_packet_structurally_requires_complete_work_boundary(self) -> None:
        packet = dispatch_packet.build_packet(
            route="simple",
            parent_role="primary_coordinator",
            parent_task_id="sol-task",
            parent_host="local",
            child_role="bounded_worker",
            child_task_id="luna-task",
            child_host="local",
            outcome="Implement the bounded slice.",
            **work_fields(),
        )
        self.assertEqual(list(dispatch_packet.WORK_FIELDS), list(packet["work"]))
        for field in dispatch_packet.WORK_FIELDS:
            broken = copy.deepcopy(packet)
            del broken["work"][field]
            with self.subTest(field=field):
                with self.assertRaises(dispatch_packet.DispatchPacketError):
                    dispatch_packet.validate_packet(broken)

    def test_malformed_packet_types_fail_closed_without_crashing(self) -> None:
        packet = dispatch_packet.build_packet(
            route="simple",
            parent_role="primary_coordinator",
            parent_task_id="sol-task",
            parent_host="local",
            child_role="bounded_worker",
            child_task_id="luna-task",
            child_host="local",
            outcome="Implement the bounded slice.",
            **work_fields(),
        )
        for path, value in (
            (("route",), []),
            (("parent", "role"), {}),
            (("schema_version",), True),
            (("work", "owned_paths"), "src/**"),
            (("work", "stop_conditions"), [""]),
        ):
            broken = copy.deepcopy(packet)
            target = broken
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = value
            with self.subTest(path=path, value=value):
                with self.assertRaises(dispatch_packet.DispatchPacketError):
                    dispatch_packet.validate_packet(broken)

    def test_parent_child_self_loop_fails_closed(self) -> None:
        packet = dispatch_packet.build_packet(
            route="simple",
            parent_role="primary_coordinator",
            parent_task_id="sol-task",
            parent_host="local",
            child_role="bounded_worker",
            child_task_id="luna-task",
            child_host="local",
            outcome="Implement the bounded slice.",
            **work_fields(),
        )
        packet["child"]["task_id"] = "sol-task"
        with self.assertRaises(dispatch_packet.DispatchPacketError):
            dispatch_packet.validate_packet(packet)

    def test_cli_rejects_malformed_types_and_duplicate_json_keys(self) -> None:
        malformed_documents = (
            '{"schema_version":1,"route":[],"parent":{},"child":{},"outcome":"x","work":{},"reporting":{},"visibility":{}}',
            '{"schema_version":1,"route":"simple","route":"multi-stage"}',
            '{"schema_version":1,"parent":{"task_id":"root","task_id":"other"}}',
        )
        for document in malformed_documents:
            with self.subTest(document=document):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "packet.json"
                    path.write_text(document, encoding="utf-8")
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(SCRIPTS / "dispatch_packet.py"),
                            "--validate",
                            str(path),
                        ],
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                self.assertEqual(2, result.returncode, result.stderr or result.stdout)
                self.assertEqual(
                    "invalid_dispatch_packet", json.loads(result.stdout)["code"]
                )
                self.assertNotIn("Traceback", result.stderr)

    def test_cli_generated_packet_round_trips_through_validator(self) -> None:
        command = [
            sys.executable,
            str(SCRIPTS / "dispatch_packet.py"),
            "--route", "simple",
            "--parent-role", "primary_coordinator",
            "--parent-task-id", "sol-task",
            "--parent-host", "local",
            "--child-role", "bounded_worker",
            "--child-task-id", "luna-task",
            "--child-host", "local",
            "--outcome", "Run focused proof.",
            "--owned-path", "src/**",
            "--forbidden-path", "production/**",
            "--non-goal", "No deployment.",
            "--authority-boundary", "Implement and test only.",
            "--base-identity", "origin/main@abc123",
            "--acceptance-criterion", "Focused tests pass.",
            "--validation-requirement", "Return command and result evidence.",
            "--stop-condition", "Return BLOCKED on conflict.",
            "--report-format", "Typed state delta with compact evidence.",
        ]
        with tempfile.TemporaryDirectory() as unrelated_directory:
            generated = subprocess.run(
                command,
                cwd=unrelated_directory,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(0, generated.returncode, generated.stderr or generated.stdout)
        self_loop_command = list(command)
        child_id_index = self_loop_command.index("--child-task-id") + 1
        self_loop_command[child_id_index] = "sol-task"
        self_loop = subprocess.run(
            self_loop_command,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, self_loop.returncode, self_loop.stderr or self_loop.stdout)
        self.assertEqual("invalid_dispatch_packet", json.loads(self_loop.stdout)["code"])
        self.assertNotIn("Traceback", self_loop.stderr)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "packet.json"
            path.write_text(generated.stdout, encoding="utf-8")
            validated = subprocess.run(
                [sys.executable, str(SCRIPTS / "dispatch_packet.py"), "--validate", str(path)],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(0, validated.returncode, validated.stderr or validated.stdout)
        self.assertEqual("dispatch-packet-valid", json.loads(validated.stdout)["action"])


if __name__ == "__main__":
    unittest.main()
