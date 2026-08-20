# Orchestration Policy

## Choose the smallest sound shape

Use Sol for requirements, decisions, packets, synthesis, review, and release.
Route authorized implementation slices, including simple slices, to Luna High.
Use read-only workers for uncertainty, risky paths, logs, or test discovery. Use
parallel workers only when outcomes are independent and write sets do not
overlap; sequence work when ownership is uncertain.

Each worker packet includes:

- one outcome and why it matters;
- owned and forbidden paths;
- non-goals and authority boundary;
- base branch/worktree identity when relevant;
- acceptance criteria and validation evidence;
- stop conditions and direct coordinator report format;
- the exact parent task ID and host; and
- the required typed callbacks and terminal callback destination.

Critical delivery and uncertain waiting remain visible in the Codex task list.
Hidden subagents may be used only inside a Luna task for bounded support and may
not own a critical milestone, terminal proof, or completion callback.

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

Route by capability and role. Use
[the executable routing contract](model-routing-contract.json) as the one
source for model names, roles, routes, unavailable-model handling, and the
live-observation schema. The declared named topology is Sol Medium as primary
coordinator, reviewer, and release owner; Terra Extra High as junior
coordinator only for a fixed multi-stage Green/Amber boundary; and Luna High
as the bounded scout, worker, executor, and waiter. A simple slice is Sol
Medium → Luna High. A suitable multi-stage slice is Sol Medium → Terra Extra
High → Luna High, with Terra receiving a compact no-history packet.

Terra may decompose only the supplied Green/Amber boundary, dispatch bounded
Luna work, enforce the supplied acceptance oracle, and return one structured
synthesis. Terra returns `SCOPE_CHANGE` to Sol immediately for Red work,
risk/authority drift, or implementation judgment that cannot be separated from
the packet. Sol retains requirements, risk classification, architecture/product
judgment, privacy/security/identity review, concurrency and destructive
decisions, P0/P1 adjudication, exact-diff review, final synthesis, and release.

Model names express this topology, not authority. Before dispatch, choose the
declared route and pass every model the native surface actually reports to
`$SKILL_ROOT/scripts/routing_contract.py` with repeated `--available` options.
If availability evidence cannot be observed, report
`availability_evidence_required` and return `SCOPE_CHANGE`; do not treat missing
evidence as observed unavailability. If a named model is observed unavailable,
report its name and return `SCOPE_CHANGE`; no route is selected. Never use a
nearest-capable fallback or a silent substitution. Substitution is unsupported
in v0.2.0; changing the declared topology requires a future contract revision.
An unavailable capability never grants a stronger worker or coordinator role.
Model choice never broadens authority.

This topology governs Codex task orchestration only. It never enables or
selects Sol, Terra, or Luna inside the application, provider runtime,
customer-facing model routing, or production inference path.

## Opt-in routing observation conformance

Ordinary CI resolves only the local routing contract; it never invokes a live
Codex command or consumes credits. To check a real, explicitly authorized
Codex routing exercise, use the version-appropriate local observer supplied by
the operator. Cody does not guess a Codex CLI or API command. The observer must
emit JSON with `route`, `available_models`, and `assignments`, then either save
that JSON and run:

```bash
python3 "$SKILL_ROOT/scripts/routing_live_eval.py" --observation routing-observation.json
```

or pass the observer as the final argument sequence after
`--command`. The harness checks whether the supplied observation conforms to
the canonical contract and reports a mismatch or named-model unavailability;
it never silently substitutes a model. Operator-authored JSON is self-attested
evidence, not proof that Codex executed the claimed route. Claim a live product
result only when the operator supplies a provenance-bearing native observer.

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

Use a visible hub-and-spoke mesh: root/portfolio coordinator → one visible Sol
task per bounded initiative; Sol → visible Terra only when coordination
materially reduces context, otherwise visible Luna directly; Terra → visible
Luna. Workers do not form a peer message bus. Every child packet names its exact
parent task ID and host and sends state deltas directly to that parent. Check-ins
are event-driven and typed: `READY`, `READY_FOR_REVIEW`, `BLOCKED`,
`SCOPE_CHANGE`, `FAILED`, `LIVE_TERMINAL`, or `COMPLETE`. Unchanged state is
silent. Fan-in is Luna → Terra → Sol → root, and the project owner is never the
message bus or completion detector.
The project owner is never the message bus.

Generate or validate packets with `scripts/dispatch_packet.py` and
`assets/schema/dispatch-packet.schema.json`. A terminal callback is mandatory.
If callback delivery fails or a child terminates silently, the immediate parent
owns one bounded reconciliation, restores the upward notification, and does not
wait for the project owner to ask for status.

Prefer a native blocking/event wait and keep coordinators idle between events.
If repeated checks or an uncertain-duration
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

Luna reports to Terra when Terra dispatched it, otherwise directly to Sol;
Terra reports to Sol; Sol reports to root. The receiving coordinator reviews
evidence, resolves conflicts, integrates within authority, and updates durable
state. Classify new ideas without silently widening scope. P0/P1 findings block completion;
P2/P3 findings receive an explicit fixed, accepted, or deferred disposition.

## CI and release economy

Follow [execution-efficiency.md](execution-efficiency.md). Measure completed job-minutes and event duplication before changing workflows. Prefer path-based tiers, explicit exhaustive matrices, one exact-candidate broad proof, and a stable required sentinel. Post-merge reuse must prove exact tree identity and successful required checks; otherwise run the full tier.
