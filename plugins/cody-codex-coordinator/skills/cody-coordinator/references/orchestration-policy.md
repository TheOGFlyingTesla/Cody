# Orchestration Policy

## Choose the smallest sound shape

Use Sol for requirements, authority, risk, architecture/product judgment,
synthesis, P0/P1 adjudication, and release. Route class-level implementation and
independent review to Terra. Use Luna after judgment is fixed for routine
operations, deterministic proof, or an exact-oracle mechanical edit. Use
parallel workers only when outcomes and write sets are independent.

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

Route by capability and role. The executable
[routing contract](model-routing-contract.json) is the source for model families,
reasoning efforts, task classes, routes, authority, and measurement. Sol Medium
is the persistent coordinator and release owner. Sol Low is only for compact
low-risk synthesis. Use Sol High for hard architecture, production/release,
security/privacy/identity, schema/data-integrity, or concurrency judgment when
Medium is insufficient; XHigh/Max are exceptional quality-first escalation.

Terra Medium is the default class-level writer and independent reviewer for
ordinary multi-file repairs, behavior-preserving refactors, known-invariant
runtime integration, and bounded causal debugging. Use Terra High when several
components or state machines interact, the cause remains uncertain, or a
class-level repair fails. Terra XHigh/Max are bounded escalation, not routine
coordination. Terra returns `SCOPE_CHANGE` when authority or risk drifts,
evidence conflicts, or Sol-owned judgment becomes inseparable.

Luna Low/Medium handles waiting, monitoring, artifact publication, repetitive
shell/computer-use, formatting, and cheap inventory. Luna High handles
deterministic focused proof, dogfood/eval execution, and tightly specified
mechanical edits with an exact oracle. Luna never owns open-ended architecture,
ambiguous repair, class-level runtime design, privacy/security judgment, P0/P1
adjudication, or release. Luna Max is exceptional and only for a hard fully
specified deterministic slice after a proved High capability gap.

Model names express this topology, not authority. Set both model and reasoning
effort explicitly. Before dispatch, choose the declared route and pass every
model the native surface actually reports to
`$SKILL_ROOT/scripts/routing_contract.py` with repeated `--available` options.
If availability evidence cannot be observed, report
`availability_evidence_required` and return `SCOPE_CHANGE`; do not treat missing
evidence as observed unavailability. If a named model is observed unavailable,
report its name and return `SCOPE_CHANGE`; no route is selected. Never use a
nearest-capable fallback or a silent substitution. Substitution is unsupported
in v0.3.0; changing the declared topology requires a future contract revision.
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

- **Green:** Luna High handles deterministic proof or an exact-oracle edit;
  Terra Medium handles any implementation judgment still required.
- **Amber:** Terra Medium owns the fixed class-level repair and review. Use Terra
  High when components interact or the causal mechanism remains uncertain;
  Luna runs deterministic proof after judgment is fixed.
- **Red:** Sol owns authority, invariants, security/transaction judgment, P0/P1,
  and release. Terra performs bounded causal work and the class repair only
  after Sol fixes the acceptance contract; Luna runs the resulting proof.

Default repair is Sol invariant/authority/stop conditions → Terra RED→GREEN
class repair → independent Terra exact-diff review when needed → Luna
production-shaped focused proof → Sol final disposition. Skip unnecessary
layers. A cheaper worker that causes another repair round is not a saving.
Continue only while each round closes a named causal gap; stop, reslice, or
escalate on repeated causal failure, failed class repair, authority drift, or
conflicting evidence.

Sol reviews 100% of Terra conclusions and every resulting diff. Terra never
accepts a release gate or substitutes its synthesis for Sol's exact-diff review.

Each round makes concrete, evidence-backed progress or the coordinator stops and
reslices. Reconcile first when interrupted state or durable evidence conflicts.

## Task mesh, waiting, and consultation

Use a visible hub-and-spoke mesh: root/portfolio coordinator → one visible Sol
task per bounded initiative; Sol → visible Terra for class-level work or visible
Luna directly for routine deterministic work; Terra → visible Luna for focused
proof when useful. Workers do not form a peer message bus. Every child packet names its exact
parent task ID and host and sends state deltas directly to that parent. Check-ins
are event-driven and typed: `READY`, `READY_FOR_REVIEW`, `BLOCKED`,
`SCOPE_CHANGE`, `FAILED`, `LIVE_TERMINAL`, or `COMPLETE`. Unchanged state is
silent. Fan-in is Luna → Terra → Sol → root, and the project owner is never the
message bus or completion detector.

Before dispatch, observe the parent's exact native task ID and host, create the
visible child, read back its exact task ID and host, then generate and validate
the complete packet with
`python3 "$SKILL_ROOT/scripts/dispatch_packet.py"`. The canonical schema is
`$SKILL_ROOT/assets/schema/dispatch-packet.schema.json`; schema-only validation
is insufficient because legal role edges and destination equality are enforced
by the Python validator. Missing native identity returns `SCOPE_CHANGE`; never
guess identity or execute a repository-relative lookalike. The generator
represents every work-boundary field listed above, and validation rejects
malformed types, unknown fields, duplicate JSON keys, and parent/child
self-loops. A terminal callback is mandatory.

Event meanings are intentionally small:

- `READY`: child accepted the packet and began; nonterminal.
- `READY_FOR_REVIEW`: bounded work and evidence await parent review;
  nonterminal.
- `LIVE_TERMINAL`: an identified terminal or session still owns uncertain
  waiting; nonterminal.
- `BLOCKED`: child stopped because required authority or evidence is missing;
  terminal.
- `SCOPE_CHANGE`: child stopped because the packet boundary no longer fits;
  terminal.
- `FAILED`: child stopped after an execution or validation failure; terminal.
- `COMPLETE`: child met its acceptance criteria and stopped; terminal.
If callback delivery fails or a child terminates silently, the immediate parent
owns one bounded reconciliation, restores the upward notification, and does not
wait for the project owner to ask for status.

Prefer a native blocking/event wait and keep coordinators idle between events.
If repeated checks or an uncertain-duration
wait is unavoidable, dispatch exactly one fresh low-context read-only Luna Low
or Medium
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

Keep routine packets near 1,000–2,000 tokens and link durable evidence instead
of copying it. Measure first-pass acceptance, repeated causal failures, repair
rounds, elapsed time, escaped defects, and coordinator rework. Use exact usage
only when exposed; otherwise mark it unavailable and use stable proxies. Public
API price ratios are directional only and are never Codex subscription quota.
Compaction is short-term pressure relief; after roughly 20–30 turns or two
compactions, checkpoint and continue from a fresh task at a safe boundary.

Luna reports to Terra when Terra dispatched it, otherwise directly to Sol;
Terra reports to Sol; Sol reports to root. The receiving coordinator reviews
evidence, resolves conflicts, integrates within authority, and updates durable
state. Classify new ideas without silently widening scope. P0/P1 findings block completion;
P2/P3 findings receive an explicit fixed, accepted, or deferred disposition.

## CI and release economy

Follow [execution-efficiency.md](execution-efficiency.md). Measure completed job-minutes and event duplication before changing workflows. Prefer path-based tiers, explicit exhaustive matrices, one exact-candidate broad proof, and a stable required sentinel. Post-merge reuse must prove exact tree identity and successful required checks; otherwise run the full tier.
