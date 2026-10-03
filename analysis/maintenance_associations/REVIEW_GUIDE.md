# Independent validation packets

## Corrective-change sample

`results/history-pilot/independent-review.csv` contains up to five changes in each repository × year × keyword stratum (2014, 2019, 2024; seed 20260922). Read the immutable commit and relevant issue/changelog evidence. Classify whether the change restores intended behaviour: `confirmed_corrective`, `confirmed_non_corrective`, `uncertain`, or `inaccessible`. Record a supporting URL, rationale and reviewer identity. A typo, dependency update or refactoring is not automatically corrective; a changed file is not necessarily the defect location. Mixed-purpose commits require an explicit rationale or uncertainty.

Do not use the presence of 'fix' as the label. Do not infer a negative label from missing issue data. This is a feasibility sample, not a population census. Selection probabilities are retained for any weighted summaries. Current issue labels can differ from their historical state.

## Detector positive sample

`results/detector-positive-review.csv` contains a small stratified positive-finding sample. Open the frozen source link and independently assess the declared language-specific rule in `analysis/multilanguage_evolution/detectors/SEMANTIC_RULES.md`. Record `yes`, `no`, or `uncertain` under independent_rule_satisfied with reasons. Rule satisfaction and whether repair is desirable are different decisions.

This packet measures agreement/precision among sampled positives only. It does not validate unflagged controls, recall, repository scope, or language equivalence. Some strata have only a few findings; retain their stratum sizes and avoid unweighted pooling. Five positives per stratum cannot support precise stratum-level estimates.

## Independence and admission

These files are deliberately unlabelled. Model-generated labels must be labelled as such and cannot be called independent human review. Reviewer disagreements should be retained and adjudicated with reasons. Completion of this pilot does not automatically satisfy the full study validation requirements. Sparse classes, inaccessible issues and unmatched controls may require descriptive reporting rather than adjusted inference.
