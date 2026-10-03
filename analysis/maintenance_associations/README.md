# Maintenance association study

> Generated results, figures and publication manifests were removed from this checkout.
> Paths and historical results described below refer to outputs that must be regenerated
> or restored before downstream analysis. Source code, protocols and dependency locks remain.

This extension tests one common maintenance outcome and specific secondary outcomes for each anti-pattern. Read [PROTOCOL.md](PROTOCOL.md) before collecting or analysing outcomes.

## Final automated analysis completed

The user explicitly waived mandatory human validation. The [final report](results/final-automated-analysis-v0.7/REPORT.md), [probability figure](results/final-automated-analysis-v0.7/adjusted-change-probability.pdf), [count figure](results/final-automated-analysis-v0.7/adjusted-change-count.pdf) and [thesis paragraph](results/final-automated-analysis-v0.7/thesis-results.tex) are complete. Earlier human-review gates below are retained as historical stage records and do not block this final automated analysis.

The reported endpoint is recorded file-change activity, replacing the unmeasured confirmed-corrective endpoint for this automated study. All seven fitted main binary contrasts include zero in their 95% intervals and fail the Holm-adjusted 5% threshold. Secondary God Class count ratios are 1.223 in Jenkins and 1.142 in Tomcat; their uncertainty and sensitivity results are retained. Odoo God Class/API contrasts are descriptive because of sparse support. No claim of confirmed defects, repair cost or causality is made.

Amendment v0.7 fixes the comparison/model specification; v0.7.1 records a diagnostic logistic sensitivity after observing out-of-range linear predictions. The current completion state is `results/final-automated-analysis-v0.7/inference-gate.json`. Statistical verification independently reconstructed the score-based two-way covariance for the substantive count findings. Reproduction commands and pinned dependencies are documented in the report.

## Previous study stages

The protocol, baseline audit, history restoration, archive verification and bounded public-evidence pilot have been executed. See [PILOT_REPORT.md](results/history-pilot/PILOT_REPORT.md) and [ACQUISITION_NOTES.md](ACQUISITION_NOTES.md).

- Restored bare, blob-filtered public histories in `tmp/maintenance-associations/git/`.
- Verified all 63 frozen commits and all 63 archived source SHA-256 seals; 139,377 archived regular-file snapshots match Git tree blob identities.
- Extracted 145,963 frozen-mainline events: Odoo 94,000; Jenkins 23,265; Tomcat 28,698. These are raw changes, not confirmed bug fixes or deduplicated maintenance episodes.
- Prepared a seeded 90-change classification packet and a separate 113-positive-finding detector packet.
- Retrieved five sampled historical GitHub PR records. Tomcat REST probes returned 404; supplemental XML probes returned login pages. The fixed Odoo 2014 sample supplied no supported GitHub reference. None of these observations establishes population-wide coverage.
- No outcome associations have been estimated. Independent labels, validated control populations, lineage and hunk mapping, PR timelines and migration identities remain incomplete.

The prior temporary Git cache is no longer needed. Persistent clones are not shallow, but absent source blobs require retrieval for hunk review. First-parent timestamp reversals are recorded: Odoo has 3,894, so future event-window construction must preserve ancestry as well as timestamps.

## File-level extraction completed

See [file-cohort stage report](results/file-cohorts/STAGE_REPORT.md).

- 1,416,619 raw file-change records extracted, with first-parent event counts reconciled to Git.
- All three database seals and integrity checks pass; reconstructed final inventories match frozen Git trees.
- 81,820 baseline production-file observations joined to source metrics, rule findings and change-activity diagnostics (Odoo 39,314; Jenkins 16,796; Tomcat 25,710).
- Edited renames, scope exits and deletion censoring remain unresolved for inference. Corrective-outcome columns remain empty.
- Odoo has material timestamp reversals; six selected annual baselines have positive ancestry-clock shifts. `results/file-cohorts/odoo-time-diagnostics.json` records the magnitude and affected counts. The ancestry-clock column is a diagnostic, not a new primary time definition.
- Detailed evidence for five PRs is archived under `results/review-evidence/`. Only one has an explicit readiness event, and two match the sampled commit to the API merge commit. Five assistant narrative-based suggestions remain separate from independent labels.

Additional reproduction commands (file-event extraction refuses to overwrite an existing database):

