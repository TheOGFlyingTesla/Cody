<!-- cody-coordinator:start standard=0.2.0 -->
Choose the smallest safe orientation tier:

- Routine continuation: applicable `AGENTS.md`, Git/status, `STATUS.md`, and one active work item or native task.
- Recovery or conflicting evidence: full contract and recent native summaries.
- Setup, upgrade, migration, destructive, or high-risk: full contract, relevant journals, and `doctor`/`reconcile` as applicable.

Conflict, stale checkpoint, wrong target, or unclear risk escalates automatically. Preserve authority, exact Git/deploy truth, identity isolation, idempotency, duplicate prevention, fail-closed runtimes, focused reproducers, WIP, and P0/P1 gates.

This managed block and `docs/codex/` are coordinator-owned. Preserve all content outside this block. More-specific nested `AGENTS.md` files govern their subtrees.

Keep `STATUS.md` near 2,000 tokens or less: identity/deploy truth, active task IDs, open P0/P1, authority/decision blocker, one next action, and freshness. Use one active task truth and one linked terminal record. Large WIP, registry, and handoff files are routed cold evidence; routine work loads only the compact index and relevant appendix. Heartbeats are state-delta-only: unchanged state is silent and cannot broaden authority or duplicate work.

The project owner retains product direction, priority, and consequential approvals. Critical and multi-stage milestones use visible Codex tasks: root/portfolio coordinator → one visible Sol Medium coordinator per bounded initiative; Sol → visible Terra Extra High only when coordination materially saves context, otherwise visible Luna High directly; Terra → visible Luna High. Hidden subagents may provide bounded internal support inside Luna but never own critical milestone delivery. Sol owns judgment, P0/P1 adjudication, review, authority, and release; Terra is a bounded junior coordinator; Luna owns routine implementation, execution, and uncertain waiting. Model names never define authority. If a named model is unavailable, report it and return `SCOPE_CHANGE`; never choose a nearest or silent substitute. Substitution is unsupported in v0.2.0; changing the declared topology requires a future contract revision. This topology governs Codex task orchestration only, never application, provider-runtime, customer-facing, or production inference model routing.

Every child packet includes the exact parent task ID and host and requires direct upward typed state deltas: `READY`, `READY_FOR_REVIEW`, `BLOCKED`, `SCOPE_CHANGE`, `FAILED`, `LIVE_TERMINAL`, or `COMPLETE`. Unchanged state is silent. Fan-in is Luna → Terra → Sol → root; the project owner is never the message bus. Coordinators stay idle and event-driven between events. If a callback fails or a child terminates without notifying, the immediate parent performs one bounded reconciliation and restores upward notification without waiting for the project owner.

Use one worktree per active writer when isolation is useful. Workers must return `BLOCKED` rather than wait for the project owner or an interactive approval. For repeated checks or uncertain-duration waiting, dispatch exactly one fresh low-context read-only Luna waiter with named targets, a wall-clock horizon, and one typed terminal report; Sol never timer-polls unchanged state. Review and repair while each round closes a named finding; there is no arbitrary repair-round limit. Reconcile first after interrupted setup or upgrade, and resume, rollback, repair, or supersede only when it is a listed safe action. Repair, rollback, and supersede require an action-specific token bound to verified evidence.

ChatGPT consultation is optional and advisory. Prefer ChatGPT Pro when visibly available; otherwise use the strongest available ChatGPT model at the highest supported reasoning level. If availability, mode, or completion cannot be verified, stop that consultation, label it unavailable, never claim substitute evidence, and continue unrelated core work.

For CI and release work, measure completed job-minutes, triggers, retries, matrices, and setup tax. When an existing hosted CI surface is evidence-discovered, keep a small independent required sentinel there; otherwise record hosted CI as unavailable and use the project's actual local or self-hosted proof surface. Reuse proof after merge only when automation proves exact Git-tree identity and successful required checks; otherwise run the full tier. Commit and push never certify deploy pins: derive the immutable candidate and re-read every required direct/workload SHA pin immediately before deploy, failing before mutation on mismatch and exposing only the approved correction path. Validate diagnostic launchers locally, prove evidence-discovered service/configuration readiness, fail closed on provider or external-runtime ambiguity, never retry unchanged failures, and record one structured terminal attempt.

Discovered validation entry points:

- **test:** `python3 -m unittest discover -s tests -p 'test_*.py'`
- **doctor:** `python3 scripts/coordinator_standard.py --repo . --format json doctor`
- **release:** `python3 scripts/build_release.py --help`
- **diff:** `git diff --check`

Project-specific exceptional risk rules:

- Public release privacy, credential, and exact-candidate review are release gates.
<!-- cody-coordinator:end -->
