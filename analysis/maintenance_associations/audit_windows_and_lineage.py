"""Audit event membership and path continuity; preserve primary cohorts and labels."""
import argparse,collections,csv,gzip,hashlib,io,json,shutil,sqlite3,tempfile
from pathlib import Path,PurePosixPath
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1];OUT=BASE/'results/window-lineage-audit'
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=OUT);OUT=parser.parse_args().output;DAY=86400

def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def scoped(path,scope,suffix):
 return (path.endswith(suffix) and (not scope.get('include_prefixes') or any(path.startswith(p) for p in scope['include_prefixes'])) and not any(x.lower() in scope.get('exclude_directory_names',[]) for x in PurePosixPath(path).parts[:-1]) and not any(path.startswith(p) for p in scope.get('exclude_prefixes',[])))
def compressed(path):
 return io.TextIOWrapper(gzip.GzipFile(filename='',mode='wb',fileobj=path.open('wb'),mtime=0),encoding='utf-8',newline='')
def main():
 OUT.mkdir(exist_ok=True)
 if (OUT/'manifest.json').exists():raise FileExistsError('Preserve the existing audit; use a new output location')
 manifest=json.loads((BASE/'results/file-cohorts-v0.2/combined-cohort-manifest.json').read_text());summaries=[];queue={};overlaps=[]
 for source in manifest:
  rid=source['repository'];p=BASE/source['csv'];assert sha(p)==source['sha256']
  with gzip.open(p,'rt') as f:rows=list(csv.DictReader(f))
  scope=json.loads((ROOT/f'analysis/multilanguage_evolution/protocols/{rid}.json').read_text());suffix='.py' if rid=='odoo__odoo' else '.java'
  with tempfile.TemporaryDirectory(prefix='window-lineage-') as temp:
   local=Path(temp)/'events.sqlite';shutil.copyfile(ROOT/f'tmp/maintenance-associations/file-events/{rid}.sqlite',local)
   expected=json.loads((BASE/f'results/file-events/{rid}.json').read_text());assert sha(local)==expected['database_sha256']
   db=sqlite3.connect(local)
   events=list(db.execute('SELECT seq,commit_hash,timestamp FROM events ORDER BY seq'));index={h:s for s,h,t in events};ts=[0]+[t for s,h,t in events];effective=[0];clock=0
   for s,h,t in events:clock=max(clock,t);effective.append(clock)
   cache={};additions={};counts=collections.Counter();output=[];details=[]
   def changes(lineage):
    if lineage not in cache:
     grouped=collections.defaultdict(list)
     for seq,path,status,note in db.execute('SELECT seq,path,status,lineage_note FROM changes WHERE lineage=? ORDER BY seq,path',(lineage,)):grouped[seq].append((path,status,note))
     cache[lineage]=dict(grouped)
    return cache[lineage]
   for r in rows:
    baseline=index[r['baseline_commit']];t=int(r['baseline_timestamp']);lineage=int(r['lineage']);history=changes(lineage)
    before={s for s in history if s<=baseline and t-365*DAY<ts[s]<=t};before_clock={s for s in history if s<=baseline and t-365*DAY<effective[s]<=t}
    raw={s for s in history if s>baseline and t<ts[s]<=t+365*DAY};ordered={s for s in history if s>baseline and t<effective[s]<=t+365*DAY}
    assert len(before)==int(r['prior365_raw_changes']) and len(raw)==int(r['following365_raw_changes']) and len(ordered)==int(r['following365_ancestry_clock_changes'])
    flags=collections.Counter();stop=[]
    for seq in sorted(raw|ordered):
     items=history[seq];statuses={status for path,status,note in items}
     move=any(note=='unique_exact_content_move' for path,status,note in items)
     dead='D' in statuses and 'A' not in statuses
     outside=any(status!='D' and not scoped(path,scope,suffix) for path,status,note in items)
     type_change='T' in statuses
     if move:flags['exact_move_events']+=1
     if dead:flags['terminal_deletion_events']+=1
     if outside:flags['outside_path_scope_events']+=1
     if type_change:flags['type_change_events']+=1
     if dead or outside or type_change:stop.append(seq)
     if move or dead or outside or type_change:
      if seq not in additions:additions[seq]=db.execute("SELECT count(*) FROM changes WHERE seq=? AND status='A' AND path LIKE ?",(seq,'%'+suffix)).fetchone()[0]
      key=(rid,lineage,seq)
      if key not in queue:queue[key]={'repository':rid,'lineage':lineage,'event_commit':events[seq-1][1],'event_timestamp':ts[seq],'paths_and_statuses':items,'exact_content_move':move,'terminal_deletion':dead,'outside_path_scope':outside,'type_change':type_change,'same_change_language_additions':additions[seq],'possible_edited_move':dead and additions[seq]>0,'affected_snapshots':set(),'independent_classification':'','scientifically_admitted':False}
      queue[key]['affected_snapshots'].add(r['snapshot'])
    rec={'repository':rid,'snapshot':r['snapshot'],'baseline_path':r['baseline_path'],'baseline_commit':r['baseline_commit'],'lineage':lineage,'baseline_clock_shift_seconds':effective[baseline]-t,'prior_membership_difference':len(before^before_clock),'followup_membership_difference':len(raw^ordered),'followup_count_difference':len(raw)-len(ordered),'equal_counts_different_events':len(raw)==len(ordered) and raw!=ordered,**{k:flags[k] for k in ['exact_move_events','terminal_deletion_events','outside_path_scope_events','type_change_events']},'first_candidate_stop_commit':events[min(stop)-1][1] if stop else '', 'generated_header_scope_checked':False,'scientifically_admitted':False}
    output.append(rec);counts['rows']+=1
    for k,v in [('baseline_shift_rows',effective[baseline]>t),('prior_membership_difference_rows',before!=before_clock),('followup_membership_difference_rows',raw!=ordered),('followup_count_difference_rows',len(raw)!=len(ordered)),('equal_counts_different_events_rows',rec['equal_counts_different_events']),('exact_move_rows',bool(flags['exact_move_events'])),('terminal_deletion_rows',bool(flags['terminal_deletion_events'])),('outside_path_scope_rows',bool(flags['outside_path_scope_events'])),('type_change_rows',bool(flags['type_change_events']))]:counts[k]+=int(v)
    if before!=before_clock or raw!=ordered:
     details.append({'snapshot':r['snapshot'],'baseline_path':r['baseline_path'],'baseline_commit':r['baseline_commit'],'prior_raw_only':[events[s-1][1] for s in sorted(before-before_clock)],'prior_clock_only':[events[s-1][1] for s in sorted(before_clock-before)],'followup_raw_only':[events[s-1][1] for s in sorted(raw-ordered)],'followup_clock_only':[events[s-1][1] for s in sorted(ordered-raw)]})
   baselines=sorted({(r['snapshot'],int(r['baseline_timestamp'])) for r in rows})
   for i,(label,t) in enumerate(baselines):
    for later,u in baselines[i+1:]:
     intersection=max(0,min(t+365*DAY,u+365*DAY)-max(t,u))
     if intersection:overlaps.append({'repository':rid,'first_snapshot':label,'second_snapshot':later,'overlap_seconds':intersection})
   db.close()
  dest=OUT/(rid+'.csv.gz')
  with compressed(dest) as f:
   w=csv.DictWriter(f,fieldnames=list(output[0]));w.writeheader();w.writerows(output)
  with compressed(OUT/(rid+'-membership.jsonl.gz')) as f:
   for detail in details:f.write(json.dumps(detail,sort_keys=True)+'\n')
  summaries.append({'repository':rid,**counts,'source_sha256':source['sha256'],'audit_sha256':sha(dest)})
  print(rid,json.dumps(dict(counts)),flush=True)
 for record in queue.values():record['affected_snapshots']=sorted(record['affected_snapshots'])
 (OUT/'lineage-review-queue.json').write_text(json.dumps(list(queue.values()),indent=2)+'\n')
 (OUT/'overlapping-windows.json').write_text(json.dumps(overlaps,indent=2)+'\n')
 (OUT/'manifest.json').write_text(json.dumps(summaries,indent=2)+'\n')
if __name__=='__main__':main()
