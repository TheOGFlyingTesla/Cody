# cody — Cody Codex Coordinator

## Purpose

Public home for the Cody Codex Coordinator repository.

## Current product shape

An in-progress open-source distribution of a durable Codex repository
coordinator skill. The public package is a clean, provider-neutral export.

## Repository map

- Repository root: current checkout.
- `docs/codex/`: repository coordination records.
- Public root skill, runtime, tests, references, examples, and community docs.

## Technology and runtime

- Python 3 standard-library coordinator tooling.
- Markdown skill, reference, template, and community documentation.

## Validation commands

- `python3 -m unittest discover -s tests`
- `python3 scripts/coordinator_standard.py --repo . --format json doctor`
- `git diff --check`

## Generated files and ownership boundaries

- Coordinator-owned: the managed block in `AGENTS.md` and `docs/codex/`.
- Product generated-file boundaries: Unknown — inspect before relying on this field.

## Deployment shape

No application deployment is configured. The repository is hosted publicly on
GitHub. Do not record credentials here.

## Authority and risk

- Public-release privacy risk: personal identity, credentials, account identifiers,
  hostnames, provider assumptions, and absolute paths must not enter the release.
- Portability risk: platform/provider examples must remain optional and explicit.
- Consultation is an optional adapter, not a runtime dependency; capability
  selection prefers Pro and otherwise the strongest available model/reasoning.

Commit, push, merge, deploy, secret, provider, billing, production, trading, and real-recipient actions require their own explicit authority.

## External systems

- GitHub: the public repository associated with this checkout.

## Unknowns

- Native Windows support remains gated on proof of a secure filesystem backend;
  unsupported install operations fail closed.
