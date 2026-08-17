# Coordinator Status

Checkpoint recorded: 2026-08-17T00:52:14Z
Freshness: current during hosted CI repair

## Current exact identity and deploy truth

- Coordinator Standard: `0.1.0`
- Observed branch: `codex/release-v0.1.0`
- Published candidate: `origin/main` and `v0.1.0` point to
  `a813ea67c225a2f4a181abb8dbc91f538767fd61`.
- Release assets at `v0.1.0` are byte-identical to the locally certified ZIP
  and checksum file.
- Working tree: bounded Windows CI assertion-harness repair plus its regression
  test and refreshed checkpoint.

## Active task IDs

- `WI-001` — open-source the coordinator skill.

## Open P0/P1

- Hosted Windows preview failed because its `cmd.exe` `%ERRORLEVEL%` assertion
  chain did not preserve stage evidence. Product tests on Ubuntu/macOS passed;
  the repair replaces the shell chain with one diagnostic Python harness.

## Authority or decision blocker

- The project owner explicitly authorized committing all candidate files,
  rebuilding from the committed tree, publishing to public `main`, replacing
  `v0.1.0`, updating GitHub copy/metadata, and verifying hosted CI and release
  assets. The official Deep Security Scan remains explicitly deferred and must
  not be represented as completed.

## One next action

Commit the bounded CI repair, rebuild and replace the exact release assets from
that commit, then require successful main and tag CI readback.
