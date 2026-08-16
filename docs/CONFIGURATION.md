# Configuration

Cody v0.1.0 does not define a separate application configuration file. The
configuration model is deliberately small and repository-local.

## Durable project state

The coordinator reads and writes a compact contract in the target repository:

| Surface | Role |
| --- | --- |
| `AGENTS.md` | User instructions plus one managed coordinator block |
| `docs/codex/PROJECT.md` | Project facts, commands, boundaries, and unknowns |
| `docs/codex/STATUS.md` | Compact recovery checkpoint |
| `docs/codex/ROADMAP.md` | Now, Next, Later, and Parked work |
| `docs/codex/DECISIONS.md` | Append-only durable rationale |
| `docs/codex/WORK_ITEMS/` | Bounded active and historical work items |
| `docs/codex/MIGRATIONS/` | Atomic journals and terminal reports |

Project-specific values should be discovered from the repository or supplied
by its owner. Cody does not require a hosting provider, database, deployment
target, secret manager, remote machine, or model account.

## Command-line options

The launcher accepts:

- `--repo PATH` — explicit target repository path; use an absolute path when
  automation or a different working directory is involved;
- `--format human|json` — readable output or structured output for tooling; and
- `--debug` — a redacted traceback for diagnosing an unexpected local failure.

Commands are `inspect`, `init`, `upgrade`, `doctor`, `reconcile`, `recover`,
and `check-current`. Run `--help` for the exact subcommand options in the
installed version.

## Local installation path

The release installer honors `CODEX_HOME` when provided and otherwise uses the
local Codex home. The chosen directory must be absolute, user-owned, and not
group- or world-writable. The installer does not accept a path merely because
it exists, and it refuses unknown existing skill entries.

This setting applies to a verified release bundle; it is not a project
configuration file and is not needed for direct CLI evaluation.

## Optional capabilities

There are no enabled-by-default adapters in this preview. If a future adapter
needs a provider, secret, remote host, or model, it must be separately named,
configured, and validated. Missing or unsupported capability must fail closed;
it must not silently fall back to a different target.
