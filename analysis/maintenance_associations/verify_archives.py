"""Verify retained archives against seals and frozen Git tree blob identities."""
import hashlib,json,subprocess,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'analysis/maintenance_associations'
cache=ROOT/'tmp/maintenance-associations/git'
archives=ROOT/'tmp/multilanguage-evolution/annual-sources'
results=[]
for rid in ['jenkinsci__jenkins','apache__tomcat','odoo__odoo']:
 h=json.loads((ROOT/f'analysis/multilanguage_evolution/selection/histories/{rid}.json').read_text())
 for sample in h['observations']:
  label=sample['label'];p=archives/f'{rid}-{label}.tar'
  seal=json.loads(p.with_suffix('.manifest.json').read_text())
  assert seal['commit']==sample['commit']
  checksum=hashlib.sha256()
  with p.open('rb') as f:
   for b in iter(lambda:f.read(1024*1024),b''):checksum.update(b)
  assert checksum.hexdigest()==seal['sha256'],str(p)
  raw=subprocess.check_output(['git','--git-dir',str(cache/rid),'ls-tree','-r','-z',sample['commit']])
  tree={}
  for record in raw.split(b'\0'):
   if record:
    meta,path=record.split(b'\t',1);mode,kind,oid=meta.split();tree[path.decode()] = (kind.decode(),oid.decode())
  checked=0
  with tarfile.open(p) as t:
   for m in t:
    if not m.isfile():continue
    body=t.extractfile(m).read()
    oid=hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()
    assert tree.get(m.name)==('blob',oid),(rid,label,m.name)
    checked+=1
  results.append({'repository':rid,'snapshot':label,'commit':sample['commit'],'archive_sha256':checksum.hexdigest(),'verified_regular_files':checked,'all_archived_regular_file_blobs_match':True,'scope_completeness_validated':False})
 print(rid,'21 archives verified',flush=True)
out=BASE/'results/archive-verification.json';out.write_text(json.dumps(results,indent=2)+'\n')
