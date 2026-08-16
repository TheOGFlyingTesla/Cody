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

Route by capability and role; model names make the current topology explicit.
The explicit topology is Sol Medium as primary coordinator, reviewer, and
release owner; Terra Extra High as an optional junior coordinator only for a
fixed multi-stage Green/Amber boundary; and Luna High as the default bounded
scout, worker, executor, and waiter. A simple slice goes directly
Sol-to-Luna. A suitable multi-stage slice goes Sol-to-Terra-to-Luna, with Terra
receiving a compact no-history packet.

Terra may decompose only the supplied Green/Amber boundary, dispatch bounded
Luna work, enforce the supplied acceptance oracle, and return one structured
synthesis. Terra returns `SCOPE_CHANGE` to Sol immediately for Red work,
risk/authority drift, or implementation judgment that cannot be separated from
the packet. Sol retains requirements, risk classification, architecture/product
judgment, privacy/security/identity review, concurrency and destructive
decisions, P0/P1 adjudication, exact-diff review, final synthesis, and release.

Model names express this topology, not authority. If names or availability
change, use the nearest capable route without claiming unavailable-model
evidence. An unavailable capability never silently grants a stronger worker or
coordinator role.

This topology governs Codex task orchestration only. It never enables or
selects Sol, Terra, or Luna inside the application, provider runtime,
customer-facing model routing, or production inference path.

## Risk and review

- **Green:** Sol writes the packet; Luna High implements and runs focused proof; Sol reviews the compact diff and evidence.
- **Amber:** Sol fixes the boundary and acceptance oracle; Luna High implements the mechanically testable slice; a risk-appropriate reviewer may add evidence, but Sol verifies the result.
- **Red:** Sol owns diagnosis, invariants, security/transaction judgment, exact-diff review, and release. Luna may implement only a causally understood, mechanically specified repair slice.

Use the write/review loop: coordinator packet → worker implementation and proof → reviewer exact-diff review → precise repair packet when needed → worker repair and proof → repeat while each round closes a named finding and makes concrete, evidence-backed progress. There is no arbitrary repair-round limit. Stop, reslice, or escalate when the same causal failure repeats without progress, a class-level repair fails again, scope or authority changes, evidence conflicts, or judgment can no longer be separated from implementation.

Sol reviews 100% of Terra conclusions and every resulting diff. Terra never
accepts a release gate or substitutes its synthesis for Sol's exact-diff review.

Each round makes concrete, evidence-backed progress or the coordinator stops and
reslices. Reconcile first when interrupted state or durable evidence conflicts.

## Task mesh, waiting, and consultation

Use a hub-and-spoke mesh. Workers report directly to their dispatching
coordinator; they do not form a peer message bus. Check-ins are event-driven and
typed: `BLOCKED`, `SCOPE_CHANGE`, `READY_FOR_REVIEW`, `FAILED`, or `CANCELLED`.
The project owner is never the message bus.

Prefer a native blocking/event wait. If repeated checks or an uncertain-duration
wait is unavoidable, dispatch exactly one fresh low-context read-only Luna High
waiter with exact targets, safety boundaries, a wall-clock horizon, and one
typed terminal report. It receives no full-history fork and no mutation or
release authority. Sol may make one initial read and one terminal spot-check;
the coordinator does not poll unchanged state.

ChatGPT consultation is optional and never a release authority. It is advisory.
Use it only when explicitly requested or authorized for a named condition.
Prefer ChatGPT Pro when it is visibly available; otherwise use the strongest
available ChatGPT model at the highest supported reasoning level. If the consultation is unavailable, cannot be verified, or cannot complete naturally,
stop that consultation, label its evidence unavailable, never claim substitute
evidence, and continue unrelated core work. Pass a structured decision memo
rather than a full transcript by default.

## Context, efficiency, and fan-in

Keep routine packets near 1,000–2,000 tokens and link durable evidence instead of copying it. Compaction is short-term pressure relief; after roughly 20–30 turns or two compactions, checkpoint and continue from a fresh task at a safe boundary. Measure actual usage when exposed; otherwise record stable proxies such as packet/output bytes, turns, compactions, repair rounds, and handoff size. A cheaper route that causes reslicing, duplicated context, or coordinator rework is not efficient.

Workers report to the coordinator. The coordinator reviews evidence, resolves conflicts, integrates within authority, and updates durable state. Classify new ideas without silently widening scope. P0/P1 findings block completion; P2/P3 findings receive an explicit fixed, accepted, or deferred disposition.

## CI and release economy

Follow [execution-efficiency.md](execution-efficiency.md). Measure completed job-minutes and event duplication before changing workflows. Prefer path-based tiers, explicit exhaustive matrices, one exact-candidate broad proof, and a stable required sentinel. Post-merge reuse must prove exact tree identity and successful required checks; otherwise run the full tier.
