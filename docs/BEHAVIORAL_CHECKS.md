# Behavioral checks

Cody treats important operating claims as executable contracts. The public CI
workflow runs the complete `unittest` suite on Linux and macOS with Python
3.11. A separate Windows job proves read-only inspection and the explicit
fail-closed blocker for unsupported native mutation; see
[Portability](PORTABILITY.md).

## Evidence map

| Scenario | Executable evidence |
|---|---|
| Setup preserves user-owned files and requires explicit authority for a non-empty non-Git folder | `tests/test_initialize.py` and `tests/test_cli_release.py` |
| Managed `AGENTS.md` updates preserve bytes outside Cody's marked block | `tests/test_markers_templates.py` |
| Credential-shaped content and hostile repository-controlled names are redacted or rejected | `tests/test_recovery_doctor.py` and `tests/test_cli_release.py` |
| Interrupted runs expose only evidence-supported recovery actions | `tests/test_recovery_doctor.py` |
| Upgrades preserve project documents and become no-ops after completion | `tests/test_upgrade_v30.py` and `tests/test_upgrade_v31.py` |
| Release bundles are deterministic, allowlisted, source-content-identified, checksum-bound, and safely extracted | `tests/test_cli_release.py` |
| An exact candidate ZIP is SHA-256-bound, installs to the supported user scope, verifies its discovery path, and runs installed-skill inspection | `scripts/quick_validate.py --archive` through `tests/test_cli_release.py` (Ubuntu/macOS CI) |
| Coordination pressure cases retain bounded routing, explicit authority, and silent unchanged heartbeats | `tests/test_lean_mode.py` and `tests/skill_pressure_cases.json` |
| Routing resolves only the declared Sol Medium → Luna High or Sol Medium → Terra Extra High → Luna High assignments, reports unavailable named models, and never silently substitutes | `tests/test_routing_contract.py` and `scripts/routing_contract.py` |
| An opt-in routing observation can be checked for contract conformance without claiming that self-authored JSON proves a live Codex run | `scripts/routing_live_eval.py` and `tests/test_routing_contract.py` |
| Executable contract checks require Terra escalation, Sol final authority, direct fan-in, one low-context waiter, and no implied duplicate coordinator | `tests/test_lean_mode.py` and `tests/skill_pressure_cases.json` |
| Visible dispatch packets require a complete work boundary, exact parent task and host identity, direct typed callbacks, terminal fan-in, silent unchanged state, bounded missing-callback reconciliation, fail-closed types, and duplicate-key rejection | `tests/test_dispatch_packet.py`, `tests/test_routing_contract.py`, and `assets/schema/dispatch-packet.schema.json` |
| Executable contract checks require deploy-pin mismatch and unknown provider/external-runtime ambiguity to fail closed | `tests/test_lean_mode.py` and `tests/skill_pressure_cases.json` |

From a source checkout, run the same suite used by CI. The generated release
bundle intentionally excludes `tests/`:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

From a release bundle, run its included archive/install smoke instead:

```bash
python3 scripts/quick_validate.py --release-root .
```

The scenario catalog records expected choices for human review. It does not
replace the executable tests above or constitute evidence about a platform or
integration that has not been exercised.
