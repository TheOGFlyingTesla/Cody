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

## Artifact and source verification

Build the candidate ZIP from a clean reviewed tree and retain both values in
the release record:

```bash
git rev-parse --verify HEAD^{commit}
python3 scripts/build_release.py --release-root . --output cody-coordinator-0.1.0.zip
python3 scripts/build_release.py --release-root . --output cody-coordinator-0.1.0.zip --check
python3 scripts/quick_validate.py --archive cody-coordinator-0.1.0.zip \
  --expected-sha256 <archive_sha256-from-build-output>
```

The builder reports an `archive_sha256` for the ZIP and a
`source_content_sha256` for the allowlisted source-file paths and bytes. Record
the exact Git commit separately: the content hash identifies the bundled source
inventory, while a Git commit identifies the reviewed source history.

`SHA256SUMS` is an inventory of the unpacked bundle members; it is not the ZIP
asset's checksum. Publish the builder's ZIP SHA-256 alongside the asset, then
verify the downloaded ZIP against that published value before extraction. After
safe extraction, the installer verifies the manifest, source-content hash, and
member checksums before installing. These checks prove consistency, not the
identity of the publisher by themselves.

Use an annotated signed Git tag for a public release when maintainers have an
established signing process, and publish the key-verification instructions with
the release. Cody does not currently claim that any tag or ZIP is signed.

The GitHub Actions workflow is one independent hosted proof lane. It runs on
pull requests and pushes, cancels superseded runs, and runs the complete Python
3.11 suite on Ubuntu and macOS. A separate Windows job proves read-only
inspection and explicit fail-closed mutation. The existing Ubuntu and macOS
jobs run `quick_validate` through the complete test suite. The suite both builds
a deterministic ZIP from source and consumes an explicit candidate archive by
its expected SHA-256. It safely extracts into a clean temporary location,
installs from the extracted archive only, verifies the discovery path, and runs
installed-skill inspection. It uses no secrets, schedules, deployment steps, or
path filters that could skip runtime proof.

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
