# Execution Efficiency

## Measure before optimizing

For repositories with CI or release automation, measure completed job-minutes, triggers, retries, matrices, setup tax, and failed pre-effect attempts before changing the proof shape. Report skipped and self-hosted work separately. Wall time, runner setup, duplicate events, and matrix fan-out matter more than test count.

## One proof per exact candidate

Keep one broad proof for the exact release candidate. A pull-request proof may satisfy the corresponding post-merge tier only when automation proves the merged commit has the exact same Git tree and required checks completed successfully. Direct pushes, squash commits, conflict resolutions, missing check evidence, or tree mismatches require the full tier.

When evidence shows that the project already has a hosted CI surface, keep a
small independent required sentinel there. Otherwise record hosted CI as
unavailable and use the project's evidence-discovered local or self-hosted proof
surface. Route exhaustive deterministic suites to an explicit isolated
execution procedure when one is proven. Record candidate SHA, tree SHA,
command, mode, result, and cleanup. Contracts-only or partial harness checks never substitute for release certification.

Exhaustive matrices are opt-in unless changed paths exercise their distinct risk. Documentation-only changes may skip product suites when a stable required sentinel proves the classification. Cache dependencies where safe, but never cache mutable databases, credentials, or unverified build outputs.

## Prevent cheap operational failures

Before a remote diagnostic or release mutation:

1. validate scripts locally, including the exact shell and module-loading form;
2. derive the candidate from the immutable merged commit, then re-read every required direct and workload SHA pin; fail before mutation when any pin differs and expose only the approved correction path;
3. prove service, environment, candidate, schema, and provider/config readiness; external-runtime or provider ambiguity fails closed rather than assuming a vendor or target;
4. use a tested dependency-closed drain/resume operation when background work must stop;
5. record a structured attempt with stage, candidate, effect count, terminal status, and safe failure code.

Commit and push never certify deploy pins. The post-merge preflight owns pin verification immediately before the deploy call.

A proven pre-effect tooling failure may continue with a materially corrected attempt under the same authority and target. Never retry an unchanged failure. Production, destructive data, schema, secret, billing, or identity ambiguity requires its own authority.

## Keep coordination compact

Write durable status only at meaningful state transitions. One owner writes the active truth; registries and dashboards link to it instead of copying narratives. Prefer one worker and one reviewer, bounded tool output, visible task ownership for critical work, required direct upward callbacks, event-driven check-ins, and structured memos instead of copied transcripts.

Treat model routing as measured resource control. Sol Medium is the persistent
judgment, synthesis, P0/P1, and release owner. Terra Medium is the default
class-level writer and independent reviewer; Terra High is for interacting
state machines, uncertain causes, or a failed class repair. Luna Low/Medium
handles waiting and repetitive operations, while Luna High runs deterministic
proof, dogfood/evals, and exact-oracle edits. Luna never owns ambiguous runtime
repair, architecture, privacy/security judgment, P0/P1, or release. Escalate
Sol or Terra effort only when representative evidence shows the lower setting
lacks necessary judgment. Set model and effort explicitly. Model names never
broaden authority, and this topology governs Codex task orchestration only.

Count prompt and synthesis overhead, retries, rejected packets, duplicated
context, waiting, consultation, and final Sol review together. Measure
first-pass acceptance, repeated causal failures, repair rounds, elapsed time,
escaped defects, and coordinator rework. Record exact tokens or credits only
when exposed; otherwise mark them unavailable and use stable proxies. Public
API prices and ratios are directional evidence only, never Codex subscription
quota. Store one compact `routing_efficiency` receipt and keep a route only when
total consumption falls without increasing defects or Sol rework.

Do not impose a numeric repair-round cutoff. Default repair is Sol invariant →
Terra RED→GREEN class repair → independent Terra review when needed → Luna
production-shaped proof → Sol disposition. Skip unnecessary layers. Reslice or
escalate when the same causal failure repeats, a class repair fails again, or
the packet becomes ambiguous. A cheaper worker that creates another repair
round is not a saving.

Count any post-dispatch interactive approval request as a setup failure. Background work starts from a managed, exact, approval-independent state; stale identity returns `BLOCKED` rather than waiting for the project owner.

## Waiting and polling budget

Waiting is execution, not coordination. Prefer a native blocking/event wait.
When only polling is available or the wait may span multiple checks, create
exactly one fresh low-context read-only Luna Low/Medium waiter. It receives no broad
project history, mutation authority, or release authority; verifies only named
targets; uses native waits or adaptive backoff; enforces a wall-clock horizon;
and returns one compact `READY_FOR_REVIEW`, `BLOCKED`, `FAILED`, or `COMPLETE`
event. The coordinator may perform one initial read and one terminal spot-check;
unchanged repeated checks are a coordination defect.

Compaction remains encouraged for short-term pressure relief. A compacted coordinator task must not resume routine polling with restored history. After about 20–30 turns or two compactions, checkpoint and rotate at the next safe boundary.

Prune or archive only worktrees proven terminal and clean. Track efficiency over a bounded window with measured CI minutes, duplicate proof avoided, failed pre-effect attempts, review fan-out, and coordinator/status write count.
