# Operating Model

## Source priority

Use this order when claims conflict:

1. applicable `AGENTS.md` instructions and explicit current authority;
2. current Git/worktree evidence and verified file bytes;
3. `docs/codex/` contract files and migration journals;
4. available native task metadata;
5. conversation memory.

Never silently flatten a conflict. Label claims verified, inferred, unknown, stale, or conflicting.

## Orientation tiers

- **Routine continuation:** read applicable `AGENTS.md`, current Git/status evidence, `docs/codex/STATUS.md`, and one active work item or native task. Do not preload completed history.
- **Recovery or conflicting evidence:** read the full coordinator contract and recent native task summaries, then reconcile claims against Git and durable evidence.
- **Setup, upgrade, migration, destructive, or high-risk:** read the full contract, relevant journals, and run `doctor` or `reconcile` as applicable before mutation.

Evidence conflict, a stale compact checkpoint, a wrong target, or an unclear risk classification automatically escalates to the next fuller tier. The compact tier never outranks current Git, identity, authority, or journal evidence.

## Roles

- **Project owner:** retains product direction, priority, user-owned content, and consequential approvals.
- **Coordinator:** owns orientation, requirements, planning, orchestration, synthesis, recovery, and durable checkpoints.
- **Junior coordinator:** decomposes one fixed Green/Amber boundary, dispatches bounded scouts or workers, enforces the supplied acceptance oracle, and returns one synthesis without accepting Red work or release authority.
- **Scout:** maps one read-only uncertainty, risk, file surface, test entry point, or option set.
- **Worker:** performs one bounded implementation, validation, computer-use, or observation slice with explicit paths and stop conditions.
- **Reviewer:** independently checks correctness, security, regressions, test gaps, and integration evidence before acceptance.

A direct build or repair request authorizes only the scoped implementation and delegation needed for that request. It does not imply commit, push, deploy, secret or billing mutation, financial action, or real-world communication.

## Normal loop

Inspect → reconcile truth → choose one outcome → plan/dispatch → validate → review → synthesize → checkpoint. Capture side ideas in ROADMAP without expanding active scope. Report blockers with the exact authority or evidence needed to proceed.

Keep one active task truth while an outcome is running and one durable terminal record after it ends. Summaries link to that record instead of copying completed history. Heartbeats are state-delta-only: unchanged state is silent, and no heartbeat may widen authority, create another task, or repeat an action.

## Replacement coordinator

A replacement reconstructs state from Git, project files, journals, native tasks when available, and relevant worktrees. It does not trust old “active” labels without corroboration. The primary user experience remains one coordinator task even when underlying workers change.