```sh
python3 analysis/maintenance_associations/extract_file_events.py jenkinsci__jenkins
python3 analysis/maintenance_associations/extract_file_events.py apache__tomcat
python3 analysis/maintenance_associations/extract_file_events.py odoo__odoo
python3 analysis/maintenance_associations/validate_file_events.py
python3 analysis/maintenance_associations/build_file_cohorts.py
python3 analysis/maintenance_associations/collect_review_evidence.py
python3 analysis/maintenance_associations/summarise_file_cohorts.py
```

Complete database extraction before launching cohort construction. The database and raw-diff caches are retained in `tmp/maintenance-associations/file-events/`, with hashes in the study results. Cohort processing uses temporary local copies for read performance. Preserve existing HTTP evidence before rerunning network collection; responses are time-dependent.

## Chronology and PR identities audited

See [chronology and linkage report](results/linkage-audit/AUDIT_REPORT.md). All five sampled PR identities are resolved from explicit historical merge events or Odoo merge-bot records. This supersedes the earlier identity warnings; it does not establish readiness-duration coverage or corrective labels.

Five Odoo annual observations (2018, 2019, 2020, 2023, 2024) contain ancestors dated after the labelled year boundary. Their existing counts must not be used as contemporaneous year-end evidence. The initial candidate commits are recorded in `results/linkage-audit/chronology.json`. The subsequent correction is versioned separately below. The original audit gate records the state at that stage.

The chronology audit can be rerun with `python3 analysis/maintenance_associations/audit_chronology_and_links.py` after retaining the archived Odoo merge-bot pages. Original source counts remain attached to their original commits. Adopting replacement snapshots requires new measurements and a versioned sampling amendment.

## Reproduction

Restore each missing cache with `git clone --bare --filter=blob:none` from its official repository (`odoo/odoo`, `jenkinsci/jenkins`, `apache/tomcat`). Finish cloning before running verification. From the repository root:

```sh
python3 analysis/maintenance_associations/audit_inputs.py
python3 analysis/maintenance_associations/run_history_pilot.py
python3 analysis/maintenance_associations/verify_archives.py
python3 analysis/maintenance_associations/sample_detector_findings.py
python3 analysis/maintenance_associations/summarise_pilot.py
```

For a new pilot run, pass `--output` to `run_history_pilot.py` with a new directory to preserve the original HTTP responses. The summary script reads the default frozen pilot directory. Network response contents and retrieval times may change; canonical Git metadata and seeded samples should reproduce from the frozen commits. Failed responses remain archived. Supplemental Bugzilla XML requests and their hashes are retained under `results/java-pilot/bugzilla-probes/`.

`results/baseline-eligibility.csv` uses actual commit timestamps and the frozen 14 September 2026 cutoff. It requires complete detector coverage, 365 days of preserved prior history and 365 days of possible follow-up. Odoo and Jenkins each have 18 temporally eligible baselines per rule (2007–2024); Tomcat has 18 Long Method and 16 semantic-rule baselines. These temporal checks do not establish independent validation or complete issue data.

## Validation handoff

Use [REVIEW_GUIDE.md](REVIEW_GUIDE.md) with `results/history-pilot/independent-review.csv` and `results/detector-positive-review.csv`. Labels are deliberately blank. Positive-only detector review cannot estimate recall or validate unflagged controls. The approved protocol requires independent assessment before validated association claims; an LLM-only assessment does not fulfil that requirement.

## Calendar-frontier amendment v0.2

The [sampling amendment](protocols/calendar-frontier-v0.2.md) freezes five replacement Odoo commits and the detector inputs. The [comparison report](results/calendar-frontier-v0.2/REPORT.md) records fresh measurements and exact replay checks; `comparison.csv` includes all three rules, denominators and production-code size. The existing histories, figures and cohorts remain attached to their original commits.

Run the reproduction commands in the amendment to restore dependencies, rescan, verify source identities and regenerate the comparison. The new `results/calendar-frontier-v0.2/inference-gate.json` records the current admission state. Rebuilding affected cohorts and independent validation remain necessary before association estimation.

## Corrected maintenance cohorts rebuilt

The [v0.2 cohort report](results/file-cohorts-v0.2/REPORT.md) supersedes the Odoo counts in the earlier file-cohort stage. Odoo now has 38,487 file-at-snapshot observations; all 13 unaffected years match the originals exactly, and a second extraction reproduces the corrected dataset byte for byte. Jenkins and Tomcat remain unchanged. The combined manifest references 80,993 observations across all three repositories.

