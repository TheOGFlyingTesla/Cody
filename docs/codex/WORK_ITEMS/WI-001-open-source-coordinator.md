# WI-001 — Open-source the coordinator skill

## Problem

The source coordinator skill is proven in one environment but contains identity,
machine, path, provider, and workflow assumptions that make it unsafe and
awkward for other people to install.

## Desired outcome

Publish Cody as an attractive, MIT-licensed, installable Codex coordinator skill
that discovers or asks for a user's own project, platform, paths, providers,
secret manager, database, deployment target, and optional remote compute.

## Non-goals

- Preserve source-owner-specific defaults in the public runtime.
- Require macOS, an external drive, a remote workstation, or any named secrets,
  hosting, database, deployment, or infrastructure provider.
- Deploy an application or change secrets, billing, provider, or production state.
- Claim eligibility for an OpenAI open-source program without current evidence.

## Acceptance criteria

- The distributable skill contains no personal names, private paths, machine
  names, account identifiers, credentials, tokens, or credential-bearing fixtures.
- Environment-specific choices are discovered, configured, or left explicitly
  optional with fail-closed behavior; examples are clearly labeled as examples.
- ChatGPT consultation is optional: prefer Pro when available, otherwise use the
  strongest available GPT-5.6/ChatGPT model and highest supported reasoning
  level; lack of a consultation surface does not block core coordination.
- Installation and setup work on common macOS, Linux, and Windows/Python
  environments without assuming an external drive or Unix-only home layout.
- The repository includes a strong README, installation and quick-start guidance,
  configuration/reference documentation, contribution and security guidance,
  changelog/release information, and an MIT license.
- Existing coordinator safety, migration, recovery, validation, and idempotence
  behavior remains covered by automated tests.
- GitHub metadata and repository contents are ready for public sharing.
- Secret/personalization scans and independent review leave no open P0/P1.

## Constraints and authority

The project owner authorized transforming the source coordinator skill, making
this repository public under MIT, and publishing the reviewed shareable result.
The primary coordinator owns architecture, privacy/security, P0/P1 adjudication,
exact-diff review, and release. Junior coordinators may coordinate only fixed
Green/Amber portability and documentation work through bounded scouts/workers.
No deploy, provider, billing, production, secret mutation, or real-recipient
communication is authorized.

## Likely affected areas

- Public skill package, installer, templates, schemas, tests, and release tooling.
- README and supporting GitHub/community documentation.
- Repository metadata, examples, and CI validation.
- Coordinator project/status/roadmap records.

## Required validation evidence

- Full source inventory and personal/provider/platform/path audit.
- Unit and integration tests on the frozen candidate.
- Cross-platform/path-focused tests and install smoke tests.
- Secret scanning and deep security scan with generated report.
- Independent exact-diff review and coordinator doctor/no-op checks.
- Final Git/GitHub readback for the exact published SHA.

## Dependencies

- Privacy-safe ChatGPT consultation requested by the project owner.
- Read-only access to the current personal coordinator skill as source evidence.
- GitHub CLI/app access to the public repository associated with this checkout.

## Risks

- Personal assumptions may be hidden in fixtures, migration evidence, generated
  reports, paths, hostnames, or prose rather than obvious runtime configuration.
- Over-generalization could weaken fail-closed safety or make setup ambiguous.
- Public claims about OpenAI program eligibility may become stale and require
  authoritative verification before publication.

## Current disposition

The generic, provider-neutral coordinator skill is published at `v0.1.0` with
its checksum-verified offline installer. The current bounded follow-up packages
the same canonical runtime as the self-contained `cody-codex-coordinator`
plugin and adds the repository marketplace named `cody`. The public quick path
is marketplace installation from `main`, restart Codex, then explicitly invoke
`$cody-coordinator`; the existing `v0.1.0` tag is not claimed to contain plugin
packaging. Runtime mirroring is deterministic and byte-checked, and a copied
plugin black-box test proves the coordinator runs without its source checkout.
The plugin package is published on `main`; the incremental `v0.1.1` release
candidate now aligns the plugin manifest, public copy, changelog, and release
evidence while preserving coordinator standard `0.1.0` and the historical
skill-only `v0.1.0` tag. Publication awaits exact-diff review, exact committed-
candidate validation, a public-route clean install and invocation smoke, hosted
CI, and live GitHub readback. The deeper security scan remains deferred.
