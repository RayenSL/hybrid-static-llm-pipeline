# Acquisition notes — 22 September 2026

No outcome or statistical hypothesis has been changed. No association estimates have been examined.

- Restore Git repositories as bare, blob-filtered clones under `tmp/maintenance-associations/git/`. These preserve ancestry and trees without downloading every historical source blob. Verify all frozen commits and compare retained archive file contents with Git tree blob identities. Subsequent hunk review must fetch required source blobs explicitly.
- Pilot strata are 2014, 2019 and 2024, each split by presence/absence of a broad corrective keyword, with up to five commits per stratum. Seed is 20260922. This sample is independent of detector exposure and maintenance outcomes. Its purpose is evidence feasibility and classification validation, not effect estimation.
- First-parent diffs record changed paths without heuristic rename detection. They are raw mainline change events, not validated maintenance episodes. Commit/merge duplication is avoided; duplicate backports and file lineage still need validation.
- A reference-syntax count includes arbitrary URLs (including SVN provenance links). It must not be presented as the number of issue-linked changes. Endpoint probes assess supported identifiers in the fixed sample only.
- Jenkins probes returned historical GitHub PR records from all three pilot periods. This establishes existence of those records only, not coverage of all PRs, issue labels, readiness events or historical tracker migration.
- Tomcat uses Bugzilla URLs and BZ identifiers. Three sampled REST endpoints returned HTTP 404. Public XML export requests returned HTTP 200 with a login page, not an issue record. Preserve this as access-limited evidence; do not label the issues nonexistent or the corresponding commits non-corrective. Authenticated access or separately validated public evidence is needed before claiming issue classification coverage.
- Current issue labels/descriptions retrieved in 2026 may have changed since the measurement window. Future collection must preserve event histories where available and distinguish retrospective classification evidence from predictors available at baseline.
- Independent human classification and detector validation remain outstanding. An automatically drafted interpretation cannot substitute for that assessment.

## File and review extraction stage

- Extracted first-parent raw file changes with root diffs, full blob identifiers and explicit A/M/D/T statuses. Unique exact-content deletion/addition pairs supply conservative move links. Edited renames remain unresolved. No source blobs were needed for these tree-level diffs.
- File cohorts retain both a raw commit-date change count and a separately named ancestry-clock count (running maximum commit date along the mainline). The latter is a timing diagnostic, not an amendment to the primary outcome or an association estimate. Baseline time shifts, deletions and possible scope exits must be reviewed before inference.
- Five sampled PR detail/timeline collections completed. One has an explicit ready-for-review transition. Two returned merge commits match their sampled mainline commits; the other three require squash/rebase/forward-port identity tracing. Do not infer review readiness at creation, or treat these five merged PRs as an unbiased duration cohort.
- Five narrative-based assistant classification suggestions are stored separately. No suggestion has been accepted into the corrective-outcome fields or labelled as independent human validation.
