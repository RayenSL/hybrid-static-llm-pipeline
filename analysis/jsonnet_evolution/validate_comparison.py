#!/usr/bin/env python3
"""Audit published comparison evidence without rebuilding historical projects."""
import csv, hashlib, json
from collections import Counter
from pathlib import Path
HERE=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
plot={(r['repository'],r['label']):r for r in csv.DictReader((HERE/'figures/comparative_figure_data.csv').open())}
for name,folder in [('Json.NET','annual_results'),('OpenRA','openra_annual_results'),('nopCommerce','nopcommerce_annual_results')]:
 root=HERE/folder
 for rel,digest in read(root/'COMPACT_SHA256SUMS.json').items():assert sha(root/rel)==digest,(name,rel)
 comp=read(root/'comparison.json')['snapshots']; samples=read(root/'protocol.json')['snapshots'] if (root/'protocol.json').exists() else read(HERE/'protocol-annual-1.1.0.json')['snapshots']
 assert {x['label'] for x in comp}=={x['label'] for x in samples}
 valid=0
 for item in comp:
  label=item['label']; row=plot[name,label]; ok=item['equal'] and item['all_complete']; assert (row['reproduced']=='True')==ok
  if not ok:
   assert all(row[k]=='' for k in ['GodClass','LongMethod','ObsoleteApiUsage','obsolete_affected_files','physical_lines','god_class_rate','long_method_rate','obsolete_affected_files_rate'])
   continue
  valid+=1; path=root/'measurements'/(label+'.json'); m=read(path); assert m['status']=='complete' and not m['compilation_errors']
  assert len(set(item['measurement_sha256'].values()))==1 and item['measurement_sha256']['A']==sha(path)
  assert Counter(x['type'] for x in m['findings'])==Counter(m['counts'])
  assert int(row['physical_lines'])==m['denominators']['physical_lines']
  for key in ['GodClass','LongMethod','ObsoleteApiUsage']:assert int(row[key])==m['counts'][key]
  for key,rate in [('god_class_rate','god_class'),('long_method_rate','long_method'),('obsolete_affected_files_rate','obsolete_affected_files')]:assert abs(float(row[key])-m['rates'][rate])<1e-14
 print(f'{name}: {valid}/{len(comp)} complete and reproduced; checksums, counts, and plot data verified')
assert len(plot)==57
