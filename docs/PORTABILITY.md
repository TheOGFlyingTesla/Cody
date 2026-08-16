# Portability

Cody aims to keep its core local and dependency-light. Portability claims in
this preview are capability- and proof-based rather than inferred from syntax.

## Baseline

- Python 3.11 or newer
- Git 2.39 or newer
- no third-party Python package required by the coordinator tooling
- no hosted service, database, provider, secret manager, deployment, or remote
  compute requirement

## Platform boundary

| Platform | Preview status | Boundary |
| --- | --- | --- |
| macOS | Primary local target | Use the standard Python and Git prerequisites. |
| Linux | Primary local target | Use a user-owned project and Codex home. |
| Windows | Read-only preview | Inspection is exercised in CI; coordinator mutation and secure skill installation fail closed because the required descriptor primitives are unavailable. |

The CI matrix exercises the complete Python 3.11 suite on Ubuntu and macOS.
A separate Windows job proves read-only inspection and the explicit
`unsupported_platform` mutation blocker. Green CI is useful evidence for the tested commands; it is not a promise that
every filesystem, Git configuration, shell, or security policy behaves the
same way on every machine.

## Path and shell guidance

Pass the repository explicitly with `--repo`. Avoid embedding personal paths in
issues, examples, or generated reports. On Windows, use the local Python
launcher and quote paths according to the active shell. The coordinator should
reject unsafe or ambiguous paths rather than normalize them into an unknown
target.

## What portability does not mean

Portability does not mean provider substitution, automatic remote execution, or
permission bypass. Unsupported security primitives are a reason to stop and
report a blocker, not a reason to weaken checks.
