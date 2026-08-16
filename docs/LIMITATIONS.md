# Limitations

Cody v0.1.0 is a preview. The following limits are intentional and should be
treated as part of the current contract.

- The source checkout is not automatically a generated release bundle.
- The verified skill installer expects the release bundle layout and checksums;
  it should not be pointed at an arbitrary source tree.
- The standard runtime and public project version are separate concepts: the
  repository's current coordinator standard is recorded by its own tooling,
  while the public project is v0.1.0 preview.
- Windows is not a blanket guarantee for secure mutation or installation; the
  implementation may fail closed where filesystem ownership or descriptor
  primitives are unavailable.
- There is no built-in hosted coordinator, API, database, deployment system,
  remote-compute adapter, secret manager, or provider integration.
- Optional ChatGPT or model consultation is not required for core coordination.
  Cody does not promise access to a particular model, plan, or reasoning mode.
- The repository contract does not replace project-specific policies, branch
  protection, code review, backups, or operational runbooks.
- A passing local check cannot prove that an external system, task surface, or
  provider is available. Unknown external state remains unknown.
- Preview releases may change command output, package shape, and supported
  platforms without a compatibility window.
- Unpublished private predecessor formats and their fixtures are intentionally
  outside the public compatibility contract.

If a use case depends on any of these capabilities, document it as a separate
proposal rather than assuming a silent fallback.
