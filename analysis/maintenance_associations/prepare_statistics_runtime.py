"""Install isolated statistical wheels from checksum-pinned PyPI artefacts."""
import argparse,hashlib,io,json,sys,zipfile
from pathlib import Path
import requests
BASE=Path(__file__).resolve().parent
PACKAGES=['packaging==25.0','numpy==2.2.6','scipy==1.15.3','pandas==2.2.3','statsmodels==0.14.5','patsy==1.0.1','matplotlib==3.10.3','python-dateutil==2.9.0.post0','six==1.17.0','pytz==2025.2','tzdata==2025.2','contourpy==1.3.2','cycler==0.12.1','fonttools==4.58.1','kiwisolver==1.4.8','pillow==11.2.1','pyparsing==3.2.3']
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--lock',type=Path,default=BASE/'protocols/statistics-runtime-lock.json');a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(a.output.resolve()));locked=json.loads(a.lock.read_text()) if a.lock.exists() else None;records=[]
for item in PACKAGES:
 name,version=item.split('==')
 if locked:r=next(r for r in locked['wheels'] if r['package']==name and r['version']==version)
 else:
  response=requests.get(f'https://pypi.org/pypi/{name}/{version}/json',timeout=90);response.raise_for_status();files=response.json()['urls']
  if name=='packaging':f=next(f for f in files if f['filename'].endswith('py3-none-any.whl'))
  else:
   from packaging.tags import sys_tags
   from packaging.utils import parse_wheel_filename
   ranks={t:i for i,t in enumerate(sys_tags())};candidates=[]
   for f in files:
    if not f['filename'].endswith('.whl'):continue
    overlap=parse_wheel_filename(f['filename'])[3]&ranks.keys()
    if overlap:candidates.append((min(ranks[t] for t in overlap),f))
   f=min(candidates,key=lambda x:x[0])[1]
  r={'package':name,'version':version,'filename':f['filename'],'url':f['url'],'sha256':f['digests']['sha256']}
 response=requests.get(r['url'],timeout=120);response.raise_for_status();data=response.content;assert hashlib.sha256(data).hexdigest()==r['sha256']
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  assert all(not Path(p).is_absolute() and '..' not in Path(p).parts for p in z.namelist());z.extractall(a.output)
 records.append(r);print(name,version,'verified',flush=True)
if not locked:a.lock.write_text(json.dumps({'python':sys.version,'platform':sys.platform,'wheels':records},indent=2)+'\n')
