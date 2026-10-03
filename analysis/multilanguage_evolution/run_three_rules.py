"""Run all three modular rules on the frozen annual observations."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'detectors'));sys.path.insert(0,str(HERE/'ingest'))
from multi_rule import run,canonical
from validate_multi_rule import validate
CASES={'odoo__odoo':'python','jenkinsci__jenkins':'java','apache__tomcat':'java'}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--parser-python',required=True);ap.add_argument('--parser-packages',type=Path,required=True);ap.add_argument('--sources',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--java',type=Path,required=True);ap.add_argument('--java-classes',type=Path,required=True);ap.add_argument('--repository',choices=CASES);ap.add_argument('--all-years',action='store_true');ap.add_argument('--labels',nargs='+');ap.add_argument('--replay',action='store_true');a=ap.parse_args()
    sys.path.insert(0,str(a.parser_packages.resolve()))
    profiles=json.loads((HERE/'protocols/java-release-profiles.json').read_text())
    a.output.mkdir(parents=True,exist_ok=True);records=[]
    for repo,lang in CASES.items():
        if a.repository and repo!=a.repository:continue
        hist=json.loads((HERE/'selection/histories'/f'{repo}.json').read_text());base=json.loads((HERE/'protocols'/f'{repo}.json').read_text())
        samples=hist['observations'] if (a.all_years or a.labels) else [hist['observations'][-1]]
        if a.labels:
            if set(a.labels)-{o['label'] for o in samples}:raise ValueError('Unknown snapshot label')
            samples=[o for o in samples if o['label'] in a.labels]
        for obs in samples:
            name=repo+'-'+obs['label'];archive=a.sources/(name+'.tar');scope=dict(base)
            seal=json.loads(archive.with_suffix('.manifest.json').read_text())
            if seal['commit']!=obs['commit'] or seal['sha256']!=hashlib.sha256(archive.read_bytes()).hexdigest():raise ValueError('Export seal mismatch')
            if lang=='python':
                year=int(obs['label'][-4:]);scope['python_parser']='legacy' if year<2017 else 'legacy3' if year==2017 else 'tree-sitter'
            scopefile=a.output/(name+'.scope.json');syntaxfile=a.output/(name+'.syntax.json');dest=a.output/(name+'.three-rules.json')
            if dest.exists():raise FileExistsError('Use a fresh output directory: '+str(dest))
            scopefile.write_bytes(canonical(scope))
            worker=(HERE/'detectors/syntax_worker.py').relative_to(Path.cwd())
            command=[a.parser_python,str(worker),'--packages',str(a.parser_packages),'--archive',str(archive),'--scope',str(scopefile),'--language',lang,'--repository',hist['repository'],'--commit',obs['commit'],'--output',str(syntaxfile)]
            subprocess.run(command,check=True,timeout=600)
            profile=next((p for p in profiles if p['repository']==repo and p['commit']==obs['commit']),None) if lang=='java' else None
            syntax=json.loads(syntaxfile.read_text());d=run(archive,syntax,a.java,a.java_classes,java_profile=profile);summary=validate(d);dest.write_bytes(canonical(d))
            if a.replay:
                subprocess.run(command,check=True,timeout=600)
                repeated=json.loads(syntaxfile.read_text())
                if canonical(syntax)!=canonical(repeated):raise ValueError('Syntax replay mismatch: '+name)
                again=run(archive,repeated,a.java,a.java_classes,java_profile=profile)
                if canonical(d)!=canonical(again):raise ValueError('Semantic replay mismatch: '+name)
            records.append({'repository':repo,'label':obs['label'],'commit':obs['commit'],'file':dest.name,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'semantic_replay_identical':True if a.replay else None,'syntax_replay_identical':True if a.replay else None,'rules':summary})
            (a.output/((a.repository or 'all')+'-manifest.json')).write_bytes(canonical(records))
            print(name,json.dumps(summary),flush=True)
if __name__=='__main__':main()
