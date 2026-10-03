"""Audit preserved first-parent history and inventory annual source trees (no scans)."""
import argparse, collections, datetime as dt, gzip, hashlib, json, subprocess
from pathlib import Path
EXT={'.py':'python','.java':'java','.c':'c','.h':'c_header','.cpp':'cpp','.cc':'cpp','.cxx':'cpp','.hpp':'cpp_header','.cs':'csharp','.js':'javascript','.ts':'typescript'}
def git(repo,*args):
 return subprocess.check_output(['git','--git-dir',str(repo),*args],text=True,encoding='utf-8',errors='replace')
def audit(repo,cutoff):
 history=[]
 for line in git(repo,'log','--first-parent','--format=%H %ct %cI').splitlines():
  h,t,iso=line.split(' ',2);history.append({'commit':h,'committer_unix':int(t),'committer_date':iso})
 # Freeze a reachable endpoint at/before the declared cutoff, never use future-dated HEAD.
 endpoint=next(x for x in history if x['committer_unix']<=cutoff.timestamp())
 history=history[history.index(endpoint):];git_root=history[-1]
 root=next(x for x in reversed(history) if any(Path(p).suffix.lower() in EXT for p in git(repo,'ls-tree','-r','--name-only',x['commit']).splitlines()))
 undated=root['committer_unix']==0
 # Preserve an undated source import separately; never treat Unix epoch as product age.
 sampling_root=next(x for x in reversed(history) if x['committer_unix']>0) if undated else root
 y0=dt.datetime.fromtimestamp(sampling_root['committer_unix'],dt.timezone.utc).year
 observations=[{'label':'undated-import' if undated else 'earliest-'+str(y0),**root}]
 if undated:observations.append({'label':'earliest-dated-'+str(y0),**sampling_root})
 for year in range(y0+1,cutoff.year):
  boundary=dt.datetime(year+1,1,1,tzinfo=dt.timezone.utc).timestamp()
  choice=next((x for x in history if x['committer_unix']<boundary),None)
  if choice:observations.append({'label':str(year),**choice})
 observations.append({'label':'endpoint-'+str(cutoff.year),**endpoint})
 trees={}
 for sample in observations:
  h=sample['commit']
  if h not in trees:
   paths=git(repo,'ls-tree','-r','--name-only',h).splitlines();counts=collections.Counter(EXT.get(Path(p).suffix.lower(),'other') for p in paths)
   trees[h]={'tracked_files':len(paths),'tracked_language_files':dict(sorted(counts.items())),'top_level_paths':dict(collections.Counter(p.split('/')[0] for p in paths).most_common(20))}
  sample['inventory']=trees[h]
 return {'schema_version':'history-audit/1','status':'inventory_only_not_measurement','repository':git(repo,'config','--get','remote.origin.url').strip(),'cutoff_utc':cutoff.isoformat(),'endpoint':endpoint,'earliest_first_parent':git_root,'earliest_source':root,'undated_source_import':undated,'reachable_roots':git(repo,'rev-list','--max-parents=0',endpoint['commit']).splitlines(),'first_parent_commits':len(history),'elapsed_years':(endpoint['committer_unix']-sampling_root['committer_unix'])/(365.2425*86400),'timestamp_reversals':sum(a['committer_unix']<b['committer_unix'] for a,b in zip(history,history[1:])),'observations':observations,'history':history,'scope_warning':'Counts cover tracked paths; no production/generated/vendor exclusions or parser admission applied.'}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--cache',type=Path,required=True);ap.add_argument('--repositories',nargs='*');ap.add_argument('--output',type=Path,required=True);ap.add_argument('--cutoff',required=True);a=ap.parse_args();cutoff=dt.datetime.fromisoformat(a.cutoff);assert cutoff.tzinfo
 a.output.mkdir(parents=True,exist_ok=True)
 for repo in sorted(a.cache.iterdir()):
  if not (repo/'HEAD').exists() or (a.repositories and repo.name not in a.repositories):continue
  result=audit(repo,cutoff)
  raw=gzip.compress((json.dumps(result.pop('history'),sort_keys=True,separators=(',',':'))+'\n').encode(),mtime=0)
  history_path=repo.name+'.history.json.gz';(a.output/history_path).write_bytes(raw)
  result['history_archive']={'file':history_path,'sha256':hashlib.sha256(raw).hexdigest()}
  (a.output/(repo.name+'.json')).write_text(json.dumps(result,indent=2)+'\n');print(repo.name,round(result['elapsed_years'],1),len(result['observations']),result['earliest_first_parent']['committer_date'],flush=True)
