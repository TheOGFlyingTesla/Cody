# Quick start

This is the smallest useful pass through Cody. Start from an extracted verified
release bundle. It is intentionally explicit so you can stop before any
mutation.

## 1. Preview the user-scoped installation

```bash
python3 scripts/install_skill.py --release-root . --check
```

The supported discovery scope is `$HOME/.agents/skills/cody-coordinator`.
This project does not establish a repository-scoped installation path.

## 2. Install and verify the discovery path

```bash
python3 scripts/install_skill.py --release-root .
python3 scripts/install_skill.py --release-root . --verify-discovery
```

The verification command must report the `user-agents-home` installation scope
and the `HOME/.agents/skills/cody-coordinator` discovery path. It does not print
the local home path. On an unsupported secure filesystem platform, it fails
closed rather than attempting another scope.

This verifies the installed filesystem path, not a running Codex process's
refreshed skill catalog. Restart or refresh Codex if needed, then invoke
`$cody-coordinator` to confirm product-level discovery.

## 3. Invoke Cody, inspect, and preview initialization

Invoke `$cody-coordinator` in the Codex task that will own coordination. The
skill resolves its own installed `SKILL_ROOT` and runs its tooling from there.
Keep talking to this task as the project's primary coordinator. It maintains
the durable state and may route bounded work to Sol/Terra/Luna tasks without
requiring you to carry messages between them.

For example:

```text
$cody-coordinator
Take over as coordinator for /absolute/path/to/project. Inspect first, tell me
where we stand, and plan the next safe outcome.
```

For a separate manual CLI smoke, remain in the extracted bundle root and run:

```bash
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format human inspect
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format human init --check
```

Confirm that the reported repository is the one you meant to inspect. Treat
unknown paths, identity conflicts, and unverified task claims as blockers.
`init --check` is read-only; it does not authorize later changes by itself.

## 4. Initialize and validate

```bash
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format human init
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format human doctor
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format human check-current
```

The doctor result is the useful handoff point: it tells a replacement
coordinator whether the repository contract is structurally sound.

## 5. Continue with a bounded request

When using Cody through a Codex-compatible skill surface, useful requests are
specific about the desired outcome and boundary. For example:

```text
Set up this repository with its coordinator standard.
Upgrade this repository to its current coordinator standard.
Take over as coordinator for this repository.
Where do we stand?
```

The coordinator should inspect first, keep one active work item, and report
authority or evidence blockers instead of guessing.

For a simple implementation slice, Sol coordinates and Luna performs the
bounded work. For a fixed multi-stage Green/Amber outcome, Sol may ask Terra to
decompose bounded Luna work. Sol still reviews the evidence and every resulting
diff. This keeps the expensive coordinator context compact while workers receive
only the information their slice needs.

## 6. Recover deliberately

For an interrupted run, start with the read-only picture:

```bash
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format json reconcile
```

Only choose a recovery action after reconciling the current Git state, durable
journal, and file hashes. Recovery is not a general-purpose undo command.

## Source evaluation is separate

If you only want to evaluate a source checkout, do not run its installer.
Follow [Installation: Evaluate a source checkout](INSTALLATION.md#evaluate-a-source-checkout)
instead; a checkout is not a generated bundle or a discovered installed skill.

## Stop conditions

Stop and ask for direction if the target path is wrong, identity is unclear,
the current state conflicts with a journal, or the next action would touch
secrets, providers, billing, deployment, production, commit history, or a real
recipient.
