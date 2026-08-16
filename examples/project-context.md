# Example project context

This is a documentation-only example of the facts a project owner may want to
make explicit before a coordinator initializes a repository. It is not read
automatically by Cody.

```text
Project purpose: <one sentence>
Repository path: <absolute path supplied at runtime; do not commit it>
Primary validation command: <command>
Deployment: none for this project
External providers: none required
Secret manager: not configured in Cody
Remote compute: disabled
Release owner: project maintainer
Known unknowns: <list anything not verified>
```

Keep real paths, credentials, account identifiers, hostnames, and private
operational details out of committed examples. If a project requires a provider
or secret manager, document the capability and authority boundary without
embedding its values.
