# Repository Contract

The Codex Coordinator skill owns universal behavior. Each repository keeps only a thin portable project layer:

```text
AGENTS.md
docs/codex/STANDARD.json
docs/codex/PROJECT.md
docs/codex/STATUS.md
docs/codex/ROADMAP.md
docs/codex/DECISIONS.md
docs/codex/WORK_ITEMS/
docs/codex/MIGRATIONS/
```

## Ownership

Only the marked coordinator block in root `AGENTS.md` is managed. Preserve every byte outside it. More-specific nested instructions govern their subtrees. Duplicate, malformed, or nested managed markers block mutation. Template-placeholder and serialized-path validation applies to the managed coordinator block, not user-owned outside-block instructions; credential-shape scanning covers the complete file and never echoes a detected value.

`STANDARD.json` records schema/standard versions, stable project identity, timestamps, risk profiles, and ordered migrations. `PROJECT.md` stores durable project facts, discovered commands, boundaries, deployment shape without credentials, and unknowns. `STATUS.md` is the recovery checkpoint. `ROADMAP.md` is Now/Next/Later/Parked. `DECISIONS.md` is append-only durable rationale. Work items hold bounded problem, outcome, acceptance, authority, and validation context.

`STATUS.md` is the compact read-only recovery interface. Keep it near 2,000 tokens or less and retain only checkpoint/freshness, exact identity and deploy truth, active task IDs, open P0/P1, authority or decision blocker, and one next action. Completed history belongs in one linked terminal record. The recovery cache never outranks repository evidence.

Operational documents use progressive disclosure. `STATUS.md` and the active work item are routine entry points; registries, WIP ledgers, handoff manifests, plans, and historical decisions are routed evidence, not a mandatory reading set. Large hand-maintained documents expose a compact index and link narrow appendices. Generated migration journals, immutable reports, and other cold evidence remain byte-stable unless a scoped migration requires otherwise.

Every mutating coordinator run has an atomic JSON journal and terminal human report under `MIGRATIONS/`. Journals contain relative paths and hashes, never raw secret values or absolute local paths.

## Validation commands

From the installed skill root:

```bash
python3 scripts/coordinator_standard.py --repo /explicit/repo --format json inspect
python3 scripts/coordinator_standard.py --repo /explicit/repo --format json check-current
python3 scripts/coordinator_standard.py --repo /explicit/repo --format json doctor
python3 scripts/coordinator_standard.py --repo /explicit/repo --format json reconcile
```

Doctor checks repository safety, schema subset, markers, required paths/sections, STATUS compactness, placeholders and local paths, credentials, journal/report/authority/reversal consistency, status correlation, managed scope, and render stability. Completed setup or upgrade must pass doctor and a repeated check-mode run with no changes.
