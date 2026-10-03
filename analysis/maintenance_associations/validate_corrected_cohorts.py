"""Reconcile corrected cohorts to source evidence and retain timing diagnostics."""
import collections,csv,gzip,hashlib,json
from pathlib import Path
BASE=Path(__file__).resolve().parent;OUT=BASE/'results/file-cohorts-v0.2';CORRECTION=BASE/'results/calendar-frontier-v0.2'
def read(path):
 with gzip.open(path,'rt',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
oldpath=BASE/'results/file-cohorts/odoo__odoo.csv.gz';newpath=OUT/'odoo__odoo.csv.gz'
old=read(oldpath);new=read(newpath)
for folder,path in [(BASE/'results/file-cohorts',oldpath),(OUT,newpath)]:
 seal=next(r for r in json.loads((folder/'manifest.json').read_text()) if r['repository']=='odoo__odoo')
 assert sha(path)==seal['sha256']
assert len({(r['snapshot'],r['baseline_path']) for r in new})==len(new)
assert all(r['confirmed_corrective_changes']=='' and r['scientifically_admitted']=='False' for r in new)
manifest=json.loads((CORRECTION/'manifest.json').read_text());changed={r['snapshot'] for r in manifest}
assert [r for r in old if r['snapshot'] not in changed]==[r for r in new if r['snapshot'] not in changed]
checks=[]
for record in manifest:
 label=record['snapshot'];name='odoo__odoo-'+label
 d=json.loads((CORRECTION/(name+'.three-rules.json')).read_text());s=json.loads((CORRECTION/(name+'.syntax.json')).read_text())
 rows={r['baseline_path']:r for r in new if r['snapshot']==label}
 assert set(rows)=={f['path'] for f in d['inventory']}
 definitions=collections.Counter(x['path'] for x in s['definitions']);classes=collections.Counter(x['path'] for x in d['class_metrics'])
 counts={r['rule']:collections.Counter(f['path'] for f in r['findings']) for r in d['rules']}
 for f in d['inventory']:
  r=rows[f['path']]
  assert r['baseline_commit']==d['commit']==record['proposed_commit']
  assert int(r['file_ploc'])==f['physical_lines'] and int(r['named_definitions'])==definitions[f['path']] and int(r['classes'])==classes[f['path']]
  for rule,c in counts.items():assert int(r[rule+'_findings'])==c[f['path']]
 for rule in d['rules']:assert sum(int(r[rule['rule']+'_findings']) for r in rows.values())==rule['finding_count']
 checks.append({'snapshot':label,'files':len(rows),'commit':d['commit'],'inventory_and_per_file_metrics_match':True})
eligibility=json.loads((OUT/'replacement-eligibility.json').read_text())
assert len(eligibility)==15 and all(r['temporally_eligible'] for r in eligibility)
summaries=[]
for label in sorted({r['snapshot'] for r in new}):
 before=[r for r in old if r['snapshot']==label];after=[r for r in new if r['snapshot']==label]
 summaries.append({'snapshot':label,'replaced':label in changed,'corrected_baseline_clock_shift_seconds':max(int(r['baseline_clock_shift_seconds']) for r in after),'original_rows':len(before),'corrected_rows':len(after),'original_baseline_clock_shift_rows':sum(int(r['baseline_clock_shift_seconds'])>0 for r in before),'corrected_baseline_clock_shift_rows':sum(int(r['baseline_clock_shift_seconds'])>0 for r in after),'original_raw_vs_ancestry_disagreements':sum(r['following365_raw_changes']!=r['following365_ancestry_clock_changes'] for r in before),'corrected_raw_vs_ancestry_disagreements':sum(r['following365_raw_changes']!=r['following365_ancestry_clock_changes'] for r in after),'original_deletion_or_unresolved_move_rows':sum(bool(r['first_followup_deletion_commit']) for r in before),'corrected_deletion_or_unresolved_move_rows':sum(bool(r['first_followup_deletion_commit']) for r in after)})
with (OUT/'comparison.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(summaries[0]));w.writeheader();w.writerows(summaries)
validation={'original_rows':len(old),'corrected_rows':len(new),'unmodified_years_identical':True,'unmodified_year_count':len(summaries)-len(changed),'replacement_metric_checks':checks,'replacement_rule_eligibility_checks':len(eligibility),'corrective_labels_blank':True,'associations_estimated':False,'diagnostics':summaries}
(OUT/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')
lines=['# Corrected Odoo maintenance cohort','','The cohort has been rebuilt from the five replacement snapshots in sampling amendment v0.2. Original outputs are retained. Actual commit timestamps still anchor the 365-day windows; the cumulative maximum timestamp remains a separate diagnostic, not a substituted outcome definition.','','| Year | Original file observations | Corrected file observations | Original shifted baselines | Corrected shifted baselines | Follow-up count disagreements (corrected) |','|---|---:|---:|---:|---:|---:|']
for r in summaries:
 if r['replaced'] or r['corrected_baseline_clock_shift_rows'] or r['corrected_raw_vs_ancestry_disagreements']:
  lines.append(f"| {r['snapshot']} | {r['original_rows']:,} | {r['corrected_rows']:,} | {r['original_baseline_clock_shift_rows']:,} | {r['corrected_baseline_clock_shift_rows']:,} | {r['corrected_raw_vs_ancestry_disagreements']:,} |")
lines+=['','Residual baseline shifts are '+', '.join(r['snapshot']+': '+str(r['corrected_baseline_clock_shift_seconds'])+' seconds' for r in summaries if r['corrected_baseline_clock_shift_seconds'])+'. Across all years, '+str(sum(r['corrected_raw_vs_ancestry_disagreements'] for r in summaries))+' file observations have different raw-date and ancestry-clock follow-up counts, compared with '+str(sum(r['original_raw_vs_ancestry_disagreements'] for r in summaries))+' originally. These differences are diagnostics, not evidence that one clock is historically correct.',f"The total changes from {len(old):,} to {len(new):,} file-at-snapshot observations. All {len(summaries)-len(changed)} unaffected years are identical row for row. Each replacement inventory, source-size measure, declaration count and per-file finding count matches its fresh scan. All 15 replacement rule observations pass the existing temporal eligibility conditions. A file can appear in several years; these rows are not independent projects or maintenance episodes.",'', '## Remaining limits','','Remaining shifted baselines and differences between raw-date and ancestry-clock follow-up counts are listed above and in `comparison.csv`. Fixing year-end snapshot selection does not remove internal timestamp reversals. Edited moves, deletions and scope exits still require handling before inference. Corrective-change labels remain blank; raw file-change activity is not a validated defect count, repair cost or deployment delay. The unchanged Jenkins and Tomcat cohorts remain in the original results directory.','','## Reproduction','','```sh','python3 analysis/maintenance_associations/build_file_cohorts.py --repository odoo__odoo --calendar-correction analysis/maintenance_associations/results/calendar-frontier-v0.2 --output analysis/maintenance_associations/results/file-cohorts-v0.2','python3 analysis/maintenance_associations/validate_corrected_cohorts.py','```','','Use a fresh output directory for a repeat extraction. A matching repeat gzip SHA-256 verifies deterministic rows and compression. The builder checks the event-database seal and replacement finding/syntax seals. Independent detector and corrective-outcome assessment remains required before association estimation.']
(OUT/'REPORT.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines))
