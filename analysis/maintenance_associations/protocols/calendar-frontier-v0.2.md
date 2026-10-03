# Sampling amendment v0.2 — 22 September 2026

The chronology audit identified five Odoo observations whose first-parent ancestry contains committer dates after the labelled year. Their measurements remain valid for the recorded commits, but they cannot be treated as contemporaneous year-end observations under the original date interpretation.

For these observations, select the latest first-parent node in the frozen ancestry for which the cumulative maximum committer timestamp is strictly earlier than 1 January of the following year (UTC). This conservative rule establishes consistency with the recorded ancestor dates; it does not establish the historical branch tip. The accompanying JSON freezes the replacement commits before rescanning. The original histories, source archives, findings and figures remain unchanged. Jenkins and Tomcat require no replacement under this annual-boundary check.

Use the existing production scope, detector implementation, thresholds, counting units and checksum-pinned parser dependencies. Export source archives from the replacement commits, seal their contents, validate the findings schema, and require identical syntax and semantic results on replay. Publish original and replacement counts together. Do not transfer old findings or maintenance outcomes to replacement commits.

This amendment concerns snapshot selection only. Maintenance cohorts must subsequently be rebuilt against the revised baselines. Timestamp reversals, incomplete follow-up and independent detector and corrective-change validation remain separate admission requirements. No association estimates have informed this amendment, and no causal claims follow from it.

Reproduction from the repository root:

```sh
python3 analysis/multilanguage_evolution/prepare_linux_runtime.py --output /tmp/odoo-correction-packages --lock analysis/multilanguage_evolution/detectors/linux-wheel-lock.json
python3 analysis/maintenance_associations/rescan_calendar_correction.py --packages /tmp/odoo-correction-packages --cache tmp/maintenance-associations/git/odoo__odoo --sources tmp/maintenance-associations/calendar-frontier-v0.2-sources --output analysis/maintenance_associations/results/calendar-frontier-v0.2
python3 analysis/maintenance_associations/verify_calendar_sources.py --cache tmp/maintenance-associations/git/odoo__odoo --sources tmp/maintenance-associations/calendar-frontier-v0.2-sources --output analysis/maintenance_associations/results/calendar-frontier-v0.2/source-verification.json
python3 analysis/maintenance_associations/summarise_calendar_correction.py
```

The Git cache must contain the frozen Odoo ancestry and permit fetching missing source blobs. The scanner preserves matching sealed archives and refuses differing existing findings. Its manifest reports both original and replacement rule summaries and replay checks.
