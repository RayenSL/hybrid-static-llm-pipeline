"""Summarise cohort completeness and timing diagnostics without association tests."""
import csv,gzip,hashlib,json
from pathlib import Path
BASE=Path(__file__).resolve().parent
man=json.loads((BASE/'results/file-cohorts/manifest.json').read_text())
review=json.loads((BASE/'results/review-evidence/manifest.json').read_text())
lines=['# File-level maintenance dataset: executed stage','','These are provisional change-activity cohorts. No corrective-maintenance association, ISO quality score or causal effect has been estimated.','','| Repository | File × baseline rows | Baseline clock shifts | Deletion / unresolved move |','|---|---:|---:|---:|']
for r in man:
 p=BASE/'results/file-cohorts'/r['csv'];assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']
 with gzip.open(p,'rt',newline='') as f:
  rows=list(csv.DictReader(f))
 assert len(rows)==r['file_baseline_rows']
 assert all(x['confirmed_corrective_changes']=='' and x['scientifically_admitted']=='False' for x in rows)
 assert len({(x['snapshot'],x['baseline_path']) for x in rows})==len(rows)
 differing=sum(x['following365_raw_changes']!=x['following365_ancestry_clock_changes'] for x in rows)
 r['raw_vs_ancestry_count_disagreement_rows']=differing
 lines.append(f"| {r['repository']} | {len(rows):,} | {r['baseline_clock_shift_rows']:,} | {r['followup_deletion_or_unresolved_move_rows']:,} |")
lines+=['','Each row links a frozen production path, source size, declaration counts and rule-specific findings to a conservative file lineage. Incomplete rules retain blank findings. Following-year raw mainline change counts are provided, with a separate ancestry-clock diagnostic. These are not deduplicated corrective episodes or developer effort.','', 'The ancestry clock is the running maximum commit timestamp in mainline order. It prevents a descendant from appearing before its parent but changes the temporal interpretation; it is reported separately and has not replaced the protocol outcome. A shifted baseline or disagreement requires review before selecting analysis windows.','']
for r in man:lines.append(f"- {r['repository']}: {r['raw_vs_ancestry_count_disagreement_rows']:,} rows differ between raw-date and ancestry-clock follow-up counts.")
lines+=['','## Lineage and scope limits','','Exact-content moves are linked only for unique deletion/addition pairs within a single mainline change. Edited moves are unresolved. Deletions remain explicit rather than being counted as a year without changes. File movement into tests, vendored code or another scope requires validation; future counts follow the baseline lineage and do not prove that every future path remains production code. God Class controls should be restricted to files with classes; Long Method controls to files with named definitions. Per-file resolved API exposure is not yet available for equivalent API-reference controls.','','## Review pilot','',f"Retrieved detail and timeline pages for {len(review)} sampled PRs. {sum(bool(r['ready_for_review_events']) for r in review)} contain an explicit readiness/draft transition; {sum(r.get('sample_commit_equals_merge_commit',False) for r in review)} match the sampled commit to the returned merge commit. Missing readiness events cannot automatically be replaced with creation time. Mismatched merge identities need tracing through squash/rebase/forward-port history. This selected merged-PR pilot cannot estimate open/closed-unmerged duration outcomes.",'', 'Five assistant-drafted classification suggestions are stored separately from independent labels. They rely on PR narratives and are not accepted corrective outcomes.','','## Next dependency','','Independent detector and corrective-change validation remains pending. Resolve commit/PR identity, edited renames, scope exits and time-window anomalies before modelling. Tomcat issue access remains limited by login requirements at the tested exports. No thresholds, hypotheses or primary outcomes were changed after observing an association.']
(BASE/'results/file-cohorts/STAGE_REPORT.md').write_text('\n'.join(lines)+'\n')
(BASE/'results/file-cohorts/validation.json').write_text(json.dumps(man,indent=2)+'\n')
print('\n'.join(lines))
