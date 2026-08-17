# Completion Report

Every setup, upgrade, implementation, repair, recovery, or release report uses these headings:

## Summary

Lead with the achieved outcome and distinguish it from recommendations.

## Files changed

List owned files or state that the work was read-only. Mention preserved user WIP when relevant.

## Validation run

List exact checks actually run and their results. Never imply an unrun check passed.

## Review findings

Record independent review scope and findings, or explicitly state that no independent review was run.

## P0/P1 status

State whether any release-blocking data-loss, credential, production, security, or correctness issue remains.

## P2/P3 disposition

Mark each as fixed, accepted with reason, or deferred with owner/trigger.

## Remaining risks

State uncertainty, unavailable evidence, and operational boundaries plainly.

## Next step

Give one concrete next action, including “none required” when genuinely complete.

Recovery reports use evidence labels consistently: verified (directly proven), inferred (supported but indirect), unknown (not available), stale (historical and not current), and conflicting (sources disagree). Native task metadata must be labeled unavailable when the active surface cannot query it.
