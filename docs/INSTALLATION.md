# Installation

Cody v0.1.0 is a preview. Start by installing a verified release bundle. Source
checkout evaluation is a separate, read-only activity and does not make that
checkout discoverable as an installed skill.

## Install a verified bundle

Before extraction, compare the downloaded ZIP's SHA-256 with the value published
for that exact release asset:

```bash
# macOS
shasum -a 256 cody-coordinator-0.1.0.zip

# Linux
sha256sum cody-coordinator-0.1.0.zip
```

Do not continue on a mismatch. After verification, extract the release ZIP to
an empty directory and run these commands from that bundle root:

```bash
python3 scripts/install_skill.py --release-root . --check
python3 scripts/install_skill.py --release-root .
python3 scripts/install_skill.py --release-root . --verify-discovery
```

The check is read-only. The install verifies the release inventory and
checksums, then installs only to the supported user scope:
`$HOME/.agents/skills/cody-coordinator`. `--verify-discovery` proves that the
expected immutable target and
the stable user-scoped discovery path are present. Its JSON output identifies
the scope and stable path without printing the local home directory. It does
not prove that an already-running Codex process has refreshed its skill catalog.
Restart or refresh Codex if needed, then invoke `$cody-coordinator` to confirm
product-level discovery.

This project has no established repository-scoped installation path. In
particular, it does not create or manage repository-scoped `.agents/skills`.
Do not copy the installed skill into another path and claim discovery-path
verification passed.

On platforms where the secure descriptor operations are unavailable, install
and discovery-path verification fail closed with `unsupported_platform`. See
[Portability](PORTABILITY.md) for the tested boundary.

After successful verification, invoke `$cody-coordinator` in the Codex task
that should coordinate the target repository.

## Evaluate a source checkout

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

## Bundle boundary

`scripts/install_skill.py` is designed for a generated Cody release bundle
whose root is the `cody-coordinator` skill itself, with `SKILL.md`, `VERSION`,
the scripts and references, manifest, and checksums at the bundle root. There
is no nested or companion package in the current layout. The source
checkout is not an installable bundle until its manifest and checksums have
been generated; an installer run against the wrong shape should fail closed.

The installer uses the documented user skill root under `$HOME/.agents`. It
uses a content-addressed destination and refuses to replace an unknown existing
skill path without a current decision token. A bundle can be installed offline
after it has been obtained and verified.

The installed skill retains its verified release metadata, so uninstall does
not depend on keeping the downloaded ZIP or extraction directory. Preview it
from the stable installed path:

```bash
python3 "$HOME/.agents/skills/cody-coordinator/scripts/install_skill.py" \
  --release-root "$HOME/.agents/skills/cody-coordinator" --uninstall --check
python3 "$HOME/.agents/skills/cody-coordinator/scripts/install_skill.py" \
  --release-root "$HOME/.agents/skills/cody-coordinator" --uninstall \
  --approve-removal <current-decision-token>
```

Never paste a real token, credential, or private path into documentation or a
support request.

Installing Cody does not create a second coordinator by implication. A request
to create or replace the coordinator task must carry the exact repository
identity and a compact recovery packet.
