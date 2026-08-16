# Installation

Cody v0.1.0 is a preview. There are two different activities: evaluating the
coordinator from this source checkout, and installing a verified skill from a
generated release bundle. Keeping those paths separate prevents an incomplete
checkout from being mistaken for a release artifact.

## Evaluate from a checkout

Install Python 3.11+ and Git 2.39+, clone or download the repository, then run
the read-only inspection against an explicit project path:

```bash
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format json inspect
```

The repository does not need a network service, database, provider account,
secret manager, or deployment target for this local evaluation. Use `python`
instead of `python3` when that is the local interpreter name.

## Initialize a project

Preview the plan first:

```bash
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format json init --check
```

If the result matches your intended scope, run the same command without
`--check`, then validate it:

```bash
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format json init
python3 scripts/coordinator_standard.py --repo /absolute/path/to/project --format json doctor
```

Initialization may create or update `AGENTS.md`'s managed coordinator block,
`docs/codex/`, and a migration receipt. On a non-empty repository, read the
boundary decision in the output before proceeding. Do not treat `init` as a
generic project scaffolder.

## Verified skill bundles

`scripts/install_skill.py` is designed for a generated Cody release bundle
whose root is the `cody-coordinator` skill itself, with `SKILL.md`, `VERSION`,
the scripts and references, manifest, and checksums at the bundle root. There
is no nested or companion package in the current layout. The source
checkout is not an installable bundle until its manifest and checksums have
been generated; an installer run against the wrong shape should fail closed.

When a verified bundle is available, run its plan first:

```bash
python3 scripts/install_skill.py --release-root . --check
```

Then install only after reviewing the result:

```bash
python3 scripts/install_skill.py --release-root .
```

The installer uses `CODEX_HOME` when set, otherwise the local Codex home. It
verifies checksums, uses a content-addressed destination, and refuses to
replace an unknown existing skill path without a current decision token. A
bundle can be installed offline after it has been obtained and verified.

Uninstall is similarly explicit and should be previewed before removal:

```bash
python3 scripts/install_skill.py --release-root . --uninstall --check
python3 scripts/install_skill.py --release-root . --uninstall --approve-removal <current-decision-token>
```

Never paste a real token, credential, or private path into documentation or a
support request.
