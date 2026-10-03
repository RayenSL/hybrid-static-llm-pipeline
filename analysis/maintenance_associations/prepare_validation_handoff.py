"""Prepare current-snapshot detector review, including unflagged structural units."""
import argparse,csv,hashlib,json,random,tarfile
from pathlib import Path
from urllib.parse import quote
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1];EV=ROOT/'analysis/multilanguage_evolution'
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=BASE/'results/validation-handoff-v0.5');OUT=ap.parse_args().output
if OUT.exists():raise FileExistsError('Use a fresh output directory; preserve reviewer edits')
OUT.mkdir(parents=True);(OUT/'sources').mkdir();(OUT/'coordinator').mkdir()
YEARS={'2014','2019','2024'};data={};syntax={}
with tarfile.open(EV/'results/three-rule-evidence.tar.gz') as archive:
 for member in archive:
  name=Path(member.name).name
  for suffix,store in [('.three-rules.json',data),('.syntax.json',syntax)]:
   if name.endswith(suffix):
    key=name.removesuffix(suffix);rid,year=key.rsplit('-',1)
    if year in YEARS:store[key]=json.load(archive.extractfile(member))
correction=BASE/'results/calendar-frontier-v0.2'
for r in json.loads((correction/'manifest.json').read_text()):
 if r['snapshot'] not in YEARS:continue
 key=r['repository']+'-'+r['snapshot'];p=correction/(key+'.three-rules.json')
 assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']
 data[key]=json.loads(p.read_text());syntax[key]=json.loads((correction/(key+'.syntax.json')).read_text())
ledger=[];strata=[]
for key,d in sorted(data.items()):
 rid,year=key.rsplit('-',1);s=syntax[key];assert s['commit']==d['commit'];inventory={f['path']:f for f in d['inventory']}
 for rule in d['rules']:
  if rule['status']!='complete':continue
  name=rule['rule'];positives=sorted(rule['findings'],key=lambda f:(f['path'],f['line'],f.get('symbol','')))
  populations=[('flagged',positives)]
  if name=='LongMethod':
   units=[{'path':x['path'],'line':x['span']['line_start'],'symbol':x['symbol'],'source_sha256':x['source_sha256'],'metrics':x['metrics']} for x in s['definitions']]
  elif name=='GodClass':
   units=[{'path':x['path'],'line':x['line'],'symbol':x['symbol'],'source_sha256':inventory[x['path']]['sha256'],'metrics':x} for x in d['class_metrics'] if x.get('wmc_complete',True) and x['assessment'] in {'resolved','negative_by_WMC'}]
  else:units=None
  if units is not None:
   identity=lambda x:(x['path'],x['line'],x['symbol'])
   assert len({identity(x) for x in units})==len(units),'Duplicate review unit'
   flagged={identity(x) for x in positives};assert flagged<={identity(x) for x in units},'Finding cannot be mapped to an eligible unit'
   negatives=sorted([x for x in units if identity(x) not in flagged],key=identity)
   populations.append(('unflagged',negatives))
  for stratum,population in populations:
   n=min(5,len(population));seed=f'20260922:detector:{rid}:{year}:{name}' if stratum=='flagged' else f'20260922:detector-unflagged:{rid}:{year}:{name}'
   strata.append({'repository':rid,'year':year,'commit':d['commit'],'rule':name,'detector_stratum':stratum,'population':len(population),'sample_size':n,'selection_probability':n/len(population) if population else None,'seed':seed})
   for finding in random.Random(seed).sample(population,n):
    identity=[rid,year,d['commit'],name,finding['path'],finding['line'],finding['symbol']];case=hashlib.sha256(json.dumps(identity,separators=(',',':')).encode()).hexdigest()[:16]
    ledger.append({'case_id':case,'repository':rid,'year':year,'commit':d['commit'],'rule':name,'detector_stratum':stratum,'path':finding['path'],'line':finding['line'],'symbol':finding['symbol'],'source_sha256':finding['source_sha256'],'declaration_path':finding.get('declaration_path',''),'source_archive_sha256':d['archive_sha256'],'stratum_size':len(population),'selection_probability':n/len(population),'detector_evidence':finding})
# Archive source evidence locally, verifying against the sealed detector inventories.
for key,d in sorted(data.items()):
 rid,year=key.rsplit('-',1);selected=[r for r in ledger if r['repository']==rid and r['year']==year]
 archive=(ROOT/'tmp/maintenance-associations/calendar-frontier-v0.2-sources' if rid=='odoo__odoo' and year in {'2019','2024'} else ROOT/'tmp/multilanguage-evolution/annual-sources')/(key+'.tar')
 with archive.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==d['archive_sha256']
 inventory={f['path']:f for f in d['inventory']};needed={r['path'] for r in selected}|{r['declaration_path'] for r in selected if r['declaration_path']}
 with tarfile.open(archive) as t:
  for path in sorted(needed):
   raw=t.extractfile(t.getmember(path)).read();digest=hashlib.sha256(raw).hexdigest();assert digest==inventory[path]['sha256']
   dest=OUT/'sources'/(digest+Path(path).suffix)
   if dest.exists():assert dest.read_bytes()==raw
   else:dest.write_bytes(raw)
 for r in selected:
  r['source_file']='sources/'+r['source_sha256']+Path(r['path']).suffix
  r['declaration_file']='sources/'+inventory[r['declaration_path']]['sha256']+Path(r['declaration_path']).suffix if r['declaration_path'] else ''
assert len({r['case_id'] for r in ledger})==len(ledger)
order=sorted(ledger,key=lambda r:r['case_id']);random.Random(20260922).shuffle(order)
fields=['case_id','repository','year','commit','rule','path','line','symbol','source_file','declaration_file','source_url','independent_rule_satisfied','evidence','rationale','reviewer']
with (OUT/'detector-review.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
 for r in order:w.writerow({**{k:r[k] for k in fields if k in r},'source_url':'https://github.com/'+r['repository'].replace('__','/')+'/blob/'+r['commit']+'/'+quote(r['path'])+'#L'+str(r['line'])})
(OUT/'coordinator/detector-sampling-ledger.json').write_text(json.dumps({'strata':strata,'cases':ledger,'api_unflagged_controls_available':False},indent=2)+'\n')
for source,dest in [('results/history-pilot/independent-review.csv','corrective-review.csv'),('results/window-lineage-audit/independent-lineage-review.csv','lineage-review.csv')]:
 (OUT/dest).write_bytes((BASE/source).read_bytes())
previous=json.loads((BASE/'results/detector-positive-sample.json').read_text());newpositive=[r for r in ledger if r['detector_stratum']=='flagged']
oldkeys={(r['repository'],r['year'],r['commit'],r['rule'],r['path'],r['line'],r['symbol']) for r in previous};newkeys={(r['repository'],r['year'],r['commit'],r['rule'],r['path'],r['line'],r['symbol']) for r in newpositive}
summary={'detector_cases':len(ledger),'flagged_cases':len(newpositive),'unflagged_cases':len(ledger)-len(newpositive),'original_positive_cases':len(previous),'original_positive_cases_retained':len(oldkeys&newkeys),'original_positive_cases_superseded':len(oldkeys-newkeys),'corrective_cases':90,'lineage_cases':50,'api_unflagged_controls_available':False,'independent_labels_completed':False,'source_files':len(list((OUT/'sources').iterdir()))}
(OUT/'manifest.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
