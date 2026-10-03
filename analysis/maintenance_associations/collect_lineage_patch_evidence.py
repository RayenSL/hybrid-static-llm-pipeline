"""Archive bounded patch evidence for the frozen independent lineage sample."""
import argparse,collections,concurrent.futures,csv,difflib,hashlib,json,subprocess
from pathlib import Path,PurePosixPath
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=BASE/'results/lineage-patch-evidence');a=ap.parse_args();OUT=a.output;OUT.mkdir(parents=True,exist_ok=True)
if (OUT/'manifest.json').exists():raise FileExistsError('Use a fresh output directory')
SAMPLE=BASE/'results/window-lineage-audit/independent-lineage-review.csv'
with SAMPLE.open(newline='') as f:sample=list(csv.DictReader(f))

def collect(group):
 rid,rows=group;git=['git','--git-dir='+str(ROOT/f'tmp/maintenance-associations/git/{rid}')];records=[]
 for row in rows:
  commit=row['event_commit'];key=rid+'-'+row['lineage']+'-'+commit[:12];folder=OUT/key;folder.mkdir(exist_ok=True)
  paths=[p for p,status,note in json.loads(row['paths_and_statuses'])]
  record={k:row[k] for k in ['repository','stratum','lineage','event_commit','affected_snapshots']};record.update({'directory':key,'baseline_paths':paths,'independent_label':None})
  try:
   meta=subprocess.check_output([*git,'show','-s','--format=%H%n%P%n%cI%n%B',commit],timeout=90);(folder/'commit.txt').write_bytes(meta)
   raw=subprocess.check_output([*git,'diff','--raw','-z','--no-abbrev','--no-renames',commit+'^1',commit],timeout=90);(folder/'whole-change.raw').write_bytes(raw)
   fields=raw.split(b'\0');changes=[]
   for i in range(0,len(fields)-1,2):
    info=fields[i].decode().split();path=fields[i+1].decode();changes.append({'path':path,'status':info[-1],'old_blob':info[2],'new_blob':info[3]})
   basename={PurePosixPath(p).name for p in paths}
   candidates=[x for x in changes if x['status'] in ['A','M'] and x['path'] not in paths and PurePosixPath(x['path']).name in basename]
   candidates.sort(key=lambda x:(-max(difflib.SequenceMatcher(None,p,x['path']).ratio() for p in paths),x['path']))
   selected=candidates[:20];record.update({'same_basename_candidates':selected,'candidate_count_before_cap':len(candidates),'candidate_cap':20,'candidate_selection':'Same-basename A/M paths in this change; ranked by path-string similarity, then lexical order. Not a content match and not exhaustive for absorptions or renamed basenames.','whole_change_paths':len(changes)})
   (folder/'whole-change.json').write_text(json.dumps(changes,indent=2)+'\n')
   command=[*git,'diff','--no-ext-diff','--no-textconv','--no-renames','--unified=4',commit+'^1',commit,'--',*paths,*[x['path'] for x in selected]]
   result=subprocess.run(command,capture_output=True,timeout=120)
   (folder/'selected-paths.patch').write_bytes(result.stdout);(folder/'stderr.txt').write_bytes(result.stderr)
   record['patch_status']='complete' if result.returncode==0 else 'failed';record['returncode']=result.returncode
  except (subprocess.TimeoutExpired,subprocess.CalledProcessError) as e:
   record['patch_status']='unavailable';record['error']=type(e).__name__
   if getattr(e,'stdout',None):(folder/'partial-output.txt').write_bytes(e.stdout)
   if getattr(e,'stderr',None):(folder/'stderr.txt').write_bytes(e.stderr)
  record['files']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file()};records.append(record)
  print(rid,row['lineage'],record['patch_status'],flush=True)
 return records
by_repo=collections.defaultdict(list)
for row in sample:by_repo[row['repository']].append(row)
records=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
 for results in ex.map(collect,sorted(by_repo.items())):records.extend(results)
(OUT/'manifest.json').write_text(json.dumps({'sample_sha256':hashlib.sha256(SAMPLE.read_bytes()).hexdigest(),'git_version':subprocess.check_output(['git','--version'],text=True).strip(),'records':records,'independent_labels_completed':False},indent=2)+'\n')
