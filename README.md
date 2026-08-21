# Cody — Codex Coordinator

![Cody coordinating three bounded work streams](assets/cody-social-preview.jpg)

![Version](https://img.shields.io/badge/version-v0.2.0-7c3aed)
![License](https://img.shields.io/badge/license-MIT-2563eb)

Cody is a **Codex plugin** that provides the explicit
`$cody-codex-coordinator:cody-coordinator` skill. It turns
one Codex task into the coordinator for a repository. You talk to that
coordinator about outcomes, status, priorities, and blockers; Cody keeps the
project state durable and routes bounded implementation or research to cheaper
worker tasks when useful.

> Cody is an independent community project. It is not affiliated with,
> sponsored by, or endorsed by OpenAI. Cody remains a preview project;
> interfaces and support claims may change between `0.x` releases.

## What Cody does

Ordinary coding tasks lose context, duplicate work, or make the project owner
carry messages between agents. Cody provides a repository-local control plane:

- one long-lived root/portfolio coordinator task that you can return to
  throughout the project;
- inspection before action, with the exact repository and Git state verified;
- durable status, decisions, roadmap, work items, and recovery evidence under
  `docs/codex/`;
- bounded worker and reviewer packets instead of repeatedly loading the full
  project history;
- deterministic validation and interrupted-work recovery; and
- explicit boundaries around commit, push, deploy, secrets, billing, providers,
  and production systems.

The core is local and provider-neutral. It does not require a hosted service,
database, secret manager, deployment target, remote compute host, or ChatGPT
subscription.

## How you use it

After installing Cody, open the Codex task that should become the project's
long-lived coordinator and invoke:

```text
$cody-codex-coordinator:cody-coordinator
```

That task becomes the one place where you can speak naturally about the
project. Useful requests include:

```text
Set up this repository with its coordinator standard.
Take over as coordinator for this repository.
Where do we stand?
Plan and implement <outcome>.
Recover the interrupted work and tell me the next safe action.
```

Cody inspects the repository, reconciles durable and current evidence, keeps one
active source of truth, and reports decisions or authority blockers directly.
When the task surface cannot expose identity, Cody reports that native metadata
is unavailable instead of inventing a callback destination.
It may dispatch visible bounded worker or reviewer tasks while keeping critical
milestone ownership inspectable. Luna tasks may use hidden subagents only for
bounded internal support; hidden subagents never own critical delivery. You
keep talking to the coordinator rather than acting as a message bus between
tasks.

The packaged schema and validator require direct upward callbacks; they cannot
prove that an external Codex task service delivered a live event. If a child
terminates without notifying its parent, the immediate parent owns one bounded
reconciliation and restores the callback path.

To move coordination to a fresh task, explicitly ask the current coordinator to
create or hand off to a replacement coordinator. The replacement recovers from
Git and `docs/codex/`; it does not rely on the old conversation alone. Cody does
not create a second coordinator merely because its description happens to match
another prompt.

## Token-efficient Sol, Terra, and Luna routing

Cody separates expensive project judgment from bounded execution. The task
where you invoke Cody is the durable root/portfolio coordinator. For critical
or multi-stage work it creates one visible Sol initiative coordinator, which
then routes bounded execution through the smallest useful worker shape:

- **Sol Medium** is the visible initiative coordinator. Sol owns requirements, planning,
  architecture and product judgment, risk classification, synthesis, exact-diff
  review, P0/P1 decisions, and release control.
- **Luna High** is the default scout, worker, executor, reviewer helper, and
  waiter. A simple bounded slice routes directly **Sol → Luna**.
- **Terra Extra High** is an optional junior coordinator for a fixed
  multi-stage Green/Amber boundary. That route is **Sol → Terra → Luna**. Terra
  decomposes only the supplied boundary and returns `SCOPE_CHANGE` when the work
  becomes Red or exceeds its authority.

The complete visible hierarchy is **root → Sol → Luna** for a simple bounded
slice, or **root → Sol → Terra → Luna** when Terra's decomposition materially
saves context. Terra is not inserted by default.

This is designed to save tokens without weakening control. Routine workers get
small packets instead of the coordinator's full transcript; independent slices
can run without duplicating all project context; repeated waiting is delegated
to one low-context Luna waiter; and Sol receives compact evidence for final
synthesis and review. Terra is used only when its decomposition saves more
context than it costs—simple work skips that extra layer.

Model availability is checked before dispatch. Missing evidence or an
unavailable required model fails closed with `SCOPE_CHANGE`; Cody never silently
selects a substitute. These roles configure Codex task orchestration only. They
do not select models inside your application or production provider.

## Authority boundaries

The task that invokes `$cody-codex-coordinator:cody-coordinator` is the
repository's coordinator;
Cody never creates a second coordinator by implication. Provider or external-
runtime ambiguity, unknown deploy pins, and unavailable consultation evidence
fail closed rather than selecting an assumed target. The project owner retains
product direction, priorities, and consequential approvals. Installing or
invoking Cody does not authorize commit, push, deploy, production mutation,
secret access, billing changes, or communication with real recipients.

The machine-checkable [routing contract](references/model-routing-contract.json)
defines the exact orchestration topology. Substitution is unsupported in
coordinator standard v0.2.0, which ships inside Cody plugin v0.2.0.

## Quick start

Add the Cody marketplace and install the plugin:

```bash
codex plugin marketplace add TheOGFlyingTesla/Cody --ref main
codex plugin add cody-codex-coordinator@cody
```

Restart Codex, open the task that should own coordination, and invoke:

```text
$cody-codex-coordinator:cody-coordinator
```

The plugin adds one explicit-only skill. It declares no MCP server, app,
authentication flow, telemetry, hosted backend, or runtime network service.
Installing it does not grant authority to commit, push, deploy, access secrets,
change billing, or send external messages; those actions always need separate
authorization.

Tell it the repository and desired outcome. The runtime commands require Python
3.11 or newer and Git 2.39 or newer.

Codex namespaces skills installed through plugins. The shorter
`$cody-coordinator` invocation is reserved for the advanced standalone/offline
skill installation described in
[Installation](docs/INSTALLATION.md#advanced-offline-installation).

To evaluate a source checkout without installing it, use the separate
[Installation](docs/INSTALLATION.md#evaluate-a-source-checkout) path. For a
manual CLI smoke from the extracted bundle root, preview initialization before
allowing mutation:

```bash
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format human inspect
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format human init --check
```

The `init` command can create or update coordinator-owned files and writes a
durable migration receipt. Read [Installation](docs/INSTALLATION.md) and
[Safety](docs/SAFETY.md) before using it on a non-empty project.

## Documentation

- [Installation](docs/INSTALLATION.md) — plugin installation, source evaluation, and verified offline bundles
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

This is an early public release, not a hosted product or a compatibility
guarantee. The repository is intentionally conservative about claims while the
public package layout and cross-platform installer hardening continue to
settle. See
[Limitations](docs/LIMITATIONS.md) for the current boundary.

If you are evaluating Cody alongside OpenAI's community programs, use the
[official Codex for Open Source page](https://developers.openai.com/community/codex-for-oss)
for current program information. Cody makes no claim of eligibility and the
link does not imply affiliation or endorsement.

## License

Cody is released under the [MIT License](LICENSE).
