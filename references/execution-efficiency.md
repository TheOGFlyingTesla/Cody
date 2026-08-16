# Execution Efficiency

## Measure before optimizing

For repositories with CI or release automation, measure completed job-minutes, triggers, retries, matrices, setup tax, and failed pre-effect attempts before changing the proof shape. Report skipped and self-hosted work separately. Wall time, runner setup, duplicate events, and matrix fan-out matter more than test count.

## One proof per exact candidate

Keep one broad proof for the exact release candidate. A pull-request proof may satisfy the corresponding post-merge tier only when automation proves the merged commit has the exact same Git tree and required checks completed successfully. Direct pushes, squash commits, conflict resolutions, missing check evidence, or tree mismatches require the full tier.

Keep a small independent required sentinel on the hosted CI service. Route exhaustive deterministic suites to an explicit isolated execution procedure when one is proven. Record candidate SHA, tree SHA, command, mode, result, and cleanup. Contracts-only or partial harness checks never substitute for release certification.

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

Write durable status only at meaningful state transitions. One owner writes the active truth; registries and dashboards link to it instead of copying narratives. Prefer one worker and one reviewer, bounded tool output, event-driven check-ins, and structured memos instead of copied transcripts.

Treat model routing as measured resource control. Sol Medium is the primary
coordinator, reviewer, and release owner; a simple packet goes Sol-to-Luna.
For a fixed multi-stage Green/Amber packet, Sol may route
Sol-to-Terra-to-Luna, where Terra Extra High is a bounded junior coordinator and
Luna High performs bounded scout, worker, executor, or waiter work. Terra
returns `SCOPE_CHANGE` for Red discovery or risk/authority drift. Model names
never broaden authority and unavailable names use the nearest capable route.
This topology governs Codex task orchestration only, never application or
provider-runtime model routing. Sol reviews 100% of Terra conclusions and every
resulting diff.

Count prompt and synthesis overhead, retries, rejected packets, duplicated
context, waiting samples, optional consultation, and final review by Sol together.
Record exact token or credit usage when exposed; otherwise mark it unavailable
and measure packet/output bytes, turns, reasoning level, compactions, elapsed
time, repair rounds, and reloaded coordinator context. Store a compact
`routing_efficiency` receipt with the topology, usage availability, proxies,
repairs, disagreements, incidents, and outcome. Keep the route only when total
consumption falls without increasing defects, gate disagreement, or coordinator
rework.

Do not impose a numeric repair-round cutoff. Continue review and repair while the failing set shrinks or new proof closes a named finding. Reslice or escalate when the same causal failure repeats without progress, a class-level repair fails again, or the packet becomes ambiguous.

Count any post-dispatch interactive approval request as a setup failure. Background work starts from a managed, exact, approval-independent state; stale identity returns `BLOCKED` rather than waiting for the project owner.

## Waiting and polling budget

Waiting is execution, not coordination. Prefer a native blocking/event wait.
When only polling is available or the wait may span multiple checks, create
exactly one fresh low-context read-only Luna High waiter. It receives no broad
project history, mutation authority, or release authority; verifies only named
targets; uses native waits or adaptive backoff; enforces a wall-clock horizon;
and returns one compact `READY_FOR_REVIEW`, `BLOCKED`, `FAILED`, or `CANCELLED`
event. The coordinator may perform one initial read and one terminal spot-check;
unchanged repeated checks are a coordination defect.

Compaction remains encouraged for short-term pressure relief. A compacted coordinator task must not resume routine polling with restored history. After about 20–30 turns or two compactions, checkpoint and rotate at the next safe boundary.

Prune or archive only worktrees proven terminal and clean. Track efficiency over a bounded window with measured CI minutes, duplicate proof avoided, failed pre-effect attempts, review fan-out, and coordinator/status write count.
