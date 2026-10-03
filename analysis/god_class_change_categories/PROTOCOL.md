# God Class change-category follow-up: exploratory protocol v1.0

This follow-up was specified after observing the God Class adjusted mean change-count ratios. It asks which **commit-message categories** account for recorded changes to God-Class-flagged files in the same 365-day windows. Its labels describe documentary cues, not verified change purpose, defects, time spent, or causal effects.

## Population and event unit

Use the corrected `analysis-input.csv.gz` from the final automated maintenance association. Include only Jenkins and Apache Tomcat file-at-snapshot observations with a complete God Class scan and at least one eligible class. Odoo's supported comparison has only nine flagged observations and is descriptive. Reproduce the earlier within-year overlap restriction on baseline PLOC and preceding-year raw change count. A change event is a distinct first-parent `(commit sequence, production-file lineage)` pair in the original event database, regardless of whether its path record is `M`, `A` or `D`. Require sequence after the baseline commit and recorded timestamp in `(baseline time, baseline time + 365 days]`. The categories must partition every such event; the sum of category counts for each file observation must equal its archived `following365_raw_changes`. Keep a distinct-commit ledger with original subject, the title selected for classification, and category.

A generic `Merge pull request`, `Merge branch`, or `Merge commit` subject uses the first non-empty line of its commit body as the title if available; otherwise it remains unclassified. No other body text is used. Matching is case-insensitive. Apply the following mutually exclusive precedence to the selected title:

1. `revert`: subject or selected title begins `Revert` or `Re-apply`.
2. `security_labelled`: explicit `CVE-`, `CWE-`, `security`, `vulnerability`, `XSS`, `CSRF`, `XXE`, or `exploit`.
3. `documentation_or_tests`: `documentation`, `javadoc`, `docs`, `readme`, `translation`, `test`, `tests`, `tck`, or `typo`.
4. `issue_linked_fix_labelled`: Jenkins title has `JENKINS-<digits>` and `fix`, `fixed`, `fixes` or `regression`; Tomcat title has a `Bug`/`BZ` number or ASF Bugzilla URL and `fix`, `fixed`, `fixes`, `correct` or `resolve`. This matches the earlier documentary rule except that a generic merge may contribute its embedded title.
5. `other_fix_labelled`: `fix`, `fixed`, `fixes`, `bug`, `correct`, `corrected`, `resolve`, `resolved`, `regression`, `prevent`, `avoid`, or `repair` without satisfying category 4.
6. `feature_labelled`: `feature`, `add`, `added`, `implement`, `introduce`, `enable`, `support`, or `allow`.
7. `update_build_labelled`: `update`, `upgrade`, `bump`, `dependency`, `dependencies`, `version`, `release`, `build`, `maven`, `gradle`, or `CI`.
8. `refactor_cleanup_labelled`: `refactor`, `cleanup`, `clean-up`, `simplify`, `rework`, `rename`, `format`, or `formatting`.
9. `unclassified`: no above cue or no usable title.

These categories do not exhaust actual software-development motives. For example, a security fix is classified as security, a test fix as tests, and an unlabelled bug fix can be unclassified. An issue number alone does not prove that the tracker entry describes a defect. Preserve category overlap diagnostics for titles matching multiple cue groups.

## Analysis

For each category, report distinct commits and eligible/cohort file-event counts by repository and flag. Report the size of the unclassified group. The main comparative analysis fits a separate Poisson pseudo-maximum-likelihood mean-count model for each category on **the same comparison rows** as the original God Class total-count model, using a flag term, calendar-year effects and cubic splines in log(1 + file PLOC) and log(1 + prior changes). Use two-way clustered covariance by file lineage and year, the original small-sample correction and the smaller cluster count minus one t reference. Require at least 20 flagged and unflagged lineages, two comparison years, and ten positive and ten zero file observations per group; otherwise do not fit. Retain point estimates, unadjusted 95% intervals and Holm-adjusted p-values across all fitted category comparisons. Refit the all-category total as a check against archived ratios 1.2225489635 and 1.1423971558. Separate-category ratios are not additive and must not be interpreted as a decomposition of a causal effect.

Use only archived local Git histories, event databases, cohort data and pinned statistics packages. Record hashes and replay outputs. Do not recode uncertain titles as verified fixes and do not infer monetary or time cost from event counts. Two previously checked issue/patch examples may illustrate bug-fix involvement, but are not population estimates or causal evidence.
