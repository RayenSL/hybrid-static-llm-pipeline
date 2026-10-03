"""Extract frozen mainline metadata and a deterministic issue-evidence pilot.

No bug labels or association estimates are inferred from message keywords.
Blob-filtered clones are sufficient for commit metadata, not hunk validation.
"""
import argparse, csv, datetime as dt, gzip, hashlib, json, random, re, subprocess
import urllib.request, urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'analysis/maintenance_associations'
EV=ROOT/'analysis/multilanguage_evolution'
IDS=['jenkinsci__jenkins','apache__tomcat','odoo__odoo']

def git(repo,*args):
 return subprocess.check_output(['git','--git-dir',str(repo),*args])
def digest(b):return hashlib.sha256(b).hexdigest()
def write_json(p,x):p.write_text(json.dumps(x,indent=2)+'\n')

def run(cache,out):
 out.mkdir(parents=True,exist_ok=True)
 script_sha256=digest(Path(__file__).read_bytes())
 totals=[]; samples=[]; acquisitions=[]
 for rid in IDS:
  repo=cache/rid
  manifest=json.loads((EV/f'selection/histories/{rid}.json').read_text())
  endpoint=manifest['endpoint']['commit']
  if git(repo,'rev-parse','--is-shallow-repository').decode().strip() != 'false':
   raise ValueError('Shallow history is inadmissible')
  verified=[]
  for s in manifest['observations']:
   actual=git(repo,'rev-parse',s['commit']+'^{commit}').decode().strip()
   subprocess.run(['git','--git-dir',str(repo),'merge-base','--is-ancestor',actual,endpoint],check=True)
   verified.append({'snapshot':s['label'],'commit':actual,'tree':git(repo,'rev-parse',actual+'^{tree}').decode().strip()})
  raw=git(repo,'log','--first-parent','--format=%H%x00%P%x00%ct%x00%B%x00',endpoint)
  packed=gzip.compress(raw,mtime=0);(out/(rid+'.mainline-log.gz')).write_bytes(packed)
  fields=raw.decode('utf-8','replace').split('\x00');events=[]
  for i in range(0,len(fields)-3,4):
   h,parents,ts,body=fields[i:i+4];h=h.strip()
   if not h:continue
   year=dt.datetime.fromtimestamp(int(ts),dt.timezone.utc).year
   refs=sorted(set(re.findall(r'JENKINS-\d+|https?://[^\s<>]+|#\d+|(?i:bug)\s+\d{4,}',body)))
   candidate=bool(re.search(r'(?i)\b(?:fix(?:es|ed|ing)?|bug|regression)\b|\[FIX\]',body))
   events.append({'repository':rid,'commit':h,'parents':parents.split(),'timestamp':int(ts),'year':year,'message':body,'references':refs,'keyword_candidate':candidate,'corrective_label':'uncertain'})
  if len(events) != int(git(repo,'rev-list','--first-parent','--count',endpoint)):
   raise ValueError('Parsed event count differs from Git ancestry count')
  data=gzip.compress(('\n'.join(json.dumps(e,sort_keys=True) for e in events)+'\n').encode(),mtime=0)
  (out/(rid+'.events.jsonl.gz')).write_bytes(data)
  for year in range(2007,2026):
   group=[e for e in events if e['year']==year]
   totals.append({'repository':rid,'year':year,'mainline_events':len(group),'keyword_candidates':sum(e['keyword_candidate'] for e in group),'events_with_reference_syntax':sum(bool(e['references']) for e in group),'merge_events':sum(len(e['parents'])>1 for e in group)})
  # Fixed pilot years, keyword strata, seeded sample. No outcome-dependent selection.
  for year in [2014,2019,2024]:
   for flag in [False,True]:
    group=sorted([e for e in events if e['year']==year and e['keyword_candidate']==flag],key=lambda e:e['commit'])
    rng=random.Random(f'20260922:{rid}:{year}:{flag}')
    for e in rng.sample(group,min(5,len(group))):
     samples.append({**e,'stratum_size':len(group),'selection_probability':min(5,len(group))/len(group),'review_status':'pending_independent_review'})
  acquisitions.append({'repository':rid,'origin':git(repo,'config','--get','remote.origin.url').decode().strip(),'endpoint':endpoint,'verified_snapshots':verified,'mainline_events':len(events),'timestamp_reversals':sum(a['timestamp']<b['timestamp'] for a,b in zip(events,events[1:])),'raw_sha256':digest(packed),'events_sha256':digest(data),'blob_filter':True,'source_blob_validation_complete':False})
  print(rid,len(events),'events; 21 frozen commits verified',flush=True)
 with (out/'message-coverage.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(totals[0]));w.writeheader();w.writerows(totals)
 write_json(out/'history-acquisition.json',acquisitions)
 # First-parent diffs avoid counting a merge plus its constituent commits.
 # Rename detection is deliberately deferred: it may require absent blobs.
 for e in samples:
  repo=cache/e['repository']
  args=['diff-tree','--no-commit-id','--name-status','--no-renames','-r','-z']
  if e['parents']:args += [e['parents'][0],e['commit']]
  else:args += ['--root',e['commit']]
  raw=git(repo,*args); fields=raw.decode('utf-8','replace').split('\x00')
  e['changed_paths']=[{'status':fields[i], 'path':fields[i+1]} for i in range(0,len(fields)-1,2)]
  e['diff_sha256']=digest(raw)
  e['lineage_status']='rename_and_hunk_validation_pending'
 write_json(out/'validation-sample.json',samples)
 # Limited public endpoint probes: one PR reference per repo per fixed pilot year.
 responses=out/'http';responses.mkdir(exist_ok=True);http=[]
 for rid in IDS:
  for year in [2014,2019,2024]:
   pattern = r'(?:show_bug\.cgi\?id=|\bBZ\s+)(\d+)' if rid=='apache__tomcat' else r'#(\d+)'
   candidates=[e for e in samples if e['repository']==rid and e['year']==year and re.search(pattern,e['message'])]
   if not candidates:
    http.append({'repository':rid,'year':year,'status':'no_supported_reference_in_sample'});continue
   e=sorted(candidates,key=lambda e:e['commit'])[0];number=re.search(pattern,e['message']).group(1)
   url=('https://bz.apache.org/bugzilla/rest/bug/'+number) if rid=='apache__tomcat' else ('https://api.github.com/repos/'+rid.replace('__','/')+'/issues/'+number)
   path=responses/f'{rid}-{year}-{number}.json'
   req=urllib.request.Request(url,headers={'Accept':'application/vnd.github+json','User-Agent':'maintenance-association-research'})
   record={'repository':rid,'year':year,'commit':e['commit'],'url':url,'retrieved_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'identity_validated':False}
   try:
    with urllib.request.urlopen(req,timeout=40) as r: body=r.read();record['http_status']=r.status
   except urllib.error.HTTPError as ex:body=ex.read();record['http_status']=ex.code
   except (OSError,TimeoutError) as ex:record['network_error']=str(ex);http.append(record);continue
   path.write_bytes(body);record['sha256']=digest(body);record['raw_file']=str(path.relative_to(out))
   try:
    obj=json.loads(body);record['is_pull_request']='pull_request' in obj;record['title']=obj.get('title');record['created_at']=obj.get('created_at');record['closed_at']=obj.get('closed_at')
   except ValueError:record['parse_error']=True
   http.append(record)
 write_json(out/'public-evidence-probes.json',http)
 write_json(out/'run-status.json',{'protocol_sha256':digest((BASE/'PROTOCOL.md').read_bytes()),'script_sha256':script_sha256,'associations_estimated':False,'confirmed_corrective_labels':0,'validation_sample_size':len(samples),'warning':'Message reference syntax is not verified issue linkage. API probes do not establish historical coverage or review readiness. Independent validation pending.'})

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--cache',type=Path,default=ROOT/'tmp/maintenance-associations/git');ap.add_argument('--output',type=Path,default=BASE/'results/history-pilot');ap.add_argument('--repositories',nargs='+',choices=IDS);a=ap.parse_args();IDS=a.repositories or IDS;run(a.cache,a.output)
