# Coordinator Status

Checkpoint recorded: 2026-08-17
Freshness: current during Cody plugin publication

## Current exact identity and deploy truth

- Coordinator Standard: `0.1.0`
- Candidate branch: `codex/package-cody-plugin`, based on published
  `origin/main` commit `ab0111e4a9480338c4f0c57248c1c3bf10c42c1c`.
- Published `v0.1.0` remains the checksum-verified skill-only release and does
  not contain marketplace packaging.
- Candidate adds the `cody` marketplace and self-contained
  `cody-codex-coordinator` plugin on `main`; the documented install source is
  therefore `main` until a later release is explicitly published.

## Active task IDs

- `WI-001` — publish Cody as a generic installable coordinator.

## Open P0/P1

- None in local validation. Independent exact-diff review and hosted CI remain
  publication gates.

## Authority or decision blocker

- The project owner explicitly authorized committing and publishing the plugin
  package and updated GitHub installation instructions.
- The previously deferred Deep Security Scan remains deferred and must not be
  represented as completed.

## One next action

Close independent review, commit the exact candidate, rerun exact-SHA proof,
publish to `main`, and verify hosted CI plus live installation copy.
