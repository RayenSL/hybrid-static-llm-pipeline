"""Assemble explicitly selected, verified snapshot batches without choosing results by count."""
import argparse,hashlib,json,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
CASES={'odoo__odoo','jenkinsci__jenkins','apache__tomcat'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--case-source',action='append',required=True,metavar='REPOSITORY=DIRECTORY');ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();chosen={r:{} for r in CASES}
    for entry in a.case_source:
        repo,directory=entry.split('=',1)
        if repo not in CASES:raise ValueError('Unknown repository')
        directory=Path(directory)
        for record in json.loads((directory/(repo+'-manifest.json')).read_text()):
            if record['repository']!=repo:raise ValueError('Repository mismatch')
            if Path(record['file']).name!=record['file']:raise ValueError('Unsafe result filename')
            if record.get('syntax_replay_identical') is not True or record.get('semantic_replay_identical') is not True:raise ValueError('Unverified replay')
            if sha(directory/record['file'])!=record['sha256']:raise ValueError('Result checksum mismatch')
            old=chosen[repo].get(record['label'])
            if old and old[0]['sha256']!=record['sha256']:raise ValueError('Conflicting snapshot results; select one protocol explicitly')
            chosen[repo][record['label']]=(record,directory)
    planned=[]
    for repo in sorted(CASES):
        history=json.loads((HERE/'selection/histories'/f'{repo}.json').read_text());expected={o['label'] for o in history['observations']}
        if set(chosen[repo])!=expected:raise ValueError('Missing or extra snapshots for '+repo)
        records=[]
        for obs in history['observations']:
            record,directory=chosen[repo][obs['label']]
            if record['commit']!=obs['commit']:raise ValueError('Frozen commit mismatch')
            records.append(record)
            for name in [record['file'],repo+'-'+obs['label']+'.syntax.json',repo+'-'+obs['label']+'.scope.json']:
                source=directory/name;dest=a.output/name
                if not source.is_file():raise FileNotFoundError(source)
                if dest.exists() and sha(source)!=sha(dest):raise FileExistsError('Refusing to replace different evidence: '+str(dest))
                planned.append((source,dest))
        planned.append((json.dumps(records,sort_keys=True,separators=(',',':')).encode()+b'\n',a.output/(repo+'-manifest.json')))
    a.output.mkdir(exist_ok=True,parents=True)
    for source,dest in planned:
        if isinstance(source,bytes):
            if dest.exists() and dest.read_bytes()!=source:raise FileExistsError(dest)
            dest.write_bytes(source)
        elif not dest.exists():shutil.copyfile(source,dest)
    print('Assembled all 63 verified snapshots')
