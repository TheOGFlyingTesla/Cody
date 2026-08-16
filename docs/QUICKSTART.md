# Quick start

This is the smallest useful pass through Cody. It is intentionally explicit so
you can stop before any mutation.

## 1. Inspect

```bash
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format human inspect
```

Confirm that the reported repository is the one you meant to inspect. Treat
unknown paths, identity conflicts, and unverified task claims as blockers.

## 2. Preview initialization

```bash
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format human init --check
```

Read the proposed files and boundary decision. `init --check` is read-only; it
does not authorize later changes by itself.

## 3. Initialize and validate

```bash
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format human init
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format human doctor
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format human check-current
```

The doctor result is the useful handoff point: it tells a replacement
coordinator whether the repository contract is structurally sound.

## 4. Continue with a bounded request

When using Cody through a Codex-compatible skill surface, useful requests are
specific about the desired outcome and boundary. For example:

```text
Set up this repository with my current coordinator standard.
Upgrade this repository to my current coordinator standard.
Take over as coordinator for this repository.
Where do we stand?
```

The coordinator should inspect first, keep one active work item, and report
authority or evidence blockers instead of guessing.

## 5. Recover deliberately

For an interrupted run, start with the read-only picture:

```bash
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format json reconcile
```

Only choose a recovery action after reconciling the current Git state, durable
journal, and file hashes. Recovery is not a general-purpose undo command.

## Stop conditions

Stop and ask for direction if the target path is wrong, identity is unclear,
the current state conflicts with a journal, or the next action would touch
secrets, providers, billing, deployment, production, commit history, or a real
recipient.
