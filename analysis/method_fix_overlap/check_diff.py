"""Compare Python line alignment against Git's zero-context hunk placement."""
import argparse,collections,csv,difflib,json,os,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=0);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
source=ROOT/'analysis/method_fix_overlap/results/v0.1/event-audit.csv'
seen={}
for row in csv.DictReader(source.open()):
 key=(row['repository'],row['old_blob'],row['new_blob'])
 seen[key]=None
keys=sorted(seen)
if a.limit:keys=[keys[i] for i in range(0,len(keys),max(1,len(keys)//a.limit))][:a.limit]
def gitdir(repo):return ROOT/'tmp/maintenance-associations/git'/repo
def gitblob(repo,oid):
 env=os.environ.copy();env['GIT_NO_LAZY_FETCH']='1'
 return subprocess.run(['git',f'--git-dir={gitdir(repo)}','cat-file','blob',oid],check=True,capture_output=True,env=env).stdout
def intervals_py(old,new):
 return [(i1+1,i2) if i1<i2 else (i1,i1) for tag,i1,i2,j1,j2 in difflib.SequenceMatcher(None,old.splitlines(),new.splitlines(),autojunk=True).get_opcodes() if tag!='equal']
def intervals_git(repo,old,new):
 env=os.environ.copy();env['GIT_NO_LAZY_FETCH']='1'
 raw=subprocess.run(['git',f'--git-dir={gitdir(repo)}','diff','--no-ext-diff','--no-textconv','--unified=0',old,new],check=True,capture_output=True,env=env).stdout.decode('utf8','replace')
 out=[]
 for line in raw.splitlines():
  match=re.match(r'^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@',line)
  if match:
   start=int(match[1]);length=int(match[2] or 1)
   out.append((start,start+length-1) if length else (start,start))
 return out
rows=[]
for i,(repo,old_oid,new_oid) in enumerate(keys,1):
 old=gitblob(repo,old_oid);new=gitblob(repo,new_oid)
 py=intervals_py(old,new);git=intervals_git(repo,old_oid,new_oid)
 rows.append({'repository':repo,'old_blob':old_oid,'new_blob':new_oid,'python_hunks':py,'git_hunks':git,'same_hunks':py==git})
 if i%25==0:print(i,'/',len(keys),flush=True)
a.output.parent.mkdir(parents=True,exist_ok=True)
a.output.write_text(json.dumps({'sampled_events':len(rows),'same_hunks':sum(r['same_hunks'] for r in rows),'rows':rows},indent=2)+'\n')
print(len(rows),sum(r['same_hunks'] for r in rows))
