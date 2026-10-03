"""Publish checksum-linked coverage only; never publish probe prevalence as findings."""
import argparse,csv,gzip,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
REPOS={'odoo__odoo':('Odoo','Business applications'),'jenkinsci__jenkins':('Jenkins','Development automation'),'apache__tomcat':('Apache Tomcat','Application-server infrastructure')}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--results',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=True);evidence=[];totals=[]
 for repo,(name,domain) in REPOS.items():
  manifest=HERE/'selection/histories'/(repo+'.json');h=json.loads(manifest.read_text());archive=manifest.with_name(h['history_archive']['file']);assert sha(archive)==h['history_archive']['sha256'];json.loads(gzip.decompress(archive.read_bytes()))
  rows=[]
  for s in h['observations']:
   lang='python' if repo=='odoo__odoo' else 'java';p=a.results/(repo+'-'+s['label']+'-'+lang+'.json');d=json.loads(p.read_text());assert d['commit']==s['commit'] and d['admitted'] is False
   row={'repository':name,'domain':domain,'label':s['label'],'commit':s['commit'],'language':lang,'syntax_status':d['status']['syntax'],'eligible_files':d['summary']['eligible_files'],'parsed_files':d['summary']['parsed_files'],'admitted':False,'result_sha256':sha(p),'result_file':p.as_posix(),'scope_sha256':d['scope_sha256'],'adapter_sha256':d['tool']['adapter_sha256'],'parser':d['scope'].get('python_parser','tree-sitter')};rows.append(row)
   evidence.append({**row,'diagnostic_examples':d['diagnostics'][:8]})
  gaps=[r['label'] for r in rows if r['syntax_status']!='complete'];totals.append({'repository':name,'domain':domain,'preserved_years':round(h['elapsed_years'],1),'observations':len(rows),'complete_syntax':len(rows)-len(gaps),'gaps':gaps,'numerical_feasibility_gate':h['elapsed_years']>=15 and len(gaps)<=2,'scientific_admission':False})
 with (a.output/'annual-coverage.csv').open('w',newline='') as f:
  keys=[k for k in evidence[0] if k!='diagnostic_examples'];w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows({k:r[k] for k in keys} for r in evidence)
 (a.output/'annual-coverage-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
 (a.output/'feasibility-summary.json').write_text(json.dumps({'status':'feasibility_only','cases':totals,'remaining_gates':['repository-specific scope review','empirical rule validation','current build and runtime smoke checks','independent A/B and offline replay']},indent=2)+'\n')
 lines=['# Annual syntax coverage','', 'These are feasibility results under provisional source filters. They are not admitted anti-pattern prevalence measurements.','', '| Case | Domain | Preserved years | Complete annual parses | Missing observations |','|---|---|---:|---:|---|']
 for r in totals:lines.append(f"| {r['repository']} | {r['domain']} | {r['preserved_years']} | {r['complete_syntax']}/{r['observations']} | {', '.join(r['gaps']) or 'None'} |")
 lines+=['','All cases meet the numerical 15-year/maximum-two-gap feasibility gate only if `numerical_feasibility_gate` is true in the companion JSON. Scope validation, rule validation, current build/smoke checks and independent replay remain required before scientific admission.','', 'The CSV and evidence JSON link every observation to its immutable commit, full result digest, source-scope digest and adapter digest. No anti-pattern count is used to rank candidates.']
 (a.output/'ANNUAL_COVERAGE.md').write_text('\n'.join(lines)+'\n');print(json.dumps(totals,indent=2))
