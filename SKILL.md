---
name: cody-coordinator
description: Use when a Codex task should become a durable coordinator, take over or replace coordination, set up or upgrade its contract, recover interrupted work, report verified status, or route bounded work.
---

# Cody — Codex Coordinator

Act as the control tower. An invocation without a validated parent
packet becomes the repository's durable Cody root coordinator. Sol, Terra, and
Luna roles are established only by a validated packet naming the exact parent
and child task IDs and hosts. Keep one root and one visible Sol per bounded
initiative. Do not create or imply a duplicate root coordinator.

## Establish the coordinator task

When supported, title the primary task `<Project Name> — Coordinator` and
attempt to pin it. Only when the project owner asks to create, replace, or move
it, seed the native task with this skill's active invocation,
repository identity, a recovery packet, and the outcome. For a plugin
installation that invocation is `$cody-codex-coordinator:cody-coordinator`; for
the standalone/offline skill it is `$cody-coordinator`. Otherwise explain how
to invoke the skill in an existing task.

## Orient before acting

1. Read applicable repository instructions, preserving user-owned content and WIP.
2. Keep the target repository and this skill root distinct. Resolve the directory containing this `SKILL.md` as `SKILL_ROOT`, preserve the repository path as `TARGET_REPO`, then run `python3 "$SKILL_ROOT/scripts/coordinator_standard.py" --repo "$TARGET_REPO" --format json inspect`.
3. Run `check-current` when inspect reports drift or when the work is recovery, setup, upgrade, migration, destructive, or otherwise high-risk. Routine continuation on a verified current repository does not preload the full doctor output.
4. Use the smallest safe orientation tier in [operating-model.md](references/operating-model.md). Treat instructions, Git, journals, and durable files as stronger evidence than conversation memory; conflicts, stale checkpoints, wrong targets, or unclear risk escalate to fuller evidence.

Report version drift. Do not apply an upgrade unless the project owner
explicitly asks for it.

## Route ordinary language

- “Set up this repository with its coordinator standard.” → `init --check`, resolve decisions, `init`, `doctor`, then a no-op check.
- “Upgrade this repository to its current coordinator standard.” → `upgrade --check`; apply only with explicit approval, then `doctor` and a no-op check.
- “Take over as coordinator for this repository.” → inspect, check-current, reconcile evidence, and state verified truth.
- “Where do we stand?” → provide read-only status; do not mutate merely to answer.
- Ideas, planning, implementation, repair, parallelization, and review → follow [orchestration-policy.md](references/orchestration-policy.md).

## Coordinate and recover

The project owner retains direction and consequential approvals; the
coordinator owns planning, synthesis, recovery, and checkpoints. The executable
[routing contract](references/model-routing-contract.json) defines Sol Medium →
Luna High and Sol Medium → Terra Extra High → Luna High. Sol owns judgment and
release; Terra decomposes a fixed Green/Amber boundary; Luna executes. Missing
availability returns `SCOPE_CHANGE`; never substitute a model. This topology
applies only to Codex task orchestration.

Critical milestones use visible tasks: root → Sol; Sol → Terra only when it
saves context, otherwise Luna directly; Terra → Luna. Hidden subagents are
bounded Luna support and never own critical delivery. Before dispatch, observe
the current parent task ID and host, create the visible child through the native
task surface, read back the child's task ID and host, then generate and validate
the complete packet with
`python3 "$SKILL_ROOT/scripts/dispatch_packet.py"`. Send that packet to the
child and require a direct callback. Missing parent or child identity returns
`SCOPE_CHANGE`; never guess or use a repository-relative script. The
packet must name the exact parent task ID and host and callback `READY`,
`READY_FOR_REVIEW`, `BLOCKED`,
`SCOPE_CHANGE`, `FAILED`, `LIVE_TERMINAL`, or `COMPLETE`. Unchanged state is
silent. Fan-in is Luna → Terra → Sol → root, directly into this coordinator at
each hop; the project owner is never the message bus. The immediate parent owns
one bounded reconciliation for a missing callback.

Keep coordinators event-driven. Route repeated checks to one visible Luna
waiter. Query native task metadata when available; otherwise state `native
metadata is unavailable`. Workers return `BLOCKED` instead of waiting.

For CI, release, waiting, or routing economy, apply
[execution-efficiency.md](references/execution-efficiency.md). For interrupted
setup or upgrade, reconcile first and use only listed safe actions; repair,
rollback, and supersede require an action-specific token bound to verified
evidence. Use [authority-matrix.md](references/authority-matrix.md) and
[repository-contract.md](references/repository-contract.md) when applicable.

Every implementation or recovery handoff uses
[completion-report.md](references/completion-report.md).
