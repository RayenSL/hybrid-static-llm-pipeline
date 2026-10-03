# Final automated association analysis v0.7 — 22 September 2026

The user explicitly waived the requirement for independent human validation and requested the final automated analysis. This amendment supersedes the human-review admission gate for this automated analysis. It does not convert unreviewed detector decisions into ground truth or unlabelled changes into confirmed corrective changes. Earlier protocols, worksheets and results remain preserved.

## Outcome and comparison population

Finalise the association between detector flags and subsequent recorded mainline file-change activity. This is the common secondary activity outcome already defined in v0.1, now the main reported outcome of this automated study. The unmeasured confirmed-corrective primary outcome, review duration, validated migration breadth and method-level repair effects are not estimated. Record this endpoint change explicitly in the thesis.

The main endpoint is at least one recorded first-parent file-change event in (actual baseline timestamp, baseline + 365 days], after the baseline in ancestry. Counts include modifications, additions/deletions representing tracked exact moves, and terminal deletions, with one count per lineage/event. The secondary endpoint is the number of such events over that window, not developer effort or a person-time rate. Deletion is therefore itself a recorded change; no claim of complete continued exposure after disappearance is made. Compare raw-time counts with the retained ancestry-clock counts, and with modification-only counts (M status) as sensitivities.

Estimate within repository and rule. Long Method comparisons require a named definition; God Class comparisons require a class. API comparisons require at least one resolved source-API pair in the retained inventory and use only the three inventory years (2014, 2019, 2024). Missing rule coverage remains excluded, never encoded as unflagged. Exposure is any baseline finding for the rule. Units are file × baseline, not independent repositories.

Before fitting, keep comparison years with both exposure groups and restrict file size and prior activity to their intersecting observed ranges within each year. Report the excluded counts. This modest range restriction does not establish full multivariate overlap or covariate balance. Use only baseline covariates: natural log(1 + file PLOC), natural log(1 + previous-365-day change count), and year fixed effects. Represent each continuous covariate with a four-degree-of-freedom cubic spline with one interior knot at the observed log-covariate range midpoint (avoiding duplicated quantile knots from zero prior activity), with a constant/linear fallback if there are insufficient distinct values. File age, contributor experience, subsystem and independently labelled prior defects are unavailable in the current analysis; acknowledge residual confounding.

## Estimation fixed before fitting

Main model: ordinary least-squares linear probability model, with the exposure coefficient reported as an adjusted percentage-point difference in probability of any subsequent recorded change. This is an adjusted association, not a causal effect. Report the fraction of fitted values outside [0,1].

Secondary model: Poisson pseudo-maximum-likelihood count model with the same design, reported as an adjusted mean-count ratio. Do not interpret this as a defect rate or an active-time rate. Report residual dispersion. The robust covariance addresses variance misspecification, not misspecification of the conditional mean or confounding.

For both models, use two-way clustered sandwich covariance by lineage and calendar year, with small-sample corrections. Use t reference quantiles with min(number of lineages, number of years) minus one degrees of freedom. The small number of calendar clusters, especially three for API comparisons, is a material precision limitation. A non-positive exposure variance or failed fit yields no inferential interval; do not silently replace it with a more favourable standard error.

Require at least 20 distinct flagged lineages, 20 distinct unflagged lineages, two comparison years, and at least ten event and ten non-event observations in each exposure group after the range restriction. Otherwise report descriptive results only. These are conservative feasibility thresholds, not a power calculation. Apply Holm correction across the available main-endpoint contrasts if reporting significance decisions. Preserve missing contrasts and explain why they were not fitted.

## Robustness and reporting

Refit the same design using ancestry-clock event counts and modification-only counts. Report diagnostic fits after excluding histories with recorded terminal deletions, scope exits or type changes, explicitly identifying this as selection on future information; it cannot replace the main population or establish causality. For the main linear probability coefficient, report a leave-one-calendar-block-out range using fixed three-year blocks anchored at 2007, refitting on the same preselected population. These ranges are stability diagnostics, not confidence intervals.

Publish raw exposed/unexposed counts and change proportions, common-support exclusions, fitted sample sizes, clustered uncertainty, adjusted effect figures as PDF, coefficient tables, sensitivity results, model diagnostics, input hashes and dependency versions. Repeated lineages can be broken by edited moves; unresolved reference bindings and source-scope changes remain limitations. No human-independent accuracy, confirmed defects, deployment duration, business impact or benefit of automated repair is inferred from change activity.
