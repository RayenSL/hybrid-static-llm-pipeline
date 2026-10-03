import sys,shutil,json,hashlib
from pathlib import Path
src=Path(sys.argv[1]); dst=Path(sys.argv[2]); name=sys.argv[3]
if dst.exists():shutil.rmtree(dst)
dst.mkdir();(dst/'measurements').mkdir()
for f in ['comparison.json','pilot-summary.csv','pilot-status.json','protocol.json','snapshot-manifest.json','tool-manifest.json','REPORT.md','PROTOCOL.md','reference-packages.json']:
 if (src/f).exists():shutil.copy2(src/f,dst/f)
c=json.loads((src/'comparison.json').read_text()); valid={x['label'] for x in c['snapshots'] if x['equal'] and x['all_complete']}
for label in valid:shutil.copy2(src/'measurements'/'A'/(label+'.json'),dst/'measurements'/(label+'.json'))
status=json.loads((src/'pilot-status.json').read_text())
# Keep full phase/status structure; strip machine-specific path prefixes from errors.
def sanitize(value):
 if isinstance(value,dict):return {k:sanitize(v) for k,v in value.items()}
 if isinstance(value,list):return [sanitize(v) for v in value]
 if isinstance(value,str) and 'see ' in value:return value.split('see ')[0]+'see full bundle logs'
 return value
(dst/'failure-evidence.json').write_text(json.dumps(sanitize(status),indent=2)+'\n')
(dst/'README.md').write_text(f'''# {name} annual comparison\n\nCompact, checksum-audited evidence for the primary-component annual analysis. `measurements/` contains only complete observations whose independent A, B, and offline JSON outputs are byte-identical. Other observations are documented in `failure-evidence.json` and are never interpreted as zero. The full sealed bundle is `{src}`.\n''')
files=sorted(p for p in dst.rglob('*') if p.is_file() and p.name!='COMPACT_SHA256SUMS.json')
sums={p.relative_to(dst).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(dst/'COMPACT_SHA256SUMS.json').write_text(json.dumps(sums,indent=2)+'\n')
print(name,len(valid))
