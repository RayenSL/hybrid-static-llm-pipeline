"""Check returned worksheets without estimating outcomes or admitting evidence."""
import argparse,csv,json
from pathlib import Path
BASE=Path(__file__).resolve().parent
CONFIG={
 'detector-review.csv':{'key':['case_id'],'label':'independent_rule_satisfied','allowed':{'yes','no','uncertain'},'editable':['independent_rule_satisfied','evidence','rationale','reviewer'],'required':['evidence','rationale','reviewer']},
 'corrective-review.csv':{'key':['repository','commit'],'label':'reviewer_label','allowed':{'confirmed_corrective','confirmed_non_corrective','uncertain','inaccessible'},'editable':['reviewer_label','evidence_url','rationale','reviewer'],'required':['evidence_url','rationale','reviewer']},
 'lineage-review.csv':{'key':['repository','lineage','event_commit'],'label':'classification','allowed':{'continuation','removal','repository_extraction','scope_exit','absorption','uncertain','inaccessible'},'editable':['reviewer','classification','linked_destination','evidence','rationale'],'required':['evidence','rationale','reviewer']}}
def read(p):
 with p.open(newline='',encoding='utf-8-sig') as f:
  reader=csv.DictReader(f);return reader.fieldnames,list(reader)
def check(packet,submission):
 reports=[];errors=[]
 for filename,cfg in CONFIG.items():
  fields,original=read(packet/filename)
  if not (submission/filename).exists():errors.append(filename+': missing worksheet');continue
  supplied_fields,rows=read(submission/filename)
  if supplied_fields!=fields:errors.append(filename+': changed column names or order');continue
  key=lambda r:tuple(r.get(k,'') for k in cfg['key']);expected={key(r):r for r in original};actual={key(r):r for r in rows}
  if len(actual)!=len(rows) or set(actual)!=set(expected):errors.append(filename+': missing, duplicate or changed case identifiers');continue
  completed=definitive=0;counts={}
  for k,r in actual.items():
   if any(r.get(f)!=expected[k].get(f) for f in fields if f not in cfg['editable']):errors.append(filename+': changed frozen evidence fields for '+str(k))
   label=r[cfg['label']].strip()
   if not label:
    if any(r[f].strip() for f in cfg['editable']):errors.append(filename+': partially completed unlabelled row '+str(k))
    continue
   if label not in cfg['allowed']:errors.append(filename+': invalid label '+label);continue
   required=list(cfg['required'])
   if filename=='lineage-review.csv' and label in {'continuation','absorption','repository_extraction','scope_exit'}:required.append('linked_destination')
   missing=[f for f in required if not r[f].strip()]
   if missing:errors.append(filename+': missing '+','.join(missing)+' for '+str(k));continue
   completed+=1;definitive+=label not in {'uncertain','inaccessible'};counts[label]=counts.get(label,0)+1
  reports.append({'worksheet':filename,'cases':len(rows),'completed_rows':completed,'definitive_rows':definitive,'pending_rows':len(rows)-completed,'label_counts':counts})
 return {'worksheets':reports,'errors':errors,'submission_complete':not errors and len(reports)==3 and all(r['pending_rows']==0 for r in reports),'reviewer_independence_verified':False,'scientifically_admitted':False,'associations_estimated':False}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--packet',type=Path,default=BASE/'results/validation-handoff-v0.5');ap.add_argument('--submission',type=Path,required=True);ap.add_argument('--output',type=Path);a=ap.parse_args();report=check(a.packet,a.submission)
 if a.output:
  if a.output.exists():raise FileExistsError('Preserve the previous review check')
  a.output.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2));raise SystemExit(1 if report['errors'] else 0)
