"""Assess legacy parsing and complexity separately; do not merge with modern probes."""
import argparse,hashlib,json,sys,tarfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--sources',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();sys.path.insert(0,str(HERE/'detectors'))
 from legacy_python import analyse,canonical
 from lib2to3 import pygram
 grammar=Path(pygram._GRAMMAR_FILE)
 scope=json.loads((HERE/'selection/odoo-probe-scope.json').read_text());hist=json.loads((HERE/'selection/histories/odoo__odoo.json').read_text());a.output.mkdir(parents=True,exist_ok=True);rows=[]
 for sample in hist['observations']:
  year=int(sample['label'][-4:])
  if year>=2018:continue
  archive=a.sources/('odoo__odoo-'+sample['label']+'.tar');diagnostics=[];definitions=[];files=[];excluded=[]
  with tarfile.open(archive) as tar:
   for m in sorted(tar.getmembers(),key=lambda x:x.name):
    if not m.isfile() or not m.name.endswith('.py'):continue
    path=m.name
    if any(part.lower() in scope['exclude_directory_names'] for part in Path(path).parts[:-1]) or any(path.startswith(p) for p in scope['exclude_prefixes']):excluded.append(path);continue
    data=tar.extractfile(m).read()
    if any(x.encode().lower() in data[:2048].lower() for x in scope['generated_markers']):excluded.append(path);continue
    ds,errs=analyse(data,path);definitions.extend(ds);diagnostics.extend({'path':path,**x} for x in errs);files.append({'path':path,'sha256':hashlib.sha256(data).hexdigest(),'complete':not errs})
  result={'purpose':'legacy_parser_feasibility','admitted':False,'commit':sample['commit'],'label':sample['label'],'tool':{'python':sys.version,'grammar_sha256':hashlib.sha256(grammar.read_bytes()).hexdigest(),'adapter_sha256':hashlib.sha256((HERE/'detectors/legacy_python.py').read_bytes()).hexdigest()},'scope':scope,'files':files,'excluded':excluded,'definitions':definitions,'diagnostics':diagnostics};dest=a.output/(sample['label']+'.json');dest.write_bytes(canonical(result));row={'label':sample['label'],'commit':sample['commit'],'files':len(files),'parsed_files':sum(x['complete'] for x in files),'status':'complete' if not diagnostics else 'partial','diagnostics':diagnostics,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()};rows.append(row);print(sample['label'],row['status'],row['parsed_files'],row['files'],flush=True)
 (a.output/'coverage-summary.json').write_bytes(canonical(rows))
