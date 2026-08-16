# Changelog

All notable public-project changes are recorded here. Cody is currently in
preview, so this log describes the repository surface rather than promising a
stable API.

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

### Known boundaries

- The source checkout and a generated release bundle are distinct shapes. The
  verified skill installer is intended for the latter.
- Optional provider, remote-compute, deployment, database, and secret-manager
  adapters are not part of this preview.
- Unpublished private predecessor formats are not supported by this public
  release.
- Windows mutation and installer support remains capability-dependent and fails
  closed when required filesystem primitives are unavailable.
