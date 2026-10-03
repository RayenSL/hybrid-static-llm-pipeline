#!/usr/bin/env python3
"""Audit annual selection, raw measurements, plotted data, and equality evidence."""
from collections import Counter
import csv, datetime as dt, hashlib, json
from pathlib import Path
HERE=Path(__file__).resolve().parent; R=HERE/'annual_results'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
for rel,expected in read(R/'COMPACT_SHA256SUMS.json').items():assert sha(R/rel)==expected,rel
protocol=read(HERE/'protocol-annual-1.1.0.json'); manifest=read(R/'snapshot-manifest.json'); comparison=read(R/'comparison.json')
assert len(protocol['snapshots'])==20==len(manifest['observations'])==len(comparison['snapshots'])
assert len({x['commit'] for x in protocol['snapshots']})==20 and comparison['full_study_gate_passed']
history=manifest['history']; dates={x['commit']:x['committer_unix'] for x in history}
plotted={x['label']:x for x in csv.DictReader((HERE/'figures/annual_figure_data.csv').open())}
for i,sample in enumerate(protocol['snapshots']):
 label=sample['label']; measurement=R/'measurements'/(label+'.json'); result=read(measurement)
 assert result['status']=='complete' and not result['compilation_errors']
 assert Counter(x['type'] for x in result['findings'])==Counter(result['counts'])
 d,c=result['denominators'],result['counts']; rates=result['rates']
 assert abs(rates['god_class']-c['GodClass']/d['class_declarations'])<1e-15
 assert abs(rates['long_method']-c['LongMethod']/d['method_declarations'])<1e-15
 assert abs(rates['obsolete_affected_files']-result['obsolete_affected_files']/d['files'])<1e-15
 evidence=comparison['snapshots'][i]; assert evidence['label']==label and evidence['equal'] and evidence['all_complete']
 assert len(set(evidence['measurement_sha256'].values()))==1 and evidence['measurement_sha256']['A']==sha(measurement)
 plot=plotted[label]; assert plot['commit']==sample['commit'] and int(plot['ploc'])==d['physical_lines']
 assert abs(float(plot['god'])-100*rates['god_class'])<1e-12
 assert abs(float(plot['long'])-100*rates['long_method'])<1e-12
 assert abs(float(plot['obsolete'])-100*rates['obsolete_affected_files'])<1e-12
 if label.isdigit():
  boundary=dt.datetime(int(label)+1,1,1,tzinfo=dt.timezone.utc).timestamp()
  assert sample['commit']==next(x['commit'] for x in history if x['committer_unix']<boundary)
assert set(plotted)=={x['label'] for x in protocol['snapshots']}
print('Annual audit passed: 20 selections, valid compilations, counts, rates, plot data, and three-way equality')
