# Safety model

Cody is a coordination layer, not an authority to act on a user's behalf. Its
central safety rule is simple: when target, identity, bytes, or authority are
unclear, stop and report the blocker.

## Core invariants

- inspect before mutation;
- keep the target repository and skill source distinct;
- preserve user-owned files and unrelated work;
- use Git and durable journals as evidence;
- make operations idempotent and verify the result;
- keep journals and reports relative-path and secret-free; and
- fail closed when secure path or filesystem primitives are unavailable.

## Authority boundaries

Read-only inspection is allowed within the selected repository. Initialization,
upgrade, repair, and recovery are explicit operations with checks and receipts.
Commit, push, merge, deploy, production, provider, billing, secret, and
real-recipient actions are not implied by a normal coordination request.

The coordinator can recommend a next action; it does not turn a recommendation
into permission.

## Secrets and privacy

Do not put credentials, tokens, private keys, account identifiers, private
transcripts, or personal absolute paths into project docs, examples, fixtures,
logs, or issues. Diagnostic output is redacted, but redaction is a safety net,
not a reason to paste sensitive input. Use a secret manager outside Cody when a
project genuinely needs one; this preview does not select or configure one.

## Recovery

An interrupted operation is reconciled against current Git state, journal
receipts, and file hashes. Do not delete a journal, guess recovery bytes, or
repeat an unchanged failing action. A recovery command is safe only when its
target and action-specific authority are verified.

## Review checklist

Before trusting a change, ask:

1. What exact repository and branch did it target?
2. Which files can it mutate, and which are explicitly protected?
3. What happens if a path, provider, or task identity is unknown?
4. Can the result be validated and repeated without accumulating state?
5. Are the public claims narrower than the evidence?
