# Coordinator Status

Checkpoint recorded: 2026-08-17
Freshness: current during Cody plugin v0.1.1 release

## Current exact identity and deploy truth

- Coordinator standard: `0.1.0`.
- Published `origin/main`: `ca55ef6e5de3a88e510c2d1c29f23f8d00da1a8d`.
- Published `v0.1.0`: `ab0111e4a9480338c4f0c57248c1c3bf10c42c1c`,
  the checksum-verified skill-only release.
- Candidate branch: `codex/release-v0.1.1`.
- Candidate product boundary: Cody plugin `0.1.1` ships coordinator standard
  `0.1.0`; `v0.1.0` remains unchanged and is not claimed to contain plugin
  packaging.

## Active task IDs

- `WI-001` — publish Cody as a generic installable coordinator.

## Open P0/P1

- None. Public installation and plugin discovery succeeded at `ca55ef6`, but
  the smoke proved plugin skills require the plugin namespace. Correcting the
  documented invocation, exact committed-candidate proof, independent review,
  hosted CI, tag publication, and release readback remain publication gates.

## Authority or decision blocker

- The project owner explicitly authorized completing and publishing the
  incremental `v0.1.1` plugin release.
- The previously deferred Deep Security Scan remains deferred and must not be
  represented as completed.

## One next action

Correct the plugin invocation, validate and independently review the bounded
diff, commit it, certify the exact SHA, publish `main` and `v0.1.1`, then verify
public installation and hosted CI.
