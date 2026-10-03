"""Validate adapter output and recompute aggregates before admitting it to analysis."""
import argparse,hashlib,json,math
from pathlib import Path,PurePosixPath
import jsonschema
SCHEMA=Path(__file__).resolve().parents[1]/'contracts/findings.schema.json'
def canonical(d):return json.dumps(d,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()+b'\n'
def validate(d):
 jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text())).validate(d)
 def check(ok,message):
  if not ok:raise ValueError(message)
 inv={x['path']:x for x in d['inventory']};check(len(inv)==len(d['inventory']),'duplicate source file')
 for path in [*inv,*(x['path'] for x in d['excluded'])]:
  p=PurePosixPath(path);check(not p.is_absolute() and '..' not in p.parts and '\\' not in path and ':' not in path,'non-relative source path')
 definitions={x['id']:x for x in d['definitions']};check(len(definitions)==len(d['definitions']),'duplicate definition')
 for x in definitions.values():
  check(x['path'] in inv,'definition source absent');check(x['source_sha256']==inv[x['path']]['sha256'],'source digest mismatch');span=x['span']
  check(0<=span['byte_start']<span['byte_end']<=inv[x['path']]['bytes'],'invalid byte span')
  check(1<=span['line_start']<=span['line_end'],'invalid line span')
  check(x['id']==hashlib.sha256(canonical([x['path'],span['byte_start'],span['byte_end'],d['language']])).hexdigest(),'definition identity mismatch')
 expected={x['id'] for x in definitions.values() if x['metrics']['cyclomatic_complexity']>10};actual={x['id'] for x in d['findings']}
 check(expected==actual and len(actual)==len(d['findings']),'finding set inconsistent with rule')
 for f in d['findings']:
  check(all(f[k]==v for k,v in definitions[f['id']].items()),'finding evidence differs from definition');check(f['rule_id']==d['rule_id'] and f['language']==d['language'],'rule/language mismatch')
 s=d['summary'];check(s['eligible_files']==len(inv),'file denominator mismatch');check(s['definition_count']==len(definitions),'definition denominator mismatch');check(s['finding_count']==len(expected),'finding count mismatch')
 check(s['parsed_files']==sum(x['parse_status']=='complete' for x in inv.values()),'parse count mismatch')
 check(s['physical_lines']==sum(x['physical_lines'] for x in inv.values()),'line count mismatch')
 complete=bool(inv) and not d['diagnostics'] and s['parsed_files']==len(inv)
 check((d['status']['syntax']=='complete')==complete,'incorrect completeness status')
 rate=len(expected)/len(definitions) if complete and definitions else None
 check(s['prevalence']==rate,'invalid prevalence or missing-value handling')
 for t in [10,15,20]:check(s['sensitivity_counts'][str(t)]==sum(x['metrics']['cyclomatic_complexity']>t for x in definitions.values()),'sensitivity mismatch')
 check(d['scope_sha256']==hashlib.sha256(canonical(d['scope'])).hexdigest(),'scope hash mismatch')
 return {'repository':d['repository'],'commit':d['commit'],'language':d['language'],'status':d['status']['syntax'],'eligible_files':len(inv),'parsed_files':s['parsed_files'],'admitted':False}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('files',nargs='+',type=Path);a=ap.parse_args()
 for p in a.files:print(json.dumps(validate(json.loads(p.read_text()))))
