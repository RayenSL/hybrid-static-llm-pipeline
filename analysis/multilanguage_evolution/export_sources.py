"""Export frozen source-only archives for coverage probes; reuse only matching seals."""
import argparse,concurrent.futures,hashlib,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
PATTERNS={'odoo__odoo':['*.py'],'apache__ofbiz-framework':['*.java'],'apache__tomcat':['*.java'],'elastic__elasticsearch':['*.java'],'jenkinsci__jenkins':['*.java']}
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--cache',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--repositories',nargs='+',required=True);ap.add_argument('--all-years',action='store_true');a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 jobs=[]
 for repo in a.repositories:
  h=json.loads((HERE/'selection/histories'/(repo+'.json')).read_text());samples=h['observations'] if a.all_years else [h['observations'][0],h['observations'][-1]]
  jobs.extend((repo,s) for s in samples)
 def export(job):
  repo,s=job;dest=a.output/(repo+'-'+s['label']+'.tar');seal=dest.with_suffix('.manifest.json');args=['git','--git-dir='+str(a.cache/repo)]
  if seal.exists():
   d=json.loads(seal.read_text())
   if d['commit']==s['commit'] and dest.exists() and sha(dest)==d['sha256']:return d
   raise ValueError('Existing archive seal mismatch: '+str(dest))
  paths=subprocess.check_output([*args,'ls-tree','-r','--name-only',s['commit']],text=True).splitlines();patterns=PATTERNS.get(repo,['*.c','*.h','*.cpp','*.cc','*.cxx','*.hpp']);patterns=[p for p in patterns if any(x.endswith(p[1:]) for x in paths)]
  if not patterns:raise ValueError('No selected-language source')
  with dest.with_suffix('.partial').open('wb') as f,dest.with_suffix('.log').open('w') as log:subprocess.run([*args,'archive','--format=tar',s['commit'],*patterns],stdout=f,stderr=log,check=True)
  dest.with_suffix('.partial').replace(dest);d={'repository':repo,'label':s['label'],'commit':s['commit'],'sha256':sha(dest),'patterns':patterns,'archive':dest.name};seal.write_text(json.dumps(d,indent=2)+'\n');return d
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
  for fut in concurrent.futures.as_completed([ex.submit(export,j) for j in jobs]):
   d=fut.result();print(d['repository'],d['label'],flush=True)
