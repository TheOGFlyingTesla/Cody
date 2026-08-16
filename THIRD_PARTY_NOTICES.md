# Third-party notices

Cody currently has no vendored third-party runtime dependencies. The Python
coordinator uses the Python standard library; Python itself is distributed
under its own PSF License.

The CI workflow uses these GitHub-maintained actions at runtime:

- [`actions/checkout`](https://github.com/actions/checkout), distributed under
  the MIT License.
- [`actions/setup-python`](https://github.com/actions/setup-python),
  distributed under the MIT License.

These actions run on GitHub-hosted runners and are not part of the Cody runtime
installed into a user's project. Their versions are pinned by the workflow and
should be reviewed when they are updated.

No OpenAI SDK, API client, hosted service, or proprietary provider integration
is bundled by this repository.

The Cody social-preview artwork was generated specifically for this project and
contains no third-party brand marks. It is distributed with the project under
the repository license.
