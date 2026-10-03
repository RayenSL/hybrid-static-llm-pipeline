"""Install checksum-verified wheels without modifying the system Python installation."""
import argparse,hashlib,json,sys,zipfile,io
from pathlib import Path
import requests
HERE=Path(__file__).resolve().parent
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--lock',type=Path,required=True);a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(a.output.resolve()));records=[]
    frozen=json.loads(a.lock.read_text()) if a.lock.exists() else None
    packages=['packaging==26.3']+(HERE/'detectors/requirements.txt').read_text().splitlines()
    for item in packages:
        if not item.strip() or item.startswith('#'):continue
        name,version=item.split('==')
        if frozen:
            record=next(x for x in frozen['wheels'] if x['package']==name and x['version']==version)
            response=requests.get(record['url'],timeout=120);response.raise_for_status();data=response.content
            if hashlib.sha256(data).hexdigest()!=record['sha256']:raise ValueError('Frozen wheel checksum mismatch')
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if any(Path(member).is_absolute() or '..' in Path(member).parts for member in z.namelist()):raise ValueError('Unsafe wheel path')
                z.extractall(a.output)
            records.append(record);print(name,version,'verified frozen wheel',flush=True);continue
        r=requests.get(f'https://pypi.org/pypi/{name}/{version}/json',timeout=60);r.raise_for_status();files=r.json()['urls']
        if name=='packaging':candidates=[f for f in files if f['filename'].endswith('py3-none-any.whl')]
        else:
            from packaging.tags import sys_tags
            from packaging.utils import parse_wheel_filename
            ranks={tag:i for i,tag in enumerate(sys_tags())};candidates=[]
            for f in files:
                if not f['filename'].endswith('.whl'):continue
                tags=parse_wheel_filename(f['filename'])[3];overlap=tags&ranks.keys()
                if overlap:f['_rank']=min(ranks[t] for t in overlap);candidates.append(f)
            candidates.sort(key=lambda f:f['_rank'])
        if not candidates:raise RuntimeError('No supported wheel for '+item)
        f=candidates[0];response=requests.get(f['url'],timeout=120);response.raise_for_status();data=response.content
        if hashlib.sha256(data).hexdigest()!=f['digests']['sha256']:raise ValueError('Wheel checksum mismatch')
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for member in z.namelist():
                if Path(member).is_absolute() or '..' in Path(member).parts:raise ValueError('Unsafe wheel path')
            z.extractall(a.output)
        records.append({'package':name,'version':version,'filename':f['filename'],'url':f['url'],'sha256':f['digests']['sha256']});print(name,version,flush=True)
    if not frozen:a.lock.write_text(json.dumps({'platform':sys.platform,'python':sys.version,'wheels':records},indent=2)+'\n')
