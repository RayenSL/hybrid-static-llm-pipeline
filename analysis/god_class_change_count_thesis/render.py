"""Render a God Class-only thesis insert from the sealed count-model table."""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
SOURCE = ROOT / 'analysis/maintenance_associations/results/final-automated-analysis-v0.7/models.csv'

parser = argparse.ArgumentParser()
parser.add_argument('--packages', type=Path)
parser.add_argument('--source', type=Path, default=SOURCE)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
SOURCE = args.source.resolve()
if args.packages:
    sys.path.insert(0, str(args.packages.resolve()))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

output = args.output.resolve()
if output.exists() and any(output.iterdir()):
    raise SystemExit(f'Refusing to overwrite {output}')
output.mkdir(parents=True, exist_ok=True)

with SOURCE.open(newline='', encoding='utf8') as f:
    rows = [r for r in csv.DictReader(f) if r['rule'] == 'GodClass' and r['endpoint'] == 'count']
by_repo = {r['repository']: r for r in rows}
assert set(by_repo) == {'odoo__odoo', 'jenkinsci__jenkins', 'apache__tomcat'}
assert by_repo['odoo__odoo']['status'] == 'not_fitted'
jenkins = by_repo['jenkinsci__jenkins']
tomcat = by_repo['apache__tomcat']
for row in (jenkins, tomcat):
    assert row['status'] == 'fitted'
    assert float(row['ci_low']) < float(row['effect']) < float(row['ci_high'])

plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9, 'pdf.fonttype': 42})
fig, ax = plt.subplots(figsize=(7.0, 2.35), layout='constrained')
ax.axvline(1.0, color='0.45', linestyle='--', linewidth=0.9)
for y, row, label in [(1, jenkins, 'Jenkins'), (0, tomcat, 'Apache Tomcat')]:
    effect = float(row['effect'])
    low = float(row['ci_low'])
    high = float(row['ci_high'])
    ax.errorbar(effect, y, xerr=[[effect-low], [high-effect]], fmt='o',
                color='#245b78', markersize=6, capsize=4, linewidth=1.2)
    ax.text(high + 0.012, y, f'{effect:.3f}', va='center', fontsize=8)
ax.set_yticks([1, 0], ['Jenkins', 'Apache Tomcat'])
ax.set_ylim(-0.55, 1.55)
ax.set_xlim(0.97, 1.39)
ax.set_xticks([1.0, 1.1, 1.2, 1.3])
ax.set_xlabel('Adjusted mean change-count ratio')
ax.spines[['top', 'right']].set_visible(False)
ax.grid(axis='x', alpha=0.15)
fig.savefig(output/'god-class-adjusted-change-count.pdf', metadata={'CreationDate': None, 'ModDate': None})
plt.close(fig)

sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
(output/'provenance.json').write_text(json.dumps({
    'source': str(SOURCE), 'source_sha256': sha(SOURCE),
    'script_sha256': sha(Path(__file__)), 'model_repositories': list(by_repo)
}, sort_keys=True, indent=2)+'\n', encoding='utf8')
(output/'SHA256SUMS.json').write_text(json.dumps({p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()},
                                                sort_keys=True, indent=2)+'\n', encoding='utf8')
print(output/'god-class-adjusted-change-count.pdf')
