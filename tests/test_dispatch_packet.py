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
        )
        for mutation in ("callback", "visibility"):
            broken = copy.deepcopy(packet)
            if mutation == "callback":
                broken["reporting"]["terminal_callback_required"] = False
            else:
                broken["visibility"]["child_task"] = "hidden"
            with self.assertRaises(dispatch_packet.DispatchPacketError):
                dispatch_packet.validate_packet(broken)

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
        ]
        generated = subprocess.run(command, text=True, capture_output=True, check=False)
        self.assertEqual(0, generated.returncode, generated.stderr or generated.stdout)
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
