# Cody — Codex Coordinator

![Cody coordinating three bounded work streams](assets/cody-social-preview.jpg)

![Preview](https://img.shields.io/badge/status-v0.1.0%20preview-7c3aed)
![License](https://img.shields.io/badge/license-MIT-2563eb)

Cody is a small, portable coordination layer for Codex-compatible repository
workflows. It keeps project state legible, turns broad requests into bounded
work, and makes safety boundaries part of the operating model.

> Cody is an independent community project. It is not affiliated with,
> sponsored by, or endorsed by OpenAI. This repository is a v0.1.0 preview;
> interfaces and support claims may change.

## Why Cody?

Coding agents are good at producing changes. Long-lived project work also needs
orientation, durable checkpoints, explicit authority, and a clean recovery path.
Cody provides a repository-local control plane for that work:

- inspect a repository before making assumptions;
- initialize or upgrade a compact `docs/codex/` contract;
- keep status, decisions, roadmap, and work items durable;
- validate structure with a deterministic doctor;
- recover interrupted coordination without guessing at bytes or authority; and
- make commit, push, deploy, provider, billing, and secret actions explicit.

The core is local and provider-neutral. It does not require a hosted service,
database, secret manager, deployment target, remote compute host, or ChatGPT
subscription.

## Coordination boundaries

The task that invokes `$cody-coordinator` is the repository's coordinator;
Cody never creates a second coordinator by implication. The documented routing
shape is Sol Medium for coordination, review, and release authority; direct
Sol-to-Luna for a simple bounded slice; and optional Sol-to-Terra-to-Luna for a
fixed multi-stage Green/Amber slice. Terra returns `SCOPE_CHANGE` for Red work
or authority/risk drift, while Sol retains final authority. Provider or
external-runtime ambiguity, unknown deploy pins, and unavailable consultation
evidence fail closed rather than selecting an assumed target or substitute.
These names describe Codex task orchestration only; Cody never selects an
application's, provider's, customer-facing, or production inference models.

## Quick start

Prerequisites are Python 3.11 or newer and Git 2.39 or newer. From a checkout:

```bash
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format human inspect
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format human init --check
```

Review the check result before allowing a mutating initialization:

```bash
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format human init
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format human doctor
```

The `init` command can create or update coordinator-owned files and writes a
durable migration receipt. Read [Installation](docs/INSTALLATION.md) and
[Safety](docs/SAFETY.md) before using it on a non-empty project.

## Documentation

- [Installation](docs/INSTALLATION.md) — source checkout evaluation and verified release bundles
- [Quick start](docs/QUICKSTART.md) — the first safe repository pass
- [Configuration](docs/CONFIGURATION.md) — repository state, flags, and local paths
- [Portability](docs/PORTABILITY.md) — platform support and fail-closed boundaries
- [Safety](docs/SAFETY.md) — authority, redaction, idempotence, and recovery
- [Limitations](docs/LIMITATIONS.md) — what this preview does not promise
- [Behavioral checks](docs/BEHAVIORAL_CHECKS.md) — executable evidence behind key claims
- [Adoption and feedback](docs/ADOPTION.md) — privacy-preserving evidence rules
- [Release guide](docs/RELEASES.md) — versioning, proof, and publication checklist
- [Codex for Open Source application](docs/CODEX_FOR_OSS.md) — factual evidence checklist and draft language
- [Contributing](CONTRIBUTING.md) — changes, tests, and review expectations
- [Security](SECURITY.md) — private vulnerability reporting guidance
- [Support](SUPPORT.md) — questions, bug reports, and useful diagnostics

## Runtime commands

The current command-line entry point is `scripts/coordinator_standard.py`:

```text
inspect        Read-only repository inspection
init            Set up the current coordinator standard
upgrade         Upgrade an existing coordinator repository
doctor          Validate the complete repository contract
reconcile       Read-only interrupted-run recovery picture
recover         Perform an explicitly selected recovery action
check-current   Report current-version and structural status
```

Use `--format json` for automation. Use an explicit absolute `--repo` path when
running from outside the target project. Debug output is redacted, but it is
still best to review diagnostics before sharing them.

## Project status

This is a preview, not a hosted product or a compatibility guarantee. The
repository is intentionally conservative about claims while the public package
layout and cross-platform installer hardening continue to settle. See
[Limitations](docs/LIMITATIONS.md) for the current boundary.

If you are evaluating Cody alongside OpenAI's community programs, use the
[official Codex for Open Source page](https://developers.openai.com/community/codex-for-oss)
for current program information. Cody makes no claim of eligibility and the
link does not imply affiliation or endorsement.

## License

Cody is released under the [MIT License](LICENSE).
