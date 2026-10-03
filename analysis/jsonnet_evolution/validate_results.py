#!/usr/bin/env python3
"""Audit the compact published pilot without build tools or network access."""
from collections import Counter
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / 'pilot_results'

def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def close(a, b): return a == b or (a is not None and b is not None and abs(a-b) < 1e-15)

checksums = read(RESULTS / 'SHA256SUMS.json')
for relative, expected in checksums.items():
    assert sha(RESULTS / relative) == expected, f'checksum: {relative}'
protocol = read(HERE / 'protocol.json')
manifest = read(RESULTS / 'snapshot-manifest.json')
assert manifest['protocol_sha256'] == sha(HERE / 'protocol.json')
assert manifest['endpoint_commit'] == protocol['endpoint_commit']
assert len(manifest['observations']) == 78
assert len({x['commit'] for x in manifest['observations']}) == 70
assert [x['commit'] for x in manifest['pilot_archives']] == [x['commit'] for x in protocol['pilot_commits']]
# Re-evaluate every non-root/non-endpoint boundary from recorded first-parent history.
history = manifest['history']
for observation in manifest['observations'][1:-1]:
    boundary = __import__('datetime').datetime.fromisoformat(observation['boundary_utc']).timestamp()
    expected = next(c['commit'] for c in history if c['committer_unix'] < boundary)
    assert observation['commit'] == expected, f'selection: {observation["label"]}'
comparison = {x['label']: x for x in read(RESULTS / 'comparison.json')['snapshots']}
for sample in protocol['pilot_commits']:
    label = sample['label']; path = RESULTS / 'measurements' / (label + '.json'); result = read(path)
    assert result['status'] == 'complete' and not result['compilation_errors']
    actual = Counter(x['type'] for x in result['findings'])
    assert actual == Counter(result['counts']), f'finding counts: {label}'
    d, c, rates = result['denominators'], result['counts'], result['rates']
    assert d['files'] > 0 and d['class_declarations'] > 0 and d['method_declarations'] > 0
    assert close(rates['god_class'], c['GodClass']/d['class_declarations'])
    assert close(rates['long_method'], c['LongMethod']/d['method_declarations'])
    assert close(rates['obsolete_affected_files'], result['obsolete_affected_files']/d['files'])
    evidence = comparison[label]
    assert evidence['all_complete'] and evidence['equal']
    assert len(set(evidence['measurement_sha256'].values())) == 1
    assert evidence['measurement_sha256']['A'] == sha(path)
print('Published pilot audit passed: checksums, selection, validity, counts, rates, and three-way equality')
