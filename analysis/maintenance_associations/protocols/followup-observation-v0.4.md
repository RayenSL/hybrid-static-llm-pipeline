# Follow-up observation specification v0.4 — 22 September 2026

This feasibility amendment is recorded after chronology and lineage audits but before association estimation. It operationalises the deletion and scope rules in protocol v0.1. The exposure definitions, 365-day horizon, frozen evidence cutoff and corrective-change validation requirements are unchanged. Original cohorts remain retained.

## Target and observation states

The shared estimand concerns a baseline production file's involvement in a confirmed corrective change in the selected repository during the following 365 days, while its tracked continuation remains in production scope. It is not the probability that its code disappears, or that the entire project fails. Cross-repository continuation is outside this study's boundary and must be described as such, rather than as code elimination.

Retain every eligible baseline in the dataset. Track the following states without excluding files on the basis of future events:

| Evidence | Treatment |
|---|---|
| Validated continuation at a new in-scope path | Continue the same baseline lineage; count each canonical maintenance event once. Record the supporting source and destination identities. |
| Independently confirmed corrective involvement before an exit | Record the primary event, including when the corrective change itself removes the file. A deletion is not corrective solely because it removes a finding. |
| Verified permanent removal, repository extraction or production-scope exit before a corrective event | Record a distinct competing exit with its reason and evidence. Do not label the file as an observed, unchanged file throughout the rest of the year. |
| Deletion with unresolved move or absorption | Record an uncertain identity boundary. Subsequent outcome is unknown, not zero. Retain any confirmed prior corrective event. |
| Full observed horizon with all eligible events classified and no corrective event | A verified negative outcome is possible; absence of a 'fix' keyword or issue link is insufficient. |
| Unclassified or inaccessible potentially relevant event | Keep corrective status unknown. A complete Git history does not establish complete outcome evidence. |

For primary first-event analysis, the first verified exit ends in-scope exposure. A later return is a new episode only in a separately declared sensitivity analysis; it must not silently restore the original first-event risk period. If corrective involvement and an exit share a commit, count corrective involvement only when supported by independent evidence about that change; report a sensitivity analysis assigning such ties to the exit instead. This tie rule is frozen before labels or estimates.

## Temporal uncertainty

Keep actual commit timestamps and first-parent order as specified in v0.1. Keep cumulative-maximum timestamps as a diagnostic, not a replacement for historical integration time. Preserve both event sets where membership differs. A record may have identical counts but different events, or uncertain prior-window covariates.

Do not fit a time-to-event model using negative or non-monotone event times. Resolve such dates using additional project evidence, or retain the affected timing as uncertain. Do not overwrite dates, impute zero exposure time or choose the time definition producing the stronger association. For a binary 365-day endpoint, record whether the outcome is invariant across the retained membership interpretations after independent classification. Invariance is robustness to these two definitions, not proof of the historical dates.

## Estimation gate and sensitivity

Estimate neither naive complete-case risks nor survival curves that assume unresolved exits are unrelated to exposure or maintenance. Verified exits can enter a competing-event analysis once time ordering and labels are admissible. Administrative censoring is the frozen observation boundary; it differs from an unresolved identity break. All baseline rows remain available for transparent population accounting.

If lineage, outcome or timing remains uncertain, retain lower/upper outcome possibilities. A confirmed corrective event fixes a positive endpoint. A complete, validated negative history or verified competing exit can establish no prior corrective event; an unclassified earlier event cannot. Unresolved histories contribute both possible endpoint values unless evidence narrows them. Any reported unadjusted bounds must include all relevant baseline denominators, be stratified by repository and rule, and be labelled identification bounds rather than confidence intervals or adjusted causal effects. Do not calculate bounds from keyword labels or treat them as a substitute for independent validation.

Adjusted comparisons remain conditional on validated covariates, overlap and outcome coverage. Report the distribution of uncertain histories by baseline exposure. Define dependence handling for repeated lineages and overlapping windows before estimation. No exposure group may receive more permissive lineage or corrective-label rules.

## Implementation status

The patch packet and machine-generated linkage suggestions support review; they do not authorise rewriting lineage identifiers or admitting outcomes. Independent reviewers must validate the continuation, removal or extraction evidence. Existing independent-label worksheets remain blank. No censoring times, competing-event estimates, outcome bounds or associations have been fitted under this amendment.
