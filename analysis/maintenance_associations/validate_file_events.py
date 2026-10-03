"""Validate database seals, integrity and final paths against frozen Git trees."""
import hashlib,json,shutil,sqlite3,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'analysis/maintenance_associations';report=[]
for rid in ['odoo__odoo','jenkinsci__jenkins','apache__tomcat']:
 m=json.loads((BASE/f'results/file-events/{rid}.json').read_text())
 source=ROOT/m['database']
 with tempfile.TemporaryDirectory(prefix='maintenance-validate-') as tmp:
  p=Path(tmp)/'events.sqlite';shutil.copyfile(source,p)
  assert hashlib.sha256(p.read_bytes()).hexdigest()==m['database_sha256']
  db=sqlite3.connect(f'file:{p}?mode=ro',uri=True)
  raw=subprocess.check_output(['git','--git-dir',str(ROOT/f'tmp/maintenance-associations/git/{rid}'),'ls-tree','-r','--name-only','-z',m['endpoint']])
  expected={x.decode() for x in raw.split(b'\0') if x};actual={p for p, in db.execute('SELECT path FROM states')}
  assert actual==expected,(rid,len(actual-expected),len(expected-actual))
  integrity=db.execute('PRAGMA integrity_check').fetchone()[0];assert integrity=='ok'
  prior=0;maxshift=0
  for ts, in db.execute('SELECT timestamp FROM events ORDER BY seq'):prior=max(prior,ts);maxshift=max(maxshift,prior-ts)
  report.append({'repository':rid,'database_seal_verified':True,'final_paths_match_git_tree':True,'paths':len(actual),'sqlite_integrity':integrity,'maximum_ancestry_clock_shift_seconds':maxshift})
  db.close()
(BASE/'results/file-events/validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
