"""Prepare a stratified positive-finding precision pilot; does not estimate recall."""
import csv,json,random,tarfile
from pathlib import Path
from urllib.parse import quote
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[1]
rows=[]
with tarfile.open(ROOT/'analysis/multilanguage_evolution/results/three-rule-evidence.tar.gz') as archive:
 for member in archive:
  if not member.name.endswith('.three-rules.json'):continue
  stem=Path(member.name).name.removesuffix('.three-rules.json')
  rid,year=stem.rsplit('-',1)
  if year not in ['2014','2019','2024']:continue
  data=json.load(archive.extractfile(member))
  for rule in data['rules']:
   findings=sorted(rule['findings'],key=lambda f:(f['path'],f['line'],f.get('symbol','')))
   if not findings:continue
   n=min(5,len(findings));rng=random.Random(f'20260922:detector:{rid}:{year}:{findings[0]["rule"]}')
   for f in rng.sample(findings,n):
    rows.append({'repository':rid,'year':year,'commit':data['commit'],'rule':f['rule'],'path':f['path'],'line':f['line'],'symbol':f.get('symbol',''),'source_url':'https://github.com/'+rid.replace('__','/')+'/blob/'+data['commit']+'/'+quote(f['path'])+'#L'+str(f['line']),'stratum_size':len(findings),'selection_probability':n/len(findings),'detector_evidence':f,'source_archive_sha256':data['archive_sha256']})
p=BASE/'results';p.mkdir(exist_ok=True)
(p/'detector-positive-sample.json').write_text(json.dumps(rows,indent=2)+'\n')
fields=['repository','year','commit','rule','path','line','symbol','source_url','independent_rule_satisfied','rationale','reviewer']
with (p/'detector-positive-review.csv').open('w',newline='') as out:
 w=csv.DictWriter(out,fieldnames=fields);w.writeheader()
 for r in rows:w.writerow({k:r.get(k,'') for k in fields})
print(len(rows),'positive findings sampled; this pilot cannot estimate false negatives or recall.')
