"""Compare original and amended snapshot measurements, preserving both."""
import csv,hashlib,json,tarfile
from pathlib import Path
BASE=Path(__file__).resolve().parent; EV=BASE.parent/'multilanguage_evolution'; OUT=BASE/'results/calendar-frontier-v0.2'
manifest=json.loads((OUT/'manifest.json').read_text())
frozen=json.loads((BASE/'protocols/calendar-frontier-v0.2.json').read_text())
assert len(manifest)==len(frozen['replacements'])==5
rows=[]
with tarfile.open(EV/'results/three-rule-evidence.tar.gz','r:gz') as archive:
 for record in manifest:
  name='odoo__odoo-'+record['snapshot']+'.three-rules.json'
  old=json.load(archive.extractfile(next(m for m in archive.getmembers() if m.name.endswith('/'+name) or m.name==name)))
  new=json.loads((OUT/name).read_text())
  assert old['commit']==record['frozen_commit'] and new['commit']==record['proposed_commit']
  assert old['adapter_sha256']==new['adapter_sha256'] and old['scope_sha256']==new['scope_sha256'] and old['tool']==new['tool']
  assert record['semantic_replay_identical'] and record['syntax_replay_identical']
  for o,n in zip(old['rules'],new['rules']):
   assert o['rule']==n['rule']
   rows.append({'year':record['snapshot'],'rule':n['rule'],'original_commit':old['commit'],'replacement_commit':new['commit'],'original_count':o['finding_count'],'replacement_count':n['finding_count'],'count_difference':n['finding_count']-o['finding_count'] if n['finding_count'] is not None and o['finding_count'] is not None else None,'original_eligible':o['eligible_count'],'replacement_eligible':n['eligible_count'],'original_status':o['status'],'replacement_status':n['status'],'original_production_files':len(old['inventory']),'replacement_production_files':len(new['inventory']),'original_physical_lines':sum(x['physical_lines'] for x in old['inventory']),'replacement_physical_lines':sum(x['physical_lines'] for x in new['inventory'])})
with (OUT/'comparison.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
lines=['# Calendar-frontier correction: measured results','','All five replacement snapshots were exported, scanned and replayed. Syntax and semantic replay were identical for each observation. The adapter fingerprint, production scope and recorded runtime match the corresponding original observations. The selection verification confirms that every replacement is the latest first-parent node satisfying the amended date rule.','','| Year | Original long-method count | Replacement count | Difference | Replacement eligible methods |','|---|---:|---:|---:|---:|']
for r in rows:
 if r['rule']=='LongMethod': lines.append(f"| {r['year']} | {r['original_count']} | {r['replacement_count']} | {r['count_difference']:+d} | {r['replacement_eligible']} |")
lines+=['','| Year | Rule | Original count | Replacement count |','|---|---|---:|---:|']
for r in rows:
 if r['rule']!='LongMethod': lines.append(f"| {r['year']} | {r['rule']} | {r['original_count']} | {r['replacement_count']} |")
lines+=['','God-class and source-declared obsolete-API counts must be interpreted under their fixed operational definitions; a zero does not establish the absence of design problems or third-party deprecated-API use. Full counts, denominators, coverage and source sizes are in `comparison.csv`.','','The corrected commits are consistent with the recorded first-parent ancestor dates before each year boundary. They are not independently established historical branch tips. These descriptive measurements therefore retain a sampling limitation. Original findings and thesis figures have been preserved; this report does not silently replace their data.','','## Admission status','','Calendar snapshot rescanning is complete. Association inference remains on hold. Rebuild affected maintenance cohorts from the replacement findings and baselines; settle event-window handling of timestamp reversals; validate lineage, unflagged controls, detector findings and independently labelled corrective changes before estimation. The previous cohorts and review packets still refer to the original snapshots. No correlations, causal effects or validated maintenance outcomes are reported.']
(OUT/'REPORT.md').write_text('\n'.join(lines)+'\n')
(OUT/'inference-gate.json').write_text(json.dumps({'status':'time_based_inference_on_hold','calendar_rescans_complete':True,'replacement_count':5,'replay_verified':True,'original_evidence_preserved':True,'cohorts_rebuilt':False,'independent_validation_complete':False,'associations_estimated':False,'remaining':['Rebuild affected cohorts','Resolve follow-up chronology and lineage','Independent detector and outcome validation']},indent=2)+'\n')
seals={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='SHA256SUMS.json'}
(OUT/'SHA256SUMS.json').write_text(json.dumps(seals,indent=2)+'\n')
print('\n'.join(lines))
