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
| Release bundles are deterministic, allowlisted, checksum-bound, and safely extracted | `tests/test_cli_release.py` |
| Coordination pressure cases retain bounded routing, explicit authority, and silent unchanged heartbeats | `tests/test_lean_mode.py` and `tests/skill_pressure_cases.json` |

Run the same suite used by CI:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

The scenario catalog records expected choices for human review. It does not
replace the executable tests above or constitute evidence about a platform or
integration that has not been exercised.
