"""Run early/current source probes and validate envelopes; no scientific admission."""
import argparse,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--packages',type=Path);ap.add_argument('--repository');ap.add_argument('--all-years',action='store_true');ap.add_argument('--legacy-python-through',type=int);ap.add_argument('--python3-from',type=int);ap.add_argument('--sources',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 if a.packages:sys.path.insert(0,str(a.packages.resolve()))
 sys.path.insert(0,str(HERE/'detectors'));sys.path.insert(0,str(HERE/'ingest'))
 from syntax_probe import run,canonical
 from validate import validate
 scope=json.loads((HERE/'selection/probe-scope.json').read_text());a.output.mkdir(parents=True,exist_ok=True);summaries=[]
 for hist in sorted((HERE/'selection/histories').glob('*.json')):
  
  if a.repository and hist.stem!=a.repository:continue
  scope=json.loads((HERE/'selection'/('odoo-probe-scope.json' if hist.stem=='odoo__odoo' else 'probe-scope.json')).read_text())
  d=json.loads(hist.read_text());langs=['python'] if hist.stem=='odoo__odoo' else ['java'] if hist.stem in ['apache__ofbiz-framework','jenkinsci__jenkins','apache__tomcat','elastic__elasticsearch'] else ['c','cpp']
  for sample in (d['observations'] if a.all_years else [d['observations'][0],d['observations'][-1]]):
   archive=a.sources/(hist.stem+'-'+sample['label']+'.tar')
   if not archive.exists():raise FileNotFoundError(archive)
   for lang in langs:
    dest=a.output/(hist.stem+'-'+sample['label']+'-'+lang+'.json')
    sample_scope=dict(scope)
    if lang=='python' and a.legacy_python_through is not None:sample_scope['python_parser']='legacy' if int(sample['label'][-4:])<=a.legacy_python_through else 'tree-sitter'
    if lang=='python' and sample_scope.get('python_parser')=='legacy' and a.python3_from is not None and int(sample['label'][-4:])>=a.python3_from:sample_scope['python_parser']='legacy3'
    result=run(archive,lang,d['repository'],sample['commit'],sample_scope);row=validate(result);dest.write_bytes(canonical(result));row.update({'label':sample['label'],'result_file':dest.name,'parse_errors':len(result['diagnostics']),'diagnostic_examples':result['diagnostics'][:5],'unvalidated_rule':True});summaries.append(row)
    print(hist.stem,sample['label'],lang,row['status'],row['parsed_files'],row['eligible_files'],flush=True)
 (a.output/((a.repository+'-' if a.repository else '')+'coverage-summary.json')).write_bytes(canonical(summaries))
