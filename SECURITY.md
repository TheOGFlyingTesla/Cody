# Security policy

Cody handles project state and may be used alongside powerful coding tools. A
security issue can therefore include unsafe path handling, credential exposure,
authority bypass, data loss, or a workflow that executes with more access than
documented.

## Supported security boundary

The `v0.1.x` preview line is the only public line currently described here.
There is no promise of a response time or a paid security program.

## Reporting a vulnerability

Please do not open a public issue with exploit details. Use GitHub's private
vulnerability-reporting or private maintainer contact features for this
repository. If no private channel is available, open a minimal public issue
asking for a private channel and do not include the vulnerable input, secret, or
reproduction details.

Include only the information needed to reproduce the issue privately: affected
version or commit, platform, prerequisites, impact, and a minimal reproducer.
Redact credentials, tokens, account identifiers, private paths, and personal
data before sending anything.

## Release safety

Contributors should not add secrets to examples, fixtures, workflow files,
logs, or documentation. CI uses no repository secrets and does not deploy. See
[Safety](docs/SAFETY.md) for the fail-closed design and
[Release guide](docs/RELEASES.md) for pre-publication checks.
