"""Verify corrected source exports against Git blob identities and date frontiers."""
import argparse,bisect,datetime as dt,hashlib,json,sqlite3,subprocess,tarfile
from pathlib import Path
BASE=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--cache',type=Path,required=True);ap.add_argument('--sources',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
frozen=json.loads((BASE/'protocols/calendar-frontier-v0.2.json').read_text())
history=json.loads((BASE.parent/'multilanguage_evolution/selection/histories/odoo__odoo.json').read_text())
git=['git','--git-dir='+str(a.cache.resolve())]
events=[line.split() for line in subprocess.check_output([*git,'log','--first-parent','--reverse','--format=%H %ct',history['endpoint']['commit']],text=True).splitlines()]
prefix=[];maximum=-1
for h,t in events: maximum=max(maximum,int(t));prefix.append(maximum)
records=[]
for r in frozen['replacements']:
 boundary=int(dt.datetime(int(r['snapshot'])+1,1,1,tzinfo=dt.timezone.utc).timestamp());i=bisect.bisect_left(prefix,boundary)-1
 assert events[i][0]==r['proposed_commit']
 tree={}
 for entry in subprocess.check_output([*git,'ls-tree','-r','-z',r['proposed_commit']]).split(b'\0'):
  if not entry: continue
  meta,path=entry.split(b'\t',1);mode,kind,oid=meta.split()
  if kind==b'blob':tree[path.decode()]=oid.decode()
 archive=a.sources/('odoo__odoo-'+r['snapshot']+'.tar');seal=json.loads(archive.with_suffix('.manifest.json').read_text());digest=hashlib.sha256(archive.read_bytes()).hexdigest()
 assert seal['commit']==r['proposed_commit'] and seal['sha256']==digest
 count=0
 with tarfile.open(archive) as t:
  for member in t:
   if not member.isfile():continue
   data=t.extractfile(member).read();blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
   assert tree[member.name]==blob,member.name
   count+=1
 records.append({'year':r['snapshot'],'commit':r['proposed_commit'],'source_sha256':digest,'regular_files_matched_to_git':count,'latest_calendar_frontier_verified':True,'maximum_first_parent_timestamp':prefix[i],'boundary_timestamp':boundary})
 print(r['snapshot'],count,'source files match Git; date frontier verified',flush=True)
a.output.write_text(json.dumps({'frozen_endpoint':history['endpoint']['commit'],'first_parent_events':len(events),'observations':records},indent=2)+'\n')
