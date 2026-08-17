# Contributing to Cody

Thanks for helping make repository coordination safer and more portable. Cody
plugin v0.1.1 is a community preview shipping coordinator standard v0.1.0, so
clear evidence and modest claims are more useful than broad promises.

## Before you start

Read the [README](README.md), [Safety](docs/SAFETY.md), and
[Limitations](docs/LIMITATIONS.md). Do not include credentials, private paths,
hostnames, account identifiers, private transcripts, or provider-specific
defaults in issues, examples, tests, or documentation.

For a focused change:

1. Create a branch from the current default branch.
2. Keep the change scoped and preserve unrelated work.
3. Add or update tests when behavior changes.
4. Run the smallest meaningful local checks before opening a pull request.
5. Explain what was verified, what remains unknown, and any portability impact.

## Local checks

The project uses the Python standard library for its coordinator tooling. From
the repository root, run:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/coordinator_standard.py --repo "$PWD" --format json inspect
git diff --check
```

Use `python` instead of `python3` where that is the local interpreter name.
Documentation-only changes still run the repository test workflow; there are no
path filters that can silently skip runtime proof.

## Pull requests

Keep pull requests small enough to review. The description should include:

- the user-facing outcome;
- files or surfaces changed;
- exact validation commands and results;
- security, privacy, and cross-platform considerations; and
- any follow-up that is intentionally out of scope.

Do not commit generated archives, local coordinator state, or secret-bearing
configuration. A maintainer may request a focused reproducer or a portability
test before merging.

## Scope boundaries

Contributing code does not authorize changes to deployment, billing, provider
settings, repository secrets, production systems, or external communications.
Those actions require separate project authority and are outside normal pull
requests.

Please follow the [Code of Conduct](CODE_OF_CONDUCT.md). For vulnerabilities,
use the private process in [SECURITY.md](SECURITY.md), not a public issue.