Residual baseline shifts and 279 disagreements between raw-date and ancestry-clock follow-up counts are retained as diagnostics. Corrective labels remain blank. The current admission gate is `results/file-cohorts-v0.2/inference-gate.json`; the previous gates are preserved as stage records. Next resolve the temporal-window and lineage treatment, then complete independent detector and outcome validation before estimating associations.

## Event membership and file continuity audited

The [window and lineage report](results/window-lineage-audit/REPORT.md) examines all 80,993 corrected file observations. Odoo has 282 follow-up event-membership differences (including three hidden by equal counts) and 233 prior-window differences. Jenkins and Tomcat have no membership differences under the two audited date definitions. There are 24 overlapping pairs of baseline follow-up intervals.

Git blob identities confirm path-scope exits for three Odoo file observations. Terminal deletions and edited moves remain distinct from confirmed removals. The fixed-seed 50-case `results/window-lineage-audit/independent-lineage-review.csv` supports the next independent review; classification fields are blank and protected against overwrite. The complete deduplicated candidate queue and original data are retained.

The current gate is `results/window-lineage-audit/inference-gate.json`. Retain actual-date windows and the alternative membership evidence; specify uncertainty, scope boundaries and deletion handling before estimating associations. Independent detector and corrective-change validation is still required.

## Lineage patch evidence and follow-up specification

The [patch report](results/lineage-patch-evidence/REPORT.md) covers all 50 sampled continuity cases. Screening records 20 exact-content links, eight edited-move candidates and 22 unresolved cases. These stratified sample counts are not population rates. The [review index](results/lineage-patch-evidence/REVIEW_INDEX.md) links the archived evidence; original independent labels remain blank.

The [v0.4 follow-up specification](protocols/followup-observation-v0.4.md) distinguishes continued in-scope identity, verified competing exits, unresolved identity and administrative end of observation. It retains all eligible baselines and does not convert unknown follow-up into negative outcomes. No lineage identifiers, outcomes or estimates have been changed. Independent validation remains pending.

Reproduce acquisition with `python3 analysis/maintenance_associations/collect_lineage_patch_evidence.py` (a fresh output directory is required), then `python3 analysis/maintenance_associations/screen_lineage_patches.py` for machine suggestions. Pass the same fresh `--output` directory to both commands for a repeat acquisition. Retain independent review worksheets separately.

## Current independent-review handoff

Use [START_HERE](results/validation-handoff-v0.5/START_HERE.md) and the [portable reviewer packet](results/validation-handoff-v0.5/reviewer-packet.zip). The detector worksheet contains 203 cases: 113 reported findings and 90 sampled unflagged methods/classes. Eighteen old Odoo positive examples have been superseded by corrected snapshot examples. Complete sampled source and API declaration files are archived locally.

The packet also contains the unchanged 90-case corrective and 50-case lineage worksheets. Detector predictions remain in the coordinator ledger, outside the reviewer zip. The submission checker rejects changed evidence identities, invalid labels and missing supporting fields; it does not validate reviewer independence or admit scientific inference. API-reference negative controls remain unavailable.

Reproduce with `prepare_validation_handoff.py` followed by `package_validation_handoff.py`, both under `analysis/maintenance_associations/`; pass the same fresh `--output` directory for a new packet. Validate returned files with `check_review_submission.py --packet <original-packet> --submission <returned-csv-directory> --output <new-report.json>`. Never overwrite returned reviewer decisions.

## Source-API control inventory and review supplement

The [v0.6 API-control report](results/api-control-review-v0.6/REPORT.md) closes the missing resolved-reference inventory gap in the previous handoff. Copies of the pinned Java and Python adapters now export individual reference records; original detector sources remain unchanged. All nine review snapshots reproduce every original raw-output field and reconcile all frozen API findings. The inventory contains 222,359 pair-at-snapshot observations, including 1,674 flagged pairs. Two Java pairs lack a valid use location and are retained with explicit flags.

The separate [45-case supplement](results/api-control-review-v0.6/api-review-supplement.zip) samples five unflagged API pairs per repository and year. It preserves the earlier reviewer package and includes source/declaration evidence and sampling probabilities. The fixed-seed sample and portable archive hashes were verified. These are not confirmed negatives; unresolved and external references remain outside the population.

Read [amendment v0.6](protocols/api-reference-controls-v0.6.md) and the report for reproduction commands. The first failed export attempt is retained under `results/api-reference-inventory-v0.6-first-pass`, documenting discovery of source-position gaps; the current inventory is `results/api-reference-inventory-v0.6`. Independent human review and subsequent outcome/coverage checks remain pending; no correlations have been estimated.
