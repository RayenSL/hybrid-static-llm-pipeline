"""Produce machine-only linkage suggestions; never fill independent labels."""
import argparse,collections,hashlib,json,subprocess
from pathlib import Path
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1];OUT=BASE/'results/lineage-patch-evidence'
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=OUT);OUT=ap.parse_args().output
manifest=json.loads((OUT/'manifest.json').read_text());suggestions=[]
for r in manifest['records']:
 folder=OUT/r['directory']
 for name,digest in r['files'].items():assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest
 result={'repository':r['repository'],'lineage':r['lineage'],'event_commit':r['event_commit'],'evidence_directory':r['directory'],'status':'unresolved','independent_classification':None,'corrective_classification':None}
 if r['patch_status']!='complete':result['reason']='Patch unavailable';suggestions.append(result);continue
 changes=json.loads((folder/'whole-change.json').read_text());by_path={x['path']:x for x in changes}
 old=[by_path[p] for p in r['baseline_paths'] if p in by_path and by_path[p]['status']=='D'];added=[by_path[p] for p in r['baseline_paths'] if p in by_path and by_path[p]['status']=='A']
 if len(old)==len(added)==1 and old[0]['old_blob']==added[0]['new_blob']:
  result.update({'status':'exact_content_link_observed','source':old[0]['path'],'destination':added[0]['path'],'blob':old[0]['old_blob'],'reason':'Same source blob across the recorded deletion/addition. Semantic and corrective meaning remain unvalidated.'})
 else:
  paths=r['baseline_paths']+[x['path'] for x in r.get('same_basename_candidates',[])]
  if r['repository']=='odoo__odoo' and r['lineage']=='52284':paths.append('addons/hr/models/discuss_channel.py');result['supplementary_search']='Manual inspection of same-directory channel paths; filename changed.'
  command=['git','--git-dir='+str(ROOT/f"tmp/maintenance-associations/git/{r['repository']}"),'diff','--no-ext-diff','--no-textconv','--name-status','-z','--find-renames=50%',r['event_commit']+'^1',r['event_commit'],'--',*paths]
  if 'supplementary_search' in result:
   supplement_command=command[:2]+['diff','--no-ext-diff','--no-textconv','--find-renames=50%','--unified=4',r['event_commit']+'^1',r['event_commit'],'--',*paths]
   (folder/'supplementary-channel-rename.patch').write_bytes(subprocess.check_output(supplement_command,timeout=120))
  output=subprocess.check_output(command,timeout=120);(folder/'bounded-rename-candidates.raw').write_bytes(output)
  fields=output.decode().split('\0');pairs=[];i=0
  while i<len(fields) and fields[i]:
   status=fields[i];i+=1
   if status.startswith(('R','C')):src,dst=fields[i:i+2];i+=2;pairs.append({'status':status,'source':src,'destination':dst})
   else:i+=1
  pairs=[p for p in pairs if p['source'] in r['baseline_paths']]
  result['rename_candidates']=pairs
  result['status']='edited_move_candidate' if pairs else 'identity_unresolved'
  result['reason']='Git similarity on the archived bounded path shortlist, threshold 50%; candidates require independent validation. No candidate does not prove removal.'
 suggestions.append(result)
 print(r['repository'],r['lineage'],result['status'],flush=True)
(OUT/'machine-linkage-suggestions.json').write_text(json.dumps({'git_version':manifest['git_version'],'rename_threshold_percent':50,'shortlist_is_exhaustive':False,'admitted':False,'suggestions':suggestions},indent=2)+'\n')
counts=collections.Counter(r['status'] for r in suggestions)
lines=['# Patch evidence and follow-up specification','','All records refer to the frozen 50-case stratified continuity sample. The source worksheets remain unchanged; this report contains machine linkage suggestions, not independent reviewer decisions.','','| Screening result | Cases |','|---|---:|']
for status,count in sorted(counts.items()):lines.append(f'| {status} | {count} |')
lines+=['','## What the patches establish','','Several apparent deletions are continuations under new paths. Tomcat examples include the javax-to-jakarta namespace migration. The sampled Odoo `addons/hr/models/mail_channel.py` continues as `discuss_channel.py`: the supplementary patch changes the inherited model name and Git reports 97% similarity. Its basename changed, so a same-basename shortlist alone missed it. These examples establish the need to validate edited moves; they do not establish the error rate of the full lineage extractor.','', 'The sampled Jenkins remoting removal is accompanied by a commit narrative stating that the module moved to another repository. Its local patch confirms removal from the selected repository; the external destination has not been independently verified. Repository extraction must not be described as disappearance of the software.','', 'Exact-content pairs are mechanically evidenced. Similarity candidates are provisional, and the bounded shortlist can miss renamed basenames, splits or absorption into existing files. Some no-candidate cases may be true removals, but that conclusion cannot be obtained from the absence of a suggested match. The chosen sample is stratified over flagged continuity cases and does not estimate population-wide rates.','','## Observation rules','','The dated `protocols/followup-observation-v0.4.md` specifies continued in-scope identity, verified competing exits, unresolved identity boundaries and administrative end of observation. Retain every eligible baseline; do not drop files because they later disappear. Unknown identity or corrective status remains unknown. Actual-date windows remain primary, with alternative event membership retained for sensitivity. No model may silently assume non-informative censoring at unresolved deletions.','','## Evidence and next dependency','','Each case directory contains immutable commit metadata, whole-change path/blob metadata, a selected-path patch and checksum provenance. Where applicable, Git similarity output supplies candidate source/destination paths. The patch acquisition manifest records the selection cap and any failures. Independent reviewers should assess continuation/removal/absorption/extraction using this evidence and extend the bounded search where needed. Confirmed corrective involvement requires its own evidence and cannot be inferred from a move or deletion.','','No lineage identifiers, maintenance outcomes, censoring times or estimates have been changed. Independent review remains the next admission dependency.']
(OUT/'REPORT.md').write_text('\n'.join(lines)+'\n')
(OUT/'inference-gate.json').write_text(json.dumps({'status':'independent_validation_pending','patch_evidence_collected':True,'followup_specification':'0.4','independent_labels_completed':False,'lineage_identifiers_modified':False,'associations_estimated':False},indent=2)+'\n')
print(dict(counts))
