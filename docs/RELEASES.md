# Release guide

This guide describes a safe public release of Cody. It does not authorize a
push, tag, deployment, provider change, billing change, or secret mutation.

## Versioning

The public project starts at `v0.1.0` and follows semantic-versioning intent
while it is in preview. A preview release may still change interfaces. The
coordinator standard version reported by the runtime is an implementation
identity and must not be presented as the public project version.

## Release checklist

Before publishing a release, a maintainer should:

1. review `git status`, the exact candidate commit, and the owned file list;
2. run the full Python test suite on the candidate;
3. run `doctor`, `check-current`, and any release-bundle check that applies;
4. validate YAML and Markdown, links, line endings, and `git diff --check`;
5. scan the complete candidate for credentials, private paths, and provider-
   specific personal assumptions;
6. review the README, limitations, security policy, and changelog together;
7. build the deterministic bundle and verify its manifest, checksums, and
   archive before distributing it; and
8. record unresolved risks instead of replacing them with marketing claims.

The GitHub Actions workflow is one independent hosted proof lane. It runs on
pull requests and pushes, cancels superseded runs, and runs the complete Python
3.11 suite on Ubuntu and macOS. A separate Windows job proves read-only
inspection and explicit fail-closed mutation. It uses no secrets, schedules,
deployment steps, or path filters that could skip runtime proof.

## Program references

OpenAI's [official community page](https://developers.openai.com/community)
contains current information about the Codex for Open Source program. Cody is
not an OpenAI project and this repository makes no claim of eligibility,
selection, sponsorship, or endorsement.

## Release notes

Every public release updates [CHANGELOG.md](../CHANGELOG.md) with user-visible
changes and known limitations. A release is not complete until its exact
candidate, validation results, and remaining risks are recorded by the
maintainer responsible for publication.
