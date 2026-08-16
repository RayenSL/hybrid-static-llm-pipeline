# Deviations

- 2026-08-16T16:13:21.8206512+02:00 — The precondition test and baseline builds could not retrieve
  vulnerability metadata from the configured private Azure DevOps and Telerik NuGet feeds
  (`NU1900`). No restore was required; compilation succeeded, all 141 tests passed, and the fresh
  baseline completed with the expected 36 findings and 13/13/10 split. No assignment or model call
  was affected.
