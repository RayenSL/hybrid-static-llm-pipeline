"""Trace directly edited Long Methods and source-declared obsolete-use transitions."""
import argparse,collections,csv,hashlib,json,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BASE=Path(__file__).resolve().parent
BUNDLE=ROOT/'analysis/multilanguage_evolution/results/three-rule-evidence.tar.gz'
CORRECTION=ROOT/'analysis/maintenance_associations/results/calendar-frontier-v0.2'
REPOS=('odoo__odoo','jenkinsci__jenkins','apache__tomcat');YEARS=range(2007,2026)
CORRECTED_ODOO={2018,2019,2020,2023,2024};RULES=('LongMethod','ObsoleteApiUsage')
P=argparse.ArgumentParser();P.add_argument('--output',type=Path,required=True);a=P.parse_args();OUT=a.output.resolve()
if OUT.exists() and any(OUT.iterdir()):raise SystemExit(f'Refusing to overwrite {OUT}')
OUT.mkdir(parents=True,exist_ok=True)
def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(name,rows,fields):
 with (OUT/name).open('w',newline='',encoding='utf8') as f:
  w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n',extrasaction='ignore');w.writeheader();w.writerows(rows)
def dump(name,obj):(OUT/name).write_text(json.dumps(obj,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf8')
input_hashes={'bundle':sha(BUNDLE),'corrections':{}}
with tarfile.open(BUNDLE,'r:gz') as tar:
 def load(repo,year):
  out={}
  for kind in ('syntax','three-rules'):
   if repo=='odoo__odoo' and year in CORRECTED_ODOO:
    path=CORRECTION/f'{repo}-{year}.{kind}.json';raw=path.read_bytes();input_hashes['corrections'][str(path.relative_to(ROOT))]=hashlib.sha256(raw).hexdigest()
   else:raw=tar.extractfile(f'raw/{repo}-{year}.{kind}.json').read()
   out[kind]=json.loads(raw)
  if out['syntax']['commit']!=out['three-rules']['commit']:raise ValueError('Commit mismatch')
  return out
 def rule(scan,name):return next(r for r in scan['three-rules']['rules'] if r['rule']==name)
 lm=[];api=[];lm_pair_support=[];api_pair_support=[];positives_by_scan={};complete_by_scan={}
 for repo in REPOS:
  previous=load(repo,2007)
  positives_by_scan[(repo,2007)]={(r['path'],r['symbol']) for r in rule(previous,'ObsoleteApiUsage')['findings']}
  complete_by_scan[(repo,2007)]=rule(previous,'ObsoleteApiUsage')['status']=='complete'
  for year in range(2007,2025):
   current=load(repo,year+1)
   base_rules={name:rule(previous,name) for name in RULES};next_rules={name:rule(current,name) for name in RULES}
   positives_by_scan[(repo,year+1)]={(r['path'],r['symbol']) for r in next_rules['ObsoleteApiUsage']['findings']}
   complete_by_scan[(repo,year+1)]=next_rules['ObsoleteApiUsage']['status']=='complete'
   if base_rules['LongMethod']['status']=='complete' and next_rules['LongMethod']['status']=='complete' and previous['syntax']['status']['syntax']=='complete' and current['syntax']['status']['syntax']=='complete':
    before=collections.defaultdict(list);after=collections.defaultdict(list)
    for d in previous['syntax']['definitions']:before[(d['path'],d['symbol'])].append(d)
    for d in current['syntax']['definitions']:after[(d['path'],d['symbol'])].append(d)
    base_files={r['path'] for r in previous['three-rules']['inventory']};next_files={r['path'] for r in current['three-rules']['inventory']}
    base_findings=collections.Counter((r['path'],r['symbol']) for r in base_rules['LongMethod']['findings'])
    next_findings=collections.Counter((r['path'],r['symbol']) for r in next_rules['LongMethod']['findings'])
    counts=collections.Counter()
    for finding in base_rules['LongMethod']['findings']:
     key=(finding['path'],finding['symbol']);path,symbol=key;state=''
     if base_findings[key]!=1 or len(before[key])!=1:state='baseline_ambiguous'
     elif path not in base_files:raise ValueError('Finding source absent from baseline inventory')
     elif before[key][0]['metrics']['cyclomatic_complexity']<=10:raise ValueError('Baseline finding/complexity mismatch')
     elif path not in next_files:state='path_absent'
     elif len(after[key])>1:state='next_ambiguous'
     elif len(after[key])==0:state='definition_absent'
     else:
      b=before[key][0];n=after[key][0]
      if (n['metrics']['cyclomatic_complexity']>10) != (next_findings[key]==1):raise ValueError('Next finding/complexity mismatch')
      changed=b['snippet_sha256']!=n['snippet_sha256']
      state='directly_changed' if changed else 'same_snippet'
     row={'repository':repo,'baseline_year':year,'next_year':year+1,'baseline_commit':previous['syntax']['commit'],
          'next_commit':current['syntax']['commit'],'path':path,'symbol':symbol,'state':state,
          'baseline_cc':'','next_cc':'','delta_cc':'','baseline_lines':'','next_lines':'','delta_lines':'','still_flagged':''}
     if len(before[key])==1:
      b=before[key][0];row['baseline_cc']=b['metrics']['cyclomatic_complexity'];row['baseline_lines']=b['metrics']['physical_lines']
     if state in ('directly_changed','same_snippet'):
      row['next_cc']=n['metrics']['cyclomatic_complexity'];row['delta_cc']=n['metrics']['cyclomatic_complexity']-b['metrics']['cyclomatic_complexity']
      row['next_lines']=n['metrics']['physical_lines'];row['delta_lines']=n['metrics']['physical_lines']-b['metrics']['physical_lines'];row['still_flagged']=int(next_findings[key]==1)
     lm.append(row);counts[state]+=1
    lm_pair_support.append({'repository':repo,'baseline_year':year,'next_year':year+1,'status':'complete','baseline_findings':len(base_rules['LongMethod']['findings']),**counts})
   else:lm_pair_support.append({'repository':repo,'baseline_year':year,'next_year':year+1,'status':'incomplete','baseline_findings':'','reason':f"baseline={base_rules['LongMethod']['status']};next={next_rules['LongMethod']['status']}"})
   if base_rules['ObsoleteApiUsage']['status']=='complete' and next_rules['ObsoleteApiUsage']['status']=='complete':
    bfiles={r['path']:r['sha256'] for r in previous['three-rules']['inventory']};nfiles={r['path']:r['sha256'] for r in current['three-rules']['inventory']}
    bfind=collections.Counter((r['path'],r['symbol']) for r in base_rules['ObsoleteApiUsage']['findings'])
    nfind=collections.Counter((r['path'],r['symbol']) for r in next_rules['ObsoleteApiUsage']['findings'])
    counts=collections.Counter()
    for finding in base_rules['ObsoleteApiUsage']['findings']:
     path,symbol=finding['path'],finding['symbol'];key=(path,symbol);decl=finding.get('declaration_path','')
     if bfind[key]!=1 or nfind[key]>1:state='ambiguous_identity'
     elif path not in bfiles:raise ValueError('API source absent from baseline inventory')
     elif path not in nfiles:state='caller_path_absent'
     else:
      changed=bfiles[path]!=nfiles[path]
      if nfind[key]==1:state='redetected_changed_caller' if changed else 'redetected_unchanged_caller'
      elif not changed:state='absent_unchanged_caller'
      elif decl and decl in bfiles and decl in nfiles and bfiles[decl]==nfiles[decl]:state='candidate_migration_unchanged_declaration'
      else:state='absent_changed_caller_declaration_changed_or_unknown'
     api.append({'repository':repo,'baseline_year':year,'next_year':year+1,'baseline_commit':previous['syntax']['commit'],
                 'next_commit':current['syntax']['commit'],'path':path,'symbol':symbol,'declaration_path':decl,'state':state,
                 'caller_changed':int(path in bfiles and path in nfiles and bfiles[path]!=nfiles[path]),
                 'declaration_unchanged':int(bool(decl and decl in bfiles and decl in nfiles and bfiles[decl]==nfiles[decl]))})
     counts[state]+=1
    api_pair_support.append({'repository':repo,'baseline_year':year,'next_year':year+1,'status':'complete','baseline_findings':len(base_rules['ObsoleteApiUsage']['findings']),**counts})
   else:api_pair_support.append({'repository':repo,'baseline_year':year,'next_year':year+1,'status':'incomplete','baseline_findings':'','reason':f"baseline={base_rules['ObsoleteApiUsage']['status']};next={next_rules['ObsoleteApiUsage']['status']}"})
   previous=current
# Positive-detection run lengths, censored at missing intervals. A run beginning in 2007 is left-truncated.
runs=[]
for repo in REPOS:
 active={}
 for year in YEARS:
  complete=complete_by_scan[(repo,year)]
  current=positives_by_scan[(repo,year)] if complete else set()
  for key,start in list(active.items()):
   if not complete or key not in current:
    runs.append({'repository':repo,'path':key[0],'symbol':key[1],'first_year':start,'last_year':year-1,
                 'observed_scans':year-start,'end':'missing_scan' if not complete else 'not_redetected',
                 'left_truncated':int(start==2007)})
    del active[key]
  if complete:
   for key in current:
    if key not in active:active[key]=year
 for key,start in active.items():
  runs.append({'repository':repo,'path':key[0],'symbol':key[1],'first_year':start,'last_year':2025,
               'observed_scans':2026-start,'end':'right_censored','left_truncated':int(start==2007)})
summary=[]
for repo in REPOS:
 for rows,name in ((lm,'LongMethod'),(api,'ObsoleteApiUsage')):
  sub=[r for r in rows if r['repository']==repo];states=collections.Counter(r['state'] for r in sub)
  record={'repository':repo,'rule':name,'baseline_observations':len(sub),'states':dict(sorted(states.items()))}
  if name=='LongMethod':
   edited=[r for r in sub if r['state']=='directly_changed'];record['directly_changed']=len(edited);record['still_flagged']=sum(r['still_flagged'] for r in edited)
   record['still_flagged_fraction']=record['still_flagged']/len(edited) if edited else None
   record['delta_cc_negative']=sum(r['delta_cc']<0 for r in edited);record['delta_cc_zero']=sum(r['delta_cc']==0 for r in edited);record['delta_cc_positive']=sum(r['delta_cc']>0 for r in edited)
  summary.append(record)
LM_FIELDS=['repository','baseline_year','next_year','baseline_commit','next_commit','path','symbol','state','baseline_cc','next_cc','delta_cc','baseline_lines','next_lines','delta_lines','still_flagged']
API_FIELDS=['repository','baseline_year','next_year','baseline_commit','next_commit','path','symbol','declaration_path','state','caller_changed','declaration_unchanged']
write('long-method-transitions.csv',lm,LM_FIELDS);write('api-transitions.csv',api,API_FIELDS)
write('long-method-pair-support.csv',lm_pair_support,['repository','baseline_year','next_year','status','baseline_findings','reason','baseline_ambiguous','path_absent','next_ambiguous','definition_absent','directly_changed','same_snippet'])
write('api-pair-support.csv',api_pair_support,['repository','baseline_year','next_year','status','baseline_findings','reason','ambiguous_identity','caller_path_absent','redetected_changed_caller','redetected_unchanged_caller','absent_unchanged_caller','candidate_migration_unchanged_declaration','absent_changed_caller_declaration_changed_or_unknown'])
write('api-observed-runs.csv',sorted(runs,key=lambda r:(r['repository'],r['path'],r['symbol'],r['first_year'])),['repository','path','symbol','first_year','last_year','observed_scans','end','left_truncated'])
dump('summary.json',summary)
dump('provenance.json',{'protocol_sha256':sha(BASE/'PROTOCOL.md'),'script_sha256':sha(Path(__file__)),'inputs':input_hashes,'repositories':REPOS,'years':[2007,2025]})
dump('SHA256SUMS.json',{p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file()})
for r in summary:print(r,flush=True)
