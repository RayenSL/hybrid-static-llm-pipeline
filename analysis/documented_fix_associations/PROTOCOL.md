# Documented fix-labelled patch association (v1.0)

This is an exploratory automated follow-up chosen after seeing the general change-activity results. It estimates association with *observable fix-labelled source edits*, not confirmed defects, developer effort or the causal effect of an anti-pattern. The earlier two inspected God Class fixes are purposive examples and do not determine the population rule below.

## Frozen population

Reuse the corrected 80,993 file-at-snapshot observations and 365-day ancestry-ordered follow-up windows from `analysis/maintenance_associations/results/final-automated-analysis-v0.7/analysis-input.csv.gz`. Treat Long Method and God Class in annual complete-rule cohorts from 2007–2024. Restrict source-declared Obsolete API Usage to 2014, 2019 and 2024, where its unflagged resolved-reference inventory is available. A file is exposed for a rule when at least one complete baseline finding exists. Long Method controls require a named definition, God Class controls a class, and API controls a resolved source/API pair. An incomplete rule observation is missing, not unflagged.

## Outcome

The outcome is at least one first-parent **modification** of the baseline production-file lineage, after the baseline commit and within 365 days of its recorded timestamp, from a commit whose subject meets a fixed repository-specific documentary rule:

- Odoo: subject begins `[FIX]` (case insensitive). This is a maintainer-applied fix label, not an independently verified bug report.
- Jenkins: subject contains `JENKINS-<digits>` and `fix`, `fixed`, `fixes`, or `regression` (case insensitive).
- Tomcat: subject contains a Bugzilla identifier (`BZ <digits>`, `Bug <digits>`, or an ASF Bugzilla URL) and `fix`, `fixed`, `fixes`, `correct`, or `resolve` (case insensitive).

Exclude subjects beginning `Revert` or containing only a revert of a candidate subject. Deduplicate each lineage/commit event. A zero means *no qualifying recorded fix-labelled edit* within this rule and window; it does not assert absence of bugs. Keep raw candidate commits, subjects, timestamps and file-event identities so every positive can be audited. No external issue page is silently assumed to be a confirmed bug. Previously inspected Jenkins issue 64621 and Tomcat bug 62664 remain illustrative source checks.

## Comparison and uncertainty

Within each repository and rule, retain calendar years with both exposed and unexposed eligible files and intersect their observed ranges of baseline production-file PLOC and prior 365-day changes. Fit the same linear probability design as the previous automated analysis: a flag term, calendar-year indicators, and cubic splines of log(1 + PLOC) and log(1 + prior change count). Use two-way clustered covariance by file lineage and year and a t reference with the smaller cluster count minus one degrees of freedom. Require at least two years, at least 20 distinct lineages in each exposure group, and at least ten positive and ten negative rows in each. Otherwise report descriptive counts only. Treat the analysis as exploratory; adjust the estimable main tests using Holm's procedure and retain unadjusted intervals for transparency.

Compare outcome coverage with all recorded modifications and the share of candidate commits that carry a qualifying source edit. This checks how selective the documentary rule is. Do not pool repositories: the commit conventions differ. Repeated file observations, edited moves, timestamp reversals, path/scope changes, imperfect semantic binding, unmeasured role/age and ambiguous issue taxonomy remain limitations. A patch to a file containing a finding need not edit the flagged entity. Report the two checked class-level examples separately from the association estimates.

## Reproduction

Read only the pinned analysis input, file-event SQLite databases and local first-parent Git histories. Record SHA-256s for those inputs and the source script. Refuse to overwrite existing outputs. A fresh output replay must reproduce canonical tables byte for byte. Do not modify the sealed prior campaign.
