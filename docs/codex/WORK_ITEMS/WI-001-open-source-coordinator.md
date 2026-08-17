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

Transplanted from reviewed source candidate
`4e758adea6390f333eee6eb737fdeb634deb364d` onto the clean public history.
Orientation, the Terra/Luna portability audit, and a privacy-safe ChatGPT Pro
consultation are complete.
The frozen design is a clean, coordinator-only, provider-neutral root skill;
the private predecessor compatibility layer has been removed. The current
uncommitted repair restores the explicit Sol Medium → Terra Extra High → Luna
High task-orchestration topology, takeover/current-version gates, recovery and
provider fail-closed boundaries, mandatory Sol review, executable contract
checks, and a normal-environment installer smoke. The full 152-test suite,
deterministic bundle build, isolated install, skill validation, doctor, blind
forward use, and focused independent re-review pass. The public candidate
commit, release replacement, hosted CI, and final published-SHA verification
remain pending.
