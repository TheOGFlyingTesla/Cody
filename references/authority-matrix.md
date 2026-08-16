# Authority Matrix

| Action | Default authority | Extra requirement |
|---|---|---|
| Read files, Git status/history, instructions, tests | Allowed | Stay inside selected repository and redact sensitive content |
| Create/update coordinator contract during requested setup | Setup request | Coordinator allowlist and terminal candidate doctor |
| Edit product code for requested build/fix | Exact user scope | Bounded paths, validation, preserve unrelated WIP |
| Delegate write work | Same exact build/fix scope | Nonoverlapping ownership, direct fan-in, stop conditions |
| Create a managed worktree | When useful for authorized work | Record base/branch identity; no orphan control branch |
| Commit | Not implied | Explicit permission in current request/instructions |
| Push, merge, deploy, production/external-service/billing mutation | Forbidden by implication | Separate explicit authority and preflight |
| Secrets/credentials | Never expose or copy | Explicit secret workflow; generated records remain secret-free |
| Real email/message/call/trade/payment | Forbidden by implication | Separate explicit consequential-action approval |

## Decision boundaries

Proceed with reversible read-only discovery and normal implementation steps inside an explicit change request. Stop when a choice changes product direction, destructive scope, repository identity, user-owned content, external state, or consequential authority.

Repository setup authorizes coordinator files and, for an empty non-Git folder, sterile `git init` without a commit. A non-empty non-Git folder requires the emitted repository-boundary decision token.

Recovery reuses original immutable authority for verified resume/rollback. Rollback, repair, and supersede require an action-specific token bound to the journal, repository/Git identity, lock, and current hashes. A token confirms reviewed state; it never authorizes guessed bytes.
