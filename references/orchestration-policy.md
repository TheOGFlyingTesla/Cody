# Orchestration Policy

## Choose the smallest sound shape

Use the coordinator for requirements, decisions, synthesis, and simple work. Use read-only workers for uncertainty, risky paths, logs, or test discovery. Use parallel workers only when outcomes are independent and write sets do not overlap; sequence work when ownership is uncertain.

Each worker packet includes:

- one outcome and why it matters;
- owned and forbidden paths;
- non-goals and authority boundary;
- base branch/worktree identity when relevant;
- acceptance criteria and validation evidence;
- stop conditions and direct coordinator report format.

Use managed worktrees only when write isolation is useful. Use one worktree per
active writer and prefer one worker and one reviewer for an ordinary bounded
slice. Do not create a permanent control checkout by default. Record active
branch, worktree, and base evidence in `STATUS.md` when recovery would otherwise
be ambiguous.

## Approval-independent task startup

Resolve the authoritative starting ref in the coordinator before dispatch. Let the managed task/worktree surface own checkout and branch setup. A worker uses its existing isolated branch; it does not create a second branch or nested clone/worktree.

Worker packets state `no interactive approval dependency`. Workers may verify HEAD, tree, origin, and status, but must not perform state-changing or network setup that can trigger an approval prompt after launch. If the starting state is stale, missing, or unverifiable, the worker emits `BLOCKED` immediately. Never grant broad persistent permission as a workaround.

Never ask the project owner to watch background tasks for approval dialogs. A
worker must return `BLOCKED` rather than wait for the project owner, and the
coordinator must correct the packet or managed starting state.

## Plan, goal, and model routing

Use `/plan` when requirements, ownership, or validation need to be explicit. Use the persistent goal mechanism for long-running work that must survive compaction. Keep goals concrete and mark them complete only after validation and review gates pass.

Route by capability and role, never by a model name:

- the coordinator and reviewer use the strongest balanced reasoning available for judgment, synthesis, risk classification, and exact-diff review;
- workers use the least costly capable model that can satisfy the fixed packet and deterministic oracle;
- a stronger model is an exception for a bounded slice that genuinely needs it or after a proved capability failure;
- model choice never broadens authority, and an unavailable model falls back to the nearest capable route without claiming stronger evidence.

## Risk and review

- **Green:** the coordinator writes the packet; a worker implements and runs focused proof; the reviewer checks the compact diff and evidence.
- **Amber:** the coordinator fixes the boundary and acceptance oracle; a worker implements the mechanically testable slice; the coordinator or risk-appropriate reviewer verifies it.
- **Red:** the coordinator owns diagnosis, invariants, security/transaction judgment, exact-diff review, and release. A worker may implement only a causally understood, mechanically specified repair slice.

Use the write/review loop: coordinator packet → worker implementation and proof → reviewer exact-diff review → precise repair packet when needed → worker repair and proof → repeat while each round closes a named finding and makes concrete, evidence-backed progress. There is no arbitrary repair-round limit. Stop, reslice, or escalate when the same causal failure repeats without progress, a class-level repair fails again, scope or authority changes, evidence conflicts, or judgment can no longer be separated from implementation.

Each round makes concrete, evidence-backed progress or the coordinator stops and
reslices. Reconcile first when interrupted state or durable evidence conflicts.

## Task mesh, waiting, and consultation

Use a hub-and-spoke mesh. Workers report to the coordinator; they do not form a peer message bus. Check-ins are event-driven and typed: `BLOCKED`, `SCOPE_CHANGE`, `READY_FOR_REVIEW`, `FAILED`, or `CANCELLED`. Prefer a native blocking/event wait. If repeated checks or an uncertain-duration wait is unavoidable, dispatch one fresh low-context read-only worker with exact targets, safety boundaries, a wall-clock horizon, and one terminal report. The coordinator does not poll unchanged state.

The project owner is never the message bus between workers.

ChatGPT consultation is optional and never a release authority. Use it only when explicitly requested or authorized for a named condition. If ChatGPT Pro is visibly available, use Pro; otherwise use the strongest available ChatGPT model (currently GPT-5.6) at the highest supported reasoning level. If the consultation is unavailable, cannot be verified, or cannot complete naturally, continue the core work without it and label that evidence unavailable. Pass a structured decision memo rather than a full transcript by default.

## Context, efficiency, and fan-in

Keep routine packets near 1,000–2,000 tokens and link durable evidence instead of copying it. Compaction is short-term pressure relief; after roughly 20–30 turns or two compactions, checkpoint and continue from a fresh task at a safe boundary. Measure actual usage when exposed; otherwise record stable proxies such as packet/output bytes, turns, compactions, repair rounds, and handoff size. A cheaper route that causes reslicing, duplicated context, or coordinator rework is not efficient.

Workers report to the coordinator. The coordinator reviews evidence, resolves conflicts, integrates within authority, and updates durable state. Classify new ideas without silently widening scope. P0/P1 findings block completion; P2/P3 findings receive an explicit fixed, accepted, or deferred disposition.

## CI and release economy

Follow [execution-efficiency.md](execution-efficiency.md). Measure completed job-minutes and event duplication before changing workflows. Prefer path-based tiers, explicit exhaustive matrices, one exact-candidate broad proof, and a stable required sentinel. Post-merge reuse must prove exact tree identity and successful required checks; otherwise run the full tier.
