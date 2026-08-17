from __future__ import annotations

import importlib
import json
from pathlib import Path
import tempfile
import unittest

from support import SKILL_ROOT, initialize_git, run_git


RELEASE_ROOT = SKILL_ROOT.parent


class LeanModeContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = tempfile.TemporaryDirectory()
        self.temp = Path(self.context.name)
        self.operations = importlib.import_module("coordinator_standard.operations")

    def tearDown(self) -> None:
        self.context.cleanup()

    def test_public_release_identity_is_single_coordinator_skill(self) -> None:
        self.assertEqual("0.1.0\n", (SKILL_ROOT / "VERSION").read_text(encoding="utf-8"))
        package = importlib.import_module("coordinator_standard")
        self.assertEqual("cody-coordinator", package.STANDARD_NAME)
        self.assertEqual("0.1.0", package.STANDARD_VERSION)

    def test_skill_and_managed_contract_expose_lean_routing_and_escalation(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        operating = (SKILL_ROOT / "references/operating-model.md").read_text(
            encoding="utf-8"
        )
        orchestration = (
            SKILL_ROOT / "references/orchestration-policy.md"
        ).read_text(encoding="utf-8")
        managed = (
            SKILL_ROOT / "assets/repo-template/AGENTS.managed.md"
        ).read_text(encoding="utf-8")
        combined = "\n".join((skill, operating, orchestration, managed)).casefold()

        for required in (
            "routine continuation",
            "recovery or conflicting evidence",
            "setup, upgrade, migration, destructive, or high-risk",
            "route by capability and role",
            "state-delta-only",
            "one active task truth",
            "one durable terminal record",
            "one worktree per active writer",
            "1,000–2,000 tokens",
            "prefer one worker and one reviewer",
            "routed cold evidence",
            "project owner",
            "coordinator",
            "worker",
            "reviewer",
            "model choice never broadens authority",
        ):
            self.assertIn(required, combined)
        for automatic_escalation in (
            "stale compact checkpoint",
            "wrong target",
            "unclear risk classification",
        ):
            self.assertIn(automatic_escalation, combined)
        self.assertIn(
            "routine continuation on a verified current repository does not preload the full doctor output",
            skill.casefold(),
        )
        self.assertNotIn("matching `check-current` command", skill)
        self.assertNotIn("nearest capable route", combined)
        consultation = orchestration.casefold()
        self.assertIn("chatgpt consultation is optional and never a release authority", consultation)
        self.assertIn("if the consultation is unavailable", consultation)
        self.assertIn("structured decision memo", consultation)

    def test_task_mesh_contract_is_bounded_and_measured(self) -> None:
        orchestration = (
            SKILL_ROOT / "references/orchestration-policy.md"
        ).read_text(encoding="utf-8").casefold()
        efficiency = (
            SKILL_ROOT / "references/execution-efficiency.md"
        ).read_text(encoding="utf-8").casefold()
        managed = (
            SKILL_ROOT / "assets/repo-template/AGENTS.managed.md"
        ).read_text(encoding="utf-8").casefold()
        combined = "\n".join((orchestration, efficiency, managed))

        for required in (
            "hub-and-spoke",
            "event-driven",
            "approval-independent task startup",
            "no interactive approval dependency",
            "never ask the project owner to watch background tasks for approval dialogs",
            "causally understood, mechanically specified repair slice",
            "there is no arbitrary repair-round limit",
            "each round makes concrete, evidence-backed progress",
            "each round closes a named finding",
            "structured decision memo",
            "measure actual usage when exposed",
            "otherwise record stable proxies",
            "optional consultation",
            "final review",
            "workers report to the coordinator",
            "p0/p1 findings block completion",
        ):
            self.assertIn(required, combined)

        self.assertIn("**green:**", orchestration)
        self.assertIn("**amber:**", orchestration)
        self.assertIn("**red:**", orchestration)
        self.assertIn("`blocked`", managed)
        self.assertIn("rather than wait for the project owner", managed)
        self.assertIn(
            "there is no arbitrary repair-round limit",
            " ".join(managed.split()),
        )
        self.assertIn("fail before mutation", efficiency)
        self.assertIn("contracts-only or partial harness checks never substitute for release certification", efficiency)
        self.assertIn("reconcile first", combined)

    def test_public_topology_and_fail_closed_boundaries_are_executable(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8").casefold()
        metadata = (SKILL_ROOT / "agents/openai.yaml").read_text(
            encoding="utf-8"
        ).casefold()
        orchestration = (
            SKILL_ROOT / "references/orchestration-policy.md"
        ).read_text(encoding="utf-8").casefold()
        efficiency = (
            SKILL_ROOT / "references/execution-efficiency.md"
        ).read_text(encoding="utf-8").casefold()
        authority = (
            SKILL_ROOT / "references/authority-matrix.md"
        ).read_text(encoding="utf-8").casefold()
        routing_contract = (
            SKILL_ROOT / "references/model-routing-contract.json"
        ).read_text(encoding="utf-8").casefold()
        managed = (
            SKILL_ROOT / "assets/repo-template/AGENTS.managed.md"
        ).read_text(encoding="utf-8").casefold()
        runtime = " ".join(
            "\n".join(
                (
                    skill,
                    metadata,
                    orchestration,
                    efficiency,
                    authority,
                    routing_contract,
                    managed,
                )
            ).split()
        )

        for required in (
            "sol medium → luna high",
            "sol medium → terra extra high → luna high",
            "terra extra high",
            "terra returns `scope_change`",
            "sol retains",
            "governs codex task orchestration only",
            "sol reviews 100% of terra conclusions and every resulting diff",
            "directly to their dispatching coordinator",
            "exactly one fresh low-context read-only luna high waiter",
            "no full-history fork",
            "approved correction path",
            "external-runtime or provider ambiguity fails closed",
            "only when listed safe",
            "action-specific token",
            "make this task the repository's durable cody coordinator",
            "do not create or imply a duplicate coordinator",
            "chatgpt pro when it is visibly available",
            "strongest available chatgpt model",
            "evidence unavailable",
            "never claim substitute evidence",
            "inspect, check-current, reconcile",
        ):
            self.assertIn(required, runtime)

        self.assertNotIn("version 2.5", runtime)
        for model_id in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"):
            self.assertIn(model_id, runtime)

    def test_standard_322_has_a_wip_preserving_upgrade_route(self) -> None:
        repo = self.temp / "standard-322-project"
        initialize_git(repo, commit=True)
        created = self.operations.initialize(repo, check=False)
        self.assertTrue(created.ok, created.blockers)

        markers = importlib.import_module("coordinator_standard.markers")
        agents_path = repo / "AGENTS.md"
        agents = agents_path.read_bytes()
        block = markers.parse_managed_block(agents)
        self.assertIsNotNone(block)
        downgraded = markers.format_managed_block(
            agents[block.body_start : block.body_end], version="3.2.2"
        )
        agents_path.write_bytes(agents[: block.start] + downgraded + agents[block.end :])

        standard_path = repo / "docs/codex/STANDARD.json"
        standard = json.loads(standard_path.read_text(encoding="utf-8"))
        standard["standard_version"] = "3.2.2"
        standard_path.write_text(json.dumps(standard, indent=2) + "\n", encoding="utf-8")
        run_git(repo, "add", ".")
        run_git(repo, "commit", "--quiet", "-m", "standard 3.2.2 baseline")

        checked = self.operations.upgrade(repo, check=True)
        self.assertTrue(checked.ok, checked.blockers)
        self.assertTrue(checked.changed)
        applied = self.operations.upgrade(repo, check=False)
        self.assertTrue(applied.ok, applied.blockers)
        self.assertIn(b"standard=0.1.0", agents_path.read_bytes())
        self.assertTrue(self.operations.doctor(repo).ok)
        self.assertFalse(self.operations.upgrade(repo, check=True).changed)

    def test_standard_323_has_a_wip_preserving_upgrade_route(self) -> None:
        repo = self.temp / "standard-323-project"
        initialize_git(repo, commit=True)
        created = self.operations.initialize(repo, check=False)
        self.assertTrue(created.ok, created.blockers)

        markers = importlib.import_module("coordinator_standard.markers")
        agents_path = repo / "AGENTS.md"
        agents = agents_path.read_bytes()
        block = markers.parse_managed_block(agents)
        self.assertIsNotNone(block)
        downgraded = markers.format_managed_block(
            agents[block.body_start : block.body_end], version="3.2.3"
        )
        agents_path.write_bytes(agents[: block.start] + downgraded + agents[block.end :])

        standard_path = repo / "docs/codex/STANDARD.json"
        standard = json.loads(standard_path.read_text(encoding="utf-8"))
        standard["standard_version"] = "3.2.3"
        standard_path.write_text(json.dumps(standard, indent=2) + "\n", encoding="utf-8")
        run_git(repo, "add", ".")
        run_git(repo, "commit", "--quiet", "-m", "standard 3.2.3 baseline")

        checked = self.operations.upgrade(repo, check=True)
        self.assertTrue(checked.ok, checked.blockers)
        self.assertTrue(checked.changed)
        applied = self.operations.upgrade(repo, check=False)
        self.assertTrue(applied.ok, applied.blockers)
        self.assertIn(b"standard=0.1.0", agents_path.read_bytes())
        self.assertTrue(self.operations.doctor(repo).ok)
        self.assertFalse(self.operations.upgrade(repo, check=True).changed)

    def test_standard_324_has_a_wip_preserving_upgrade_route(self) -> None:
        repo = self.temp / "standard-324-project"
        initialize_git(repo, commit=True)
        created = self.operations.initialize(repo, check=False)
        self.assertTrue(created.ok, created.blockers)

        markers = importlib.import_module("coordinator_standard.markers")
        agents_path = repo / "AGENTS.md"
        agents = agents_path.read_bytes()
        block = markers.parse_managed_block(agents)
        self.assertIsNotNone(block)
        downgraded = markers.format_managed_block(
            agents[block.body_start : block.body_end], version="3.2.4"
        )
        agents_path.write_bytes(agents[: block.start] + downgraded + agents[block.end :])

        standard_path = repo / "docs/codex/STANDARD.json"
        standard = json.loads(standard_path.read_text(encoding="utf-8"))
        standard["standard_version"] = "3.2.4"
        standard_path.write_text(json.dumps(standard, indent=2) + "\n", encoding="utf-8")
        run_git(repo, "add", ".")
        run_git(repo, "commit", "--quiet", "-m", "standard 3.2.4 baseline")

        checked = self.operations.upgrade(repo, check=True)
        self.assertTrue(checked.ok, checked.blockers)
        self.assertTrue(checked.changed)
        applied = self.operations.upgrade(repo, check=False)
        self.assertTrue(applied.ok, applied.blockers)
        self.assertIn(b"standard=0.1.0", agents_path.read_bytes())
        self.assertTrue(self.operations.doctor(repo).ok)
        self.assertFalse(self.operations.upgrade(repo, check=True).changed)

    def test_pressure_catalog_covers_lean_routing_and_silent_heartbeats(self) -> None:
        catalog = json.loads(
            (SKILL_ROOT / "tests/skill_pressure_cases.json").read_text(encoding="utf-8")
        )
        cases = {item["case"] for item in catalog["forward_with_skill"]}
        self.assertTrue(
            {
                "routine-continuation",
                "compaction-recovery-and-evidence-conflict",
                "high-risk-routing",
                "unchanged-heartbeat",
                "mechanical-scout-routing",
                "topology-and-runtime-ambiguity",
                "oversized-wip-routing",
            }.issubset(cases)
        )

    def test_execution_efficiency_contract_is_fail_closed(self) -> None:
        policy = (SKILL_ROOT / "references/execution-efficiency.md").read_text(
            encoding="utf-8"
        ).casefold()
        managed = (SKILL_ROOT / "assets/repo-template/AGENTS.managed.md").read_text(
            encoding="utf-8"
        ).casefold()
        combined = policy + "\n" + managed
        for required in (
            "completed job-minutes",
            "exact git-tree identity",
            "small independent",
            "exhaustive matrices",
            "validate diagnostic launchers locally",
            "provider/config readiness",
            "commit and push never certify deploy pins",
            "re-read every required direct and workload sha pin",
            "never retry unchanged failures",
            "structured terminal attempt",
            "one owner writes the active truth",
        ):
            self.assertIn(required, combined)

    def test_standard_321_has_a_wip_preserving_upgrade_route(self) -> None:
        repo = self.temp / "standard-321-project"
        initialize_git(repo, commit=True)
        created = self.operations.initialize(repo, check=False)
        self.assertTrue(created.ok, created.blockers)

        markers = importlib.import_module("coordinator_standard.markers")
        agents_path = repo / "AGENTS.md"
        agents = agents_path.read_bytes()
        block = markers.parse_managed_block(agents)
        self.assertIsNotNone(block)
        downgraded = markers.format_managed_block(
            agents[block.body_start : block.body_end], version="3.2.1"
        )
        agents_path.write_bytes(agents[: block.start] + downgraded + agents[block.end :])

        standard_path = repo / "docs/codex/STANDARD.json"
        standard = json.loads(standard_path.read_text(encoding="utf-8"))
        standard["standard_version"] = "3.2.1"
        standard_path.write_text(json.dumps(standard, indent=2) + "\n", encoding="utf-8")
        run_git(repo, "add", ".")
        run_git(repo, "commit", "--quiet", "-m", "standard 3.2.1 baseline")

        checked = self.operations.upgrade(repo, check=True)
        self.assertTrue(checked.ok, checked.blockers)
        self.assertTrue(checked.changed)
        applied = self.operations.upgrade(repo, check=False)
        self.assertTrue(applied.ok, applied.blockers)
        self.assertIn(b"standard=0.1.0", agents_path.read_bytes())
        self.assertTrue(self.operations.doctor(repo).ok)
        self.assertFalse(self.operations.upgrade(repo, check=True).changed)

    def test_standard_320_has_a_wip_preserving_upgrade_route(self) -> None:
        repo = self.temp / "standard-320-project"
        initialize_git(repo, commit=True)
        created = self.operations.initialize(repo, check=False)
        self.assertTrue(created.ok, created.blockers)

        markers = importlib.import_module("coordinator_standard.markers")
        agents_path = repo / "AGENTS.md"
        agents = agents_path.read_bytes()
        block = markers.parse_managed_block(agents)
        self.assertIsNotNone(block)
        downgraded = markers.format_managed_block(
            agents[block.body_start : block.body_end], version="3.2.0"
        )
        agents_path.write_bytes(agents[: block.start] + downgraded + agents[block.end :])

        standard_path = repo / "docs/codex/STANDARD.json"
        standard = json.loads(standard_path.read_text(encoding="utf-8"))
        standard["standard_version"] = "3.2.0"
        standard_path.write_text(json.dumps(standard, indent=2) + "\n", encoding="utf-8")
        run_git(repo, "add", ".")
        run_git(repo, "commit", "--quiet", "-m", "standard 3.2.0 baseline")

        checked = self.operations.upgrade(repo, check=True)
        self.assertTrue(checked.ok, checked.blockers)
        self.assertTrue(checked.changed)
        applied = self.operations.upgrade(repo, check=False)
        self.assertTrue(applied.ok, applied.blockers)
        self.assertIn(b"standard=0.1.0", agents_path.read_bytes())
        self.assertTrue(self.operations.doctor(repo).ok)
        self.assertFalse(self.operations.upgrade(repo, check=True).changed)

    def test_new_status_is_compact_and_contains_only_current_truth_contract(self) -> None:
        repo = self.temp / "lean-project"
        initialize_git(repo, commit=True)
        result = self.operations.initialize(repo, check=False)
        self.assertTrue(result.ok, result.blockers)

        status = (repo / "docs/codex/STATUS.md").read_text(encoding="utf-8")
        required = (
            "## Current exact identity and deploy truth",
            "## Active task IDs",
            "## Open P0/P1",
            "## Authority or decision blocker",
            "## One next action",
            "Freshness:",
        )
        for heading in required:
            self.assertIn(heading, status)
        self.assertLessEqual((len(status.encode("utf-8")) + 3) // 4, 2_000)
        self.assertNotIn("## Last verified completed milestone", status)
        doctor = self.operations.doctor(repo)
        self.assertTrue(doctor.ok, doctor.validation)
        compactness = next(
            item for item in doctor.validation if item["name"] == "status-compactness"
        )
        self.assertTrue(compactness["ok"])

    def test_oversized_status_fails_closed_and_requires_fuller_orientation(self) -> None:
        repo = self.temp / "oversized-status"
        initialize_git(repo, commit=True)
        result = self.operations.initialize(repo, check=False)
        self.assertTrue(result.ok, result.blockers)
        status_path = repo / "docs/codex/STATUS.md"
        status_path.write_text(status_path.read_text() + ("evidence " * 4_500))

        doctor = self.operations.doctor(repo)

        self.assertFalse(doctor.ok)
        compactness = next(
            item for item in doctor.validation if item["name"] == "status-compactness"
        )
        self.assertFalse(compactness["ok"])


if __name__ == "__main__":
    unittest.main()
