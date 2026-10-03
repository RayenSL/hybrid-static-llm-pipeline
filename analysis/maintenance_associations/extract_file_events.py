"""Extract first-parent file events and conservative path lineages, without labels."""
import argparse,gzip,hashlib,json,sqlite3,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'analysis/maintenance_associations'

def extract(rid):
 cache=ROOT/'tmp/maintenance-associations';repo=cache/'git'/rid
 out=cache/'file-events';out.mkdir(exist_ok=True)
 manifest=json.loads((ROOT/f'analysis/multilanguage_evolution/selection/histories/{rid}.json').read_text())
 endpoint=manifest['endpoint']['commit'];raw=out/(rid+'.raw');dbpath=out/(rid+'.sqlite')
 if dbpath.exists():raise FileExistsError(str(dbpath)+'; use a new output location or inspect existing result')
 cmd=['git','--git-dir',str(repo),'log','--reverse','--root','--first-parent','--diff-merges=first-parent','--raw','--no-renames','--no-abbrev','-z','--format=%x1e%H%x00%ct%x00',endpoint]
 with raw.open('wb') as f:subprocess.run(cmd,stdout=f,check=True)
 db=sqlite3.connect(dbpath)
 db.executescript('CREATE TABLE events (seq INTEGER PRIMARY KEY, commit_hash TEXT UNIQUE, timestamp INTEGER, time_reversal INTEGER); CREATE TABLE changes (seq INTEGER, path TEXT, status TEXT, old_blob TEXT, new_blob TEXT, lineage INTEGER, lineage_note TEXT); CREATE TABLE states (path TEXT PRIMARY KEY, lineage INTEGER);')
 live={};next_id=0;last=None;count=0;renames=0;ambiguous=0;h=hashlib.sha256()
 def chunks():
  pending=b''
  with raw.open('rb') as f:
   while True:
    b=f.read(1024*1024)
    if not b:break
    h.update(b);parts=(pending+b).split(b'\x1e');pending=parts.pop()
    for part in parts:
     if part:yield part
   if pending:yield pending
 for chunk in chunks():
  fields=chunk.split(b'\0');commit=fields[0].decode();ts=int(fields[1]);items=[];i=2
  while i<len(fields):
   meta=fields[i].strip(b'\n');i+=1
   if not meta:continue
   if not meta.startswith(b':') or i>=len(fields):raise ValueError('Malformed raw diff')
   mode_old,mode_new,old,new,status=meta[1:].decode().split();path=fields[i].decode('utf-8');i+=1
   if status not in ['A','M','D','T']:raise ValueError('Unexpected status '+status)
   items.append((path,status,old,new))
  # Only exact-content, unique deletion/addition pairs establish a move.
  deleted={};added={}
  for path,status,old,new in items:
   if status=='D':deleted.setdefault(old,[]).append(path)
   if status=='A':added.setdefault(new,[]).append(path)
  moves={}
  for oid,paths in deleted.items():
   if oid in added:
    if len(paths)==len(added[oid])==1 and paths[0] in live:moves[added[oid][0]]=live[paths[0]];renames+=1
    else:ambiguous+=1
  count+=1;db.execute('INSERT INTO events VALUES (?,?,?,?)',(count,commit,ts,int(last is not None and ts<last)));last=ts
  for path,status,old,new in items:
   note='same_path'
   if status=='A':
    if path in moves:lineage=moves[path];note='unique_exact_content_move'
    else:next_id+=1;lineage=next_id;note='addition_or_unresolved_move'
    live[path]=lineage
   else:
    if path not in live:raise ValueError('Missing predecessor for '+path)
    lineage=live[path]
   db.execute('INSERT INTO changes VALUES (?,?,?,?,?,?,?)',(count,path,status,old,new,lineage,note))
  for path,status,old,new in items:
   if status=='D':live.pop(path,None)
  if count%5000==0:db.commit();print(rid,count,'events',flush=True)
 expected=int(subprocess.check_output(['git','--git-dir',str(repo),'rev-list','--first-parent','--count',endpoint]))
 if count!=expected:raise ValueError(f'{count} != {expected}')
 db.executemany('INSERT INTO states VALUES (?,?)',live.items())
 db.executescript('CREATE INDEX changes_lineage ON changes(lineage,seq); CREATE INDEX changes_seq ON changes(seq); CREATE INDEX changes_path ON changes(path,seq); CREATE INDEX events_time ON events(timestamp);')
 db.commit();summary={'repository':rid,'endpoint':endpoint,'events':count,'file_changes':db.execute('SELECT count(*) FROM changes').fetchone()[0],'timestamp_reversals':db.execute('SELECT sum(time_reversal) FROM events').fetchone()[0],'unique_exact_content_moves':renames,'ambiguous_content_move_groups':ambiguous,'raw_sha256':h.hexdigest(),'database':str(dbpath.relative_to(ROOT)),'lineage_limit':'Edited renames are unresolved; deletions remain censoring candidates. Exact-content moves are heuristic identities, not proof of refactoring.','corrective_labels_available':False,'associations_estimated':False,'command':cmd}
 db.close()
 summary['database_sha256']=hashlib.sha256(dbpath.read_bytes()).hexdigest()
 d=BASE/'results/file-events';d.mkdir(exist_ok=True)
 (d/(rid+'.json')).write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('repository',choices=['odoo__odoo','jenkinsci__jenkins','apache__tomcat']);a=p.parse_args();extract(a.repository)
