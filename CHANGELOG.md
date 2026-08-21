# Changelog

All notable public-project changes are recorded here. Cody is currently in
preview, so this log describes the repository surface rather than promising a
stable API.

## [0.2.0] — 2026-08-21

### Visible task hierarchy and required upward fan-in

### Added

- Critical milestones and uncertain waiting remain owned by visible Codex
  tasks: root → Sol, optional Terra, then Luna.
- Dispatch packets structurally require exact parent task/host routing, direct
  typed callbacks, terminal notification, silent unchanged state, and one
  immediate-parent reconciliation after a missing callback.
- Packets also require the complete bounded-work contract: owned and forbidden
  paths, non-goals, authority and base identity, acceptance and validation
  requirements, stop conditions, and report format.
- A dependency-free dispatch packet generator/validator and schema.
- Packet parsing rejects duplicate JSON keys and malformed value types without
  leaking a traceback or accepting last-key-wins routing ambiguity.

### Version boundary

- Existing standard `0.1.0` installations and supported listed legacy versions
  `3.2.0` through `3.2.6` can explicitly upgrade to standard `0.2.0`.
- Cody plugin `0.2.0` ships coordinator standard `0.2.0`.

## [0.1.1] — Codex plugin packaging

### Added

- A repository marketplace named `cody` and the self-contained
  `cody-codex-coordinator` plugin.
- The standard public installation flow through `codex plugin marketplace add`
  and `codex plugin add`.
- The standard plugin invocation,
  `$cody-codex-coordinator:cody-coordinator`; `$cody-coordinator` remains the
  standalone/offline skill invocation.
- Deterministic source-to-plugin runtime synchronization, drift detection, and
  a black-box copied-plugin execution check.
- A release gate requiring exact public clean-install evidence from an isolated
  Codex profile before publication.

### Version boundary

- Cody plugin `0.1.1` ships coordinator standard `0.1.0`.
- The existing `v0.1.0` release remains the earlier checksum-verified,
  skill-only offline bundle and is not rewritten or represented as containing
  marketplace packaging.
- Windows plugin execution remains preview-level; hosted CI proves read-only
  fail-closed behavior, not a complete Windows plugin invocation.

## [0.1.0] — Preview

### Added

- Public README, installation, quick-start, configuration, portability, safety,
  limitations, behavioral-evidence, adoption, and release guidance.
- Community contribution, conduct, security, support, governance, maintainer,
  and third-party notices.
- GitHub issue and pull-request templates.
- A single read-only-permission GitHub Actions workflow with cancellation and a
  Python 3.11 matrix on Ubuntu, Windows, and macOS.
- A deterministic allowlisted release builder, checksum-bound installer,
  repository doctor, recovery journal, and executable behavioral checks.
- An explicit Codex skill workflow with one durable coordinator task and
  token-conscious Sol Medium → Luna High or Sol Medium → Terra Extra High →
  Luna High orchestration.

### Known boundaries

- The source checkout and a generated release bundle are distinct shapes. The
  verified skill installer is intended for the latter.
- Optional provider, remote-compute, deployment, database, and secret-manager
  adapters are not part of this preview.
- Unpublished private predecessor formats are not supported by this public
  release.
- Windows mutation and installer support remains capability-dependent and fails
  closed when required filesystem primitives are unavailable.
