"""Run the reviewed syntax campaign; preserve feasibility-only scientific status."""
import argparse, hashlib, json, shutil, socket, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
CASES={'odoo__odoo':'python','jenkinsci__jenkins':'java','apache__tomcat':'java'}
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--packages',type=Path,required=True);ap.add_argument('--sources',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--pass-name',choices=['A','B','offline'],required=True);a=ap.parse_args()
    sys.path.insert(0,str(a.packages.resolve()));sys.path.insert(0,str(HERE/'detectors'));sys.path.insert(0,str(HERE/'ingest'))
    from syntax_probe import run,canonical
    from validate import validate
    def blocked(*args,**kwargs):raise RuntimeError('Network disabled for measurement replay')
    socket.socket=blocked;socket.create_connection=blocked
    out=a.output/a.pass_name;out.mkdir(parents=True,exist_ok=True);records=[]
    for repo,language in CASES.items():
        history=json.loads((HERE/'selection/histories'/f'{repo}.json').read_text())
        base=json.loads((HERE/'protocols'/f'{repo}.json').read_text())
        for obs in history['observations']:
            name=f"{repo}-{obs['label']}";source=a.sources/(name+'.tar')
            seal=json.loads(source.with_suffix('.manifest.json').read_text())
            archive_sha=sha(source)
            # Accept the exporter's exact declared seal field, never infer a commit from a filename.
            if seal.get('commit')!=obs['commit'] or archive_sha != seal.get('sha256'):raise ValueError('Archive seal mismatch: '+name)
            scope=dict(base)
            if language=='python':
                year=int(obs['label'][-4:]);scope['python_parser']='legacy' if year<2017 else 'legacy3' if year==2017 else 'tree-sitter'
            dest=out/(name+'-'+language+'.json')
            if dest.exists():raise FileExistsError('Refusing to overwrite '+str(dest))
            # Distinct archive paths exercise independence from machine-local input paths.
            local=out/(name+'.tar');shutil.copyfile(source,local)
            if sha(local)!=archive_sha:raise ValueError('Copy mismatch')
            try:result=run(local,language,history['repository'],obs['commit'],scope)
            finally:local.unlink()
            validate(result);dest.write_bytes(canonical(result))
            records.append({'file':dest.name,'sha256':sha(dest),'archive_sha256':archive_sha,'commit':obs['commit'],'scope_sha256':result['scope_sha256'],'syntax':result['status']['syntax']})
            print(a.pass_name,name,result['status']['syntax'],flush=True)
    (out/'manifest.json').write_bytes(canonical({'pass':a.pass_name,'network':'Python socket creation blocked; no target source execution','records':records}))
if __name__=='__main__':main()
