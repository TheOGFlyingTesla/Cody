# Governance

Cody is an independent community project. It is not an OpenAI project and is
not affiliated with or endorsed by OpenAI.

## Decision principles

Maintainers use the following principles when reviewing changes:

1. Preserve user authority and fail closed when identity, paths, or scope are
   ambiguous.
2. Prefer evidence from the repository, Git, and executable validation over
   assumptions or marketing language.
3. Keep the core provider-neutral and portable.
4. Make security, privacy, recovery, and idempotence part of the design.
5. Keep public claims narrower than the proof available in the repository.

## Maintainers

The [maintainer record](MAINTAINERS.md) and repository settings identify the
current people with merge and release authority. A maintainer may request
changes, reject unsafe scope, or pause a contribution while evidence is
collected.

## Changes to the project

Routine fixes may land through reviewed pull requests. Changes to safety
invariants, supported platforms, release policy, or governance should explain
the tradeoff and include updated documentation and validation. Releases are
made only after the checklist in [RELEASES.md](docs/RELEASES.md) is complete.

This document does not grant permission to change deployment, billing,
provider settings, secrets, or production systems.
