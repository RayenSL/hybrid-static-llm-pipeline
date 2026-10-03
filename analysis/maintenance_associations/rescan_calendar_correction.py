"""Rescan frozen calendar-frontier replacements without modifying original evidence."""
import argparse, hashlib, json, subprocess, sys, tarfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
EV=HERE.parent/'multilanguage_evolution'
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--packages',type=Path,required=True)
    ap.add_argument('--cache',type=Path,required=True)
    ap.add_argument('--sources',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args()
    sys.path[:0]=[str(a.packages.resolve()),str(EV/'detectors'),str(EV/'ingest')]
    from multi_rule import run, canonical
    from validate_multi_rule import validate
    frozen=json.loads((HERE/'protocols/calendar-frontier-v0.2.json').read_text())
    for name,digest in frozen['detector_inputs'].items():
        if sha(EV/name)!=digest: raise ValueError('Detector input changed: '+name)
    for p in (a.sources,a.output): p.mkdir(parents=True,exist_ok=True)
    records=[]
    with tarfile.open(EV/'results/three-rule-evidence.tar.gz','r:gz') as old:
        for obs in frozen['replacements']:
            name='odoo__odoo-'+obs['snapshot']; archive=a.sources/(name+'.tar')
            seal=archive.with_suffix('.manifest.json')
            if not seal.exists():
                with archive.with_suffix('.partial').open('wb') as f,archive.with_suffix('.log').open('w') as log:
                    subprocess.run(['git','--git-dir='+str(a.cache.resolve()),'archive','--format=tar',obs['proposed_commit'],'*.py'],stdout=f,stderr=log,check=True)
                archive.with_suffix('.partial').replace(archive)
                seal.write_bytes(canonical({'repository':'odoo__odoo','label':obs['snapshot'],'commit':obs['proposed_commit'],'sha256':sha(archive),'patterns':['*.py'],'archive':archive.name}))
            export=json.loads(seal.read_text())
            if export['commit']!=obs['proposed_commit'] or export['sha256']!=sha(archive): raise ValueError('Archive seal mismatch')
            print(name,'archive verified',flush=True)
            scope=json.loads((EV/'protocols/odoo__odoo.json').read_text());scope['python_parser']='tree-sitter'
            scopefile=a.output/(name+'.scope.json'); syntaxfile=a.output/(name+'.syntax.json');dest=a.output/(name+'.three-rules.json')
            scopefile.write_bytes(canonical(scope))
            command=[sys.executable,str(EV/'detectors/syntax_worker.py'),'--packages',str(a.packages.resolve()),'--archive',str(archive.resolve()),'--scope',str(scopefile.resolve()),'--language','python','--repository',frozen['repository'],'--commit',obs['proposed_commit'],'--output',str(syntaxfile.resolve())]
            subprocess.run(command,check=True,timeout=1200)
            syntax=json.loads(syntaxfile.read_text()); result=run(archive,syntax); summary=validate(result)
            subprocess.run(command,check=True,timeout=1200)
            repeated=json.loads(syntaxfile.read_text())
            if canonical(syntax)!=canonical(repeated) or canonical(result)!=canonical(run(archive,repeated)): raise ValueError('Replay mismatch')
            if dest.exists() and dest.read_bytes()!=canonical(result): raise ValueError('Existing result mismatch')
            dest.write_bytes(canonical(result))
            member=next(m for m in old.getmembers() if m.name.endswith('/'+name+'.three-rules.json') or m.name==name+'.three-rules.json')
            original=json.load(old.extractfile(member))
            record={**obs,'sha256':sha(dest),'syntax_replay_identical':True,'semantic_replay_identical':True,'rules':summary,'original_rules':validate(original)}
            records.append(record); (a.output/'manifest.json').write_bytes(canonical(records))
            print(name,json.dumps(record),flush=True)
if __name__=='__main__': main()
