# Decision Log

Append durable product, architecture, safety, or operating decisions. Factual corrections may amend an entry; superseding decisions must link the prior entry.

## Decisions

### 2026-08-15 — Public release uses a clean, provider-neutral export

- Decision: Publish Cody as a clean coordinator-only export with the skill at
  the repository root, a compact `SKILL.md`, detailed referenced contracts, a
  single portable Python runtime, optional capability adapters, and ignored
  local state. Do not publish the private source history or the separate
  unrelated companion packages.
- Reason: Both the Terra/Luna audit and the completed ChatGPT Pro consultation
  found identity and environment assumptions bound into package names,
  migrations, release tooling, fixtures, shell behavior, and prose. A clean
  allowlisted export preserves the safety model without carrying private
  history or pretending that unproved provider adapters are supported.
- Owner: Project owner.
- Affected scope: Repository layout, package identity, runtime, installer,
  migrations, release tooling, tests, examples, and public documentation.
- Supersedes: None

### 2026-08-15 — Portability claims are capability- and proof-based

- Decision: The core requires Git and Python 3.11+ and supports local
  coordination without any hosting, database, secret-manager, deployment, CI,
  remote-compute, or ChatGPT dependency. Optional capabilities default to
  disabled or absent and must identify an exact adapter and target. Native
  Windows support is claimed only for operations covered by a separately proved
  secure backend; unsupported security primitives fail closed.
- Reason: Provider substitution and syntax compatibility are not evidence of
  safe support. Cody's approval, revision, receipt, migration, and recovery
  invariants must remain stronger than any individual integration.
- Owner: Project owner.
- Affected scope: Configuration, onboarding, platform layer, adapters, tests,
  support matrix, and release claims.
- Supersedes: None

### 2026-08-15 — External consultation evidence is privacy-safe and advisory

- Decision: Record consultation purpose, surface/mode, prompt digest,
  completion state, conclusions, and unresolved risks, but do not publish
  browser-account details or private transcript links. The 2026-08-15 Pro review
  completed naturally after 9m55s for prompt SHA-256
  `621638868556e9b192264ac2c822ef25d5506864055db97626166f2816f17a32`.
- Reason: Consultation strengthens review evidence but cannot replace source
  inspection, executable validation, or authoritative program documentation.
- Owner: Project owner.
- Affected scope: Release evidence, architecture decisions, and application
  preparation.
- Supersedes: None

### 2026-08-15 — Consultation is optional and capability-based

- Decision: Cody's core coordinator must not require ChatGPT Pro. When an
  external ChatGPT consultation is useful and authorized, prefer a visibly
  available Pro mode; otherwise use the strongest available ChatGPT/GPT-5.6
  model at its highest supported reasoning level. If no consultation surface is
  available, continue with the local coordinator and report that consultation
  evidence is unavailable.
- Reason: Public users have different plans and model access; optional decision
  support must not become an installation or execution dependency.
- Owner: Project owner.
- Affected scope: Skill routing policy, onboarding, configuration, examples,
  validation, and documentation.
- Supersedes: None

### 2026-08-15 — Public v0.1.0 excludes private predecessor compatibility

- Decision: Remove the private predecessor migration engine, format detection,
  rollback encoding, CLI options, documentation, and synthetic fixtures from
  Cody's public source and release bundle. Preserve the generic initialization,
  versioned upgrade, journaling, recovery, and validation framework.
- Reason: New public users have no dependency on an unpublished private format,
  and carrying it would confuse Cody's public version identity and expose
  irrelevant historical implementation detail.
- Owner: Project owner.
- Affected scope: Runtime, schemas, tests, references, release allowlist, and
  compatibility claims.
- Supersedes: None

### 2026-08-15 — Public routing preserves the proven coordinator topology

- Decision: Cody names Sol Medium as the primary coordinator, reviewer, and
  release owner; Terra Extra High as an optional bounded junior coordinator for
  fixed multi-stage Green/Amber work; and Luna High as the default scout,
  worker, executor, and waiter. Simple work routes directly from Sol to Luna.
  Model names describe the current capability map and never grant authority;
  unavailable names use the nearest capable route while preserving the same
  control, escalation, and review boundaries.
- Reason: Removing the named topology during provider-neutralization changed
  Cody's observable coordination behavior and erased the token-efficient
  junior-coordinator path proven by the source standard.
- Owner: Project owner.
- Affected scope: Skill triggering, task lifecycle, orchestration, waiting,
  recovery, efficiency measurement, templates, documentation, and behavioral
  tests.
- Supersedes: The unnamed-routing portion of “Portability claims are
  capability- and proof-based”; all provider-neutral and proof-based boundaries
  remain in force.

### 2026-08-16 — Unavailable named coordinator models fail closed

- Decision: If a declared Sol, Terra, or Luna model is unavailable, Cody reports
  the unavailable model and returns `SCOPE_CHANGE`. It never chooses a nearest
  or silent substitute. Substitution is unsupported in v0.1.0; changing the
  declared topology requires a future contract revision.
- Reason: A silent capability substitution makes the public skill behave
  differently from its declared topology and can change cost or review quality
  without informed approval.
- Owner: Project owner.
- Affected scope: Routing contract, skill instructions, managed repository
  contract, documentation, and behavioral checks.
- Supersedes: The unavailable-model fallback in “Public routing preserves the
  proven coordinator topology.”

### 2026-08-20 — Visible task ownership and automatic upward fan-in

- Decision: Standard 0.2.0 makes visible Codex tasks the owners of critical
  milestones and uncertain waiting. Every child dispatch packet carries its
  exact parent task ID/host and mandatory typed callbacks; the immediate parent
  owns one bounded reconciliation after missing notification.
- Reason: Completion must reach Luna → Terra → Sol → root automatically without
  making the project owner relay messages or repeatedly ask for status.
- Owner: Project owner.
- Affected scope: Skill instructions, routing contract, dispatch packet schema
  and validator, managed repository template, plugin runtime, migration path,
  documentation, and behavioral tests.
- Supersedes: The less explicit task-mesh language in standard 0.1.0.

Use this entry shape:

```text
### YYYY-MM-DD — Decision title
- Decision:
- Reason:
- Owner:
- Affected scope:
- Supersedes: None
```
