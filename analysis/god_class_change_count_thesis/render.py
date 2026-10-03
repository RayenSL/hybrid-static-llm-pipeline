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
parser.add_argument('--packages', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
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

text = rf'''\paragraph{{God Class and subsequent change frequency.}}
We compared production files with and without a detected God Class within each repository. The outcome was the number of recorded mainline changes to the file during the following 365 days. Each comparison retained file-at-snapshot observations with overlapping baseline file size and preceding-year change activity; the count model adjusted for those variables and calendar year. In Jenkins, the adjusted mean change-count ratio was {float(jenkins['effect']):.3f} (95\% interval {float(jenkins['ci_low']):.3f}--{float(jenkins['ci_high']):.3f}; {int(jenkins['n']):,} comparison observations, of which {int(jenkins['flagged_rows']):,} were flagged). In Apache Tomcat, it was {float(tomcat['effect']):.3f} ({float(tomcat['ci_low']):.3f}--{float(tomcat['ci_high']):.3f}; {int(tomcat['n']):,} observations, of which {int(tomcat['flagged_rows']):,} were flagged). These estimates correspond to {(float(jenkins['effect'])-1)*100:.1f}\% and {(float(tomcat['effect'])-1)*100:.1f}\% more recorded changes, respectively, conditional on the modelled covariates. Odoo supplied only nine flagged observations in the supported comparison population, so no ratio was fitted. Figure~\ref{{fig:god-class-adjusted-change-count}} presents the fitted ratios.

\begin{{figure}}[tbp]
    \centering
    \includegraphics[width=0.68\linewidth]{{figures/god-class-adjusted-change-count.pdf}}
    \caption{{Adjusted mean change-count ratios for files flagged for God Class versus other eligible production files during the following 365 days. Points are repository-specific ratios; bars are 95\% intervals without multiplicity adjustment, with uncertainty clustered by file lineage and calendar year. The dashed line denotes equal adjusted mean counts. Odoo did not meet the prespecified support threshold and has no estimate.}}
    \label{{fig:god-class-adjusted-change-count}}
\end{{figure}}

The count comparison was a secondary analysis, and its intervals were not adjusted for multiple comparisons. Recorded changes are an activity measure, not developer hours, corrective-maintenance cost or defects. Files with central responsibilities may also be changed frequently for reasons unrelated to the detected class structure. The observed association therefore identifies a useful group for closer investigation, but does not establish that the God Class condition caused the additional changes or that removing it would reduce them.
'''
(output/'thesis-god-class-count.tex').write_text(text, encoding='utf8')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
(output/'provenance.json').write_text(json.dumps({
    'source': str(SOURCE.relative_to(ROOT)), 'source_sha256': sha(SOURCE),
    'script_sha256': sha(Path(__file__)), 'model_repositories': list(by_repo)
}, sort_keys=True, indent=2)+'\n', encoding='utf8')
(output/'SHA256SUMS.json').write_text(json.dumps({p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()},
                                                sort_keys=True, indent=2)+'\n', encoding='utf8')
print(output/'thesis-god-class-count.tex')
print(output/'god-class-adjusted-change-count.pdf')
