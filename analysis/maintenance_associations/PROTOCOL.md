# Anti-patterns and subsequent maintenance

Version 0.1, recorded 22 September 2026 before outcome extraction or association estimation. This is a prospective analysis plan for a retrospective observational study, not an externally preregistered study. Feasibility amendments must be dated and explained before estimating associations. Null results remain reportable.

## Purpose and scope

Extend the descriptive Odoo, Jenkins and Apache Tomcat study with concrete maintenance outcomes. The existing .NET repair experiments and frozen evolution measurements remain separate. This study tests associations; it neither proves that anti-patterns cause maintenance problems nor measures the effect of the thesis repair pipeline.

The thesis cites ISO/IEC 25010:2023. ISO categories organise hypotheses, not automatic deductions from findings. Use the 2023 standard's title, Product quality model (the thesis bibliography currently uses the earlier edition's title).

| Rule | Hypothesised mechanism | Quality interpretation | Specific secondary outcome |
|---|---|---|---|
| Long Method | Complex control flow may complicate understanding a change | Maintainability: analysability; no direct testability measurement | Elapsed ready-for-review-to-merge time for PRs touching baseline flagged methods |
| God Class | Concentrated responsibilities may make modifications less local | Maintainability: modularity and modifiability | Number of other production files changed alongside a modified flagged class |
| Source-declared Obsolete API Usage | Replacing deprecated interfaces may require coordinated edits | Maintainability: modifiability | Number of production files in a validated internal API migration change |

The shared primary outcome is any confirmed corrective change touching an eligible baseline production file during the following 365 days. This measures corrective-maintenance involvement, not defect introduction, failure probability or hours of work. Secondary common outcomes are the number of corrective changes and total modifying changes. Source churn is descriptive. Security and runtime compatibility are not inferred from deprecation alone.

Long Method in this implementation means complexity >10; length alone does not trigger it. Do not imply equivalence between Java/Python mappings and the C# detector. Findings retain the existing provisional validation status.

## Temporal and population rules

Use frozen 14 September 2026 evidence cutoff and the previously selected commits. Do not extend follow-up merely because the present date is later. For a baseline at actual commit time t, follow-up is (t,t+365 days], conditional on complete history through that boundary. Thus 2025 year-end and 2026 endpoints lack full follow-up. An audit must calculate eligibility using actual timestamps, not labels. Earliest observations may lack the 365-day prior history needed for adjustment; omit these from adjusted primary estimates and retain descriptively. Flag overlapping follow-up windows; annual labels do not guarantee independence.

Require rule-specific complete baseline measurements, a complete eligible file inventory, and an auditable link from baseline paths to later changes. A missing detector output is not an unflagged file. Files deleted during follow-up remain tracked with their observed exposure time; analyse deletion as a competing event/sensitivity rather than treating unobserved time as absence of fixes. Never discard a file because it later changes name or disappears.

Use changes introduced onto the frozen mainline ancestry, respecting ancestry order and recording commit-date reversals. Do not count a merge diff and its constituent commits twice. Canonical maintenance events group documented backports/forward-ports of the same fix. Ambiguous grouping is retained for sensitivity analysis. Match source hunks when feasible; a file-level association cannot be described as a method-level causal effect.

The main shared unit is file × baseline snapshot × rule. Exposure is presence of at least one baseline finding for that rule. Counts or densities are secondary doses, never sums across rules. Unflagged files must be within the same language and frozen production scope. Report files carrying multiple rules; estimate rules separately and assess co-occurrence in sensitivity analyses.

## Corrective-change evidence

Join commit/PR references to public issue records, changelogs and patch content. A 'fix' keyword or Odoo [FIX] prefix nominates a candidate only. Labels: confirmed corrective, confirmed non-corrective, uncertain, inaccessible. Missing links and unlabelled events are not automatically non-corrective. Preserve supporting URLs, immutable commit hashes, retrieved records and classification rationale. A corrective label requires evidence of restoring intended behaviour, rather than a feature, formatting or refactoring alone.

Before outcome modelling, audit link availability by repository and period. Restrict confirmatory comparisons to declared coverage intervals; poor evidence coverage cannot be cured by treating unknown events as zero. Publish sensitivity bounds or alternate classifications for unresolved events. Estimate label precision and agreement on a stratified sample, with a human reviewer independent of automatic candidate selection. An LLM-only review is not independent ground truth.

## Specific secondary studies

Long Method: exposure comes from PR base code, not the post-merge state. A yearly snapshot cannot safely substitute for the PR base; rescan the relevant base revision with pinned tools. Measure readiness transition to merge; if readiness events are unavailable, opening-to-merge is a separately named exploratory endpoint. Retain open PRs as right-censored and closed-unmerged PRs as competing events. Account for patch size, author experience, calendar period and baseline subsystem. Review rounds are exploratory. Wall-clock delay is not active review effort.

