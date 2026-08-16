# Deviations

- 2026-08-16T16:13:21.8206512+02:00 — The precondition test and baseline builds could not retrieve
  vulnerability metadata from the configured private Azure DevOps and Telerik NuGet feeds
  (`NU1900`). No restore was required; compilation succeeded, all 141 tests passed, and the fresh
  baseline completed with the expected 36 findings and 13/13/10 split. No assignment or model call
  was affected.

- 2026-08-16 — The command wrapper reached its one-hour limit after 112 assignments and detached
  from the campaign child. The child remained healthy and continued from the same in-memory runner;
  no resume was issued, no assignment was repeated, no incomplete trace was created, and the ledger
  reached 432/432.

- 2026-08-16 — The parallel post-campaign evaluator wrapper reached its one-hour limit after the
  whole-solution quality stage had completed and while Layer 3 was still running. The Layer 3 child
  remained healthy and completed under its original process; neither evaluator was restarted.
