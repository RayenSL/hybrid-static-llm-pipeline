"""Verify path-scope exits against immutable first-parent Git diffs."""
import argparse,json,subprocess
from pathlib import Path
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1];OUT=BASE/'results/window-lineage-audit'
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=OUT);OUT=parser.parse_args().output
queue=json.loads((OUT/'lineage-review-queue.json').read_text());verified=[]
for row in queue:
 if not row['outside_path_scope']:continue
 rid=row['repository'];commit=row['event_commit'];scope=json.loads((ROOT/f'analysis/multilanguage_evolution/protocols/{rid}.json').read_text())
 paths=[p for p,status,note in row['paths_and_statuses']]
 command=['git','--git-dir='+str(ROOT/f'tmp/maintenance-associations/git/{rid}'),'diff','--raw','--no-abbrev','--no-renames',commit+'^1',commit,'--',*paths]
 text=subprocess.check_output(command,text=True);changes=[]
 for line in text.splitlines():
  meta,path=line.split('\t',1);mode_old,mode_new,old,new,status=meta[1:].split();changes.append({'path':path,'status':status,'old_blob':old,'new_blob':new})
 deleted=[r['old_blob'] for r in changes if r['status']=='D'];added=[r['new_blob'] for r in changes if r['status']=='A']
 assert row['exact_content_move'] and len(deleted)==len(added)==1 and deleted==added
 destinations=[{'path':r['path'],'matching_excluded_prefixes':[p for p in scope['exclude_prefixes'] if r['path'].startswith(p)]} for r in changes if r['status']=='A']
 assert all(d['matching_excluded_prefixes'] for d in destinations)
 verified.append({'repository':rid,'lineage':row['lineage'],'event_commit':commit,'affected_snapshots':row['affected_snapshots'],'git_raw_diff':text,'identical_source_blob':added[0],'excluded_destinations':destinations,'status':'verified_exact_content_path_scope_exit','independent_semantic_or_corrective_classification':None})
(OUT/'verified-scope-exits.json').write_text(json.dumps(verified,indent=2)+'\n')
print(len(verified),'path transitions verified against Git')