God Class: use verified class-to-file and hunk mapping where possible. Compare co-change breadth conditional on a modification with comparable unflagged classes in the same repository and period. Record the number of other in-scope production files touched by the canonical change. Account for baseline size, past activity and change type; do not adjust for total changed-file count because it contains the outcome. Large mechanical changes and release sweeps require predefined classification and a reported sensitivity analysis. Co-change is not proof that the other edits were necessary consequences.

Obsolete API Usage: follow identified source symbols and their references. Validate migration replacements using declarations, documentation and diffs. Separate replacement, caller deletion, API deletion, annotation removal and unresolved identity. Migration latency is exploratory and right-censored at cutoff; a long delay is not evidence of harm. Primary secondary measure is migration change breadth. A per-API analysis of baseline caller-file count versus migration breadth tests coordination burden conditional on migration, not whether deprecated APIs are worse than non-deprecated APIs. Size overlap makes this partly mechanical; report it explicitly. Do not select only visibly expensive migrations.

## Estimation and interpretation

Freeze baseline covariates: file PLOC, file age, previous-365-day modifying changes, previous confirmed corrective changes, contributor count and subsystem. Covariates are measured before follow-up. Do not adjust for future churn in the primary analysis: it may mediate the association. Do not use WMC, ATFD or TCC as independent maintenance outcomes since they define God Class. Assess common support before matching/weighting; unmatched strata are reported, not extrapolated silently.

Primary estimates: within-repository adjusted probabilities and risk differences for subsequent corrective involvement, separately for the three rules. Fit only after event counts, missingness and common support are audited; sparse strata remain descriptive. Use a parsimonious binary-outcome model with baseline covariates and calendar effects, or time-to-event model if variable exposure/deletion requires it. Repeated file histories require clustered uncertainty; investigate calendar dependence with temporal-block sensitivity. A file-year is not an independent repository. Do not fit a cross-project random effect from only three projects or pool languages to rank quality.

Secondary count models must address overdispersion and observation time. Duration outcomes require censoring-aware estimates. Report estimates and 95% intervals, event counts, excluded populations and diagnostics. The planned primary family contains up to nine repository × rule contrasts; use Holm correction if reporting significance decisions. Specific secondary analyses are exploratory in protocol 0.1. No search over lags, thresholds, outcomes or covariates to obtain significance. Model changes require a dated amendment with reasons.

## Validation, reproducibility and gates

1. Audit the existing sealed evidence, source inventory and baseline/follow-up eligibility without outcome analysis.
2. Restore complete Git histories in a persistent cache; verify every frozen commit and archive source hash. Never use moving HEAD as the exposure endpoint.
3. Audit public issue and PR coverage. Store immutable raw responses, retrieval date, request parameters, pagination and content hashes. Separate transient/network failures from unavailable records.
4. Prepare stratified detector and corrective-label validation samples using seed 20260922; retain sampling probabilities. Independent human assessment is required before calling estimates validated.
5. Implement canonical event extraction and file lineage; manually audit merges, renames, backports and negative examples. Execute a bounded feasibility pilot before the full extraction, with no hypothesis estimates.
6. Freeze any feasibility amendments, then construct outcome tables and estimate planned associations. Insufficient coverage is reported; it is not an excuse to change outcomes after looking at associations.

The existing evolution results remain admitted:false. Repeated replay of custom detector output establishes repeatability, not empirical precision or recall. No new scientific admission occurs through this protocol.

## Figures and thesis integration

Keep annual prevalence/count figures as context. Add separate panels of adjusted risk differences with confidence intervals for common outcomes. Show secondary outcomes on their own scales, with explicit populations and periods. Avoid dual-axis annual plots and raw correlations between trending project totals. Do not label any outcome an ISO quality score. Report null and contradictory findings. This extension motivates selective repair; the controlled repair experiment still supplies the evidence about repair validity.

## Sources

- ISO/IEC 25010:2023 official catalogue: https://www.iso.org/standard/78176.html
- Palomba et al., diffuseness/change/fault associations: https://doi.org/10.1007/s10664-017-9535-z
- Sjøberg et al., maintenance effort and confounding: https://doi.org/10.1109/TSE.2012.89
- Pascarella et al., review and smell evolution: https://arxiv.org/abs/1912.10098
- Deprecated API usage mining study: https://www.sciencedirect.com/science/article/pii/S0950584925001211
- Jenkins issue identifier migration: https://issue-redirect.jenkins.io/
- Tomcat contribution channels: https://tomcat.apache.org/bugreport.html

Official ISO catalogue confirms edition/title; the mapping above is a study hypothesis, not a quotation or claim of standard-prescribed measurements.
