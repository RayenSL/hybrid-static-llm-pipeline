"""Refit merged fix-labelled counts and render the God Class category figure."""
import os
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
INPUT = ROOT/'analysis/god_class_change_categories/results/v1.1/comparison-file-counts.csv'
UPSTREAM = ROOT/'analysis/god_class_change_categories/results/v1.1/SHA256SUMS.json'
P = argparse.ArgumentParser()
P.add_argument('--packages', type=Path)
P.add_argument('--input', type=Path, default=INPUT)
P.add_argument('--seal', type=Path, default=UPSTREAM)
P.add_argument('--output', type=Path, required=True)
a = P.parse_args()
INPUT, UPSTREAM = a.input.resolve(), a.seal.resolve()
if a.packages:
    sys.path.insert(0, str(a.packages.resolve()))
import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm
from scipy import stats
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.sandwich_covariance import cov_cluster_2groups
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

OUT = a.output.resolve()
if OUT.exists() and any(OUT.iterdir()):
    raise SystemExit(f'Refusing to overwrite {OUT}')
OUT.mkdir(parents=True, exist_ok=True)
REPOS = ('jenkinsci__jenkins', 'apache__tomcat')
ORIGINAL = ('issue_linked_fix_labelled', 'other_fix_labelled', 'feature_labelled',
            'update_build_labelled', 'documentation_or_tests', 'refactor_cleanup_labelled',
            'security_labelled', 'revert', 'unclassified')
CATEGORIES = ('fix_labelled', 'feature_labelled', 'update_build_labelled',
              'documentation_or_tests', 'refactor_cleanup_labelled',
              'security_labelled', 'revert', 'unclassified')
ORDER = ('following365_raw_changes', *CATEGORIES)
LABELS = {'following365_raw_changes': 'All changes', 'fix_labelled': 'Fix-labelled',
          'feature_labelled': 'Feature cue', 'update_build_labelled': 'Update / build cue',
          'documentation_or_tests': 'Documentation / test cue',
          'refactor_cleanup_labelled': 'Refactor / cleanup cue',
          'security_labelled': 'Security cue', 'revert': 'Revert',
          'unclassified': 'Unclassified'}


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def dump(name, data):
    (OUT/name).write_text(json.dumps(data, sort_keys=True, indent=2, allow_nan=False)+'\n', encoding='utf8')


def design(f):
    terms = ['flag', 'C(snapshot)']
    for name in ('logsize', 'logprior'):
        if f[name].nunique() >= 5:
            knot = float((f[name].min()+f[name].max())/2)
            terms.append(f'bs({name}, knots=({knot!r},), degree=3, include_intercept=False)')
        elif f[name].nunique() > 1:
            terms.append(name)
    return patsy.dmatrix('1+'+'+'.join(terms), f, return_type='dataframe')


def fit(f, X, name):
    y = f[name].to_numpy(float)
    result = {'category': name, 'n_file_observations': len(f),
              'flagged_file_observations': int(f.flag.sum()),
              'positive_flagged': int(((f.flag == 1)&(f[name] > 0)).sum()),
              'positive_unflagged': int(((f.flag == 0)&(f[name] > 0)).sum()),
              'status': 'not_fitted'}
    reasons = []
    if f.snapshot.nunique() < 2:
        reasons.append('fewer_than_two_years')
    for flag in (0, 1):
        g = f[f.flag == flag]
        if g.lineage.nunique() < 20:
            reasons.append(f'flag_{flag}_fewer_than_20_lineages')
        if (g[name] > 0).sum() < 10 or (g[name] == 0).sum() < 10:
            reasons.append(f'flag_{flag}_fewer_than_10_positive_or_zero_rows')
    if reasons:
        result['reason'] = ';'.join(reasons)
        return result
    model = sm.GLM(y, X, family=sm.families.Poisson()).fit(maxiter=100)
    if not model.converged:
        result['reason'] = 'poisson_did_not_converge'
        return result
    idx = list(X.columns).index('flag')
    beta = float(model.params.iloc[idx])
    covariance, _, _ = cov_cluster_2groups(
        model, f.lineage.to_numpy(), pd.factorize(f.snapshot)[0], use_correction=True)
    variance = float(covariance[idx, idx])
    df = min(f.lineage.nunique(), f.snapshot.nunique())-1
    result.update(status='fitted', ratio=float(np.exp(beta)), reference_df=int(df))
    if math.isfinite(variance) and variance > 0:
        se = math.sqrt(variance)
        critical = stats.t.ppf(.975, df)
        result.update(ci_low=float(np.exp(beta-critical*se)),
                      ci_high=float(np.exp(beta+critical*se)),
                      p_value=float(2*stats.t.sf(abs(beta/se), df)))
    else:
        result['interval_status'] = 'unavailable_nonpositive_cluster_variance'
    return result


expected = json.loads(UPSTREAM.read_text())['comparison-file-counts.csv']
if sha(INPUT) != expected:
    raise ValueError('Upstream file counts differ from their sealed manifest')
f = pd.read_csv(INPUT, dtype={'snapshot': str})
if len(f) != 5367:
    raise ValueError('Unexpected comparison population')
f['fix_labelled'] = f.issue_linked_fix_labelled + f.other_fix_labelled
if not (f[list(ORIGINAL)].sum(axis=1) == f.following365_raw_changes).all():
    raise ValueError('Original categories do not partition total changes')
if not (f[list(CATEGORIES)].sum(axis=1) == f.following365_raw_changes).all():
    raise ValueError('Merged categories do not partition total changes')
f['logsize'] = np.log1p(f.file_ploc)
f['logprior'] = np.log1p(f.prior365_raw_changes)
models = []
counts = []
for repo in REPOS:
    g = f[f.repository == repo].copy()
    X = design(g)
    if np.linalg.matrix_rank(X.to_numpy()) != X.shape[1]:
        raise ValueError('Rank-deficient original model design')
    for flag, h in g.groupby('flag'):
        counts.append({'repository': repo, 'flag': int(flag), 'file_observations': len(h),
                       **{name: int(h[name].sum()) for name in ORDER}})
    for name in ORDER:
        models.append({'repository': repo, **fit(g, X, name)})
    ratio = next(r['ratio'] for r in models if r['repository'] == repo and r['category'] == 'following365_raw_changes')
    expected_ratio = 1.222548963522983 if repo == 'jenkinsci__jenkins' else 1.1423971557733392
    if abs(ratio-expected_ratio) > 1e-8:
        raise ValueError('Archived total ratio not reproduced')
valid = [r for r in models if r['category'] != 'following365_raw_changes' and r.get('p_value') is not None]
for r, p in zip(valid, multipletests([r['p_value'] for r in valid], method='holm')[1]):
    r['holm_p_value'] = float(p)

with (OUT/'models.csv').open('w', newline='', encoding='utf8') as h:
    fields = ['repository', 'category', 'status', 'reason', 'n_file_observations',
              'flagged_file_observations', 'positive_flagged', 'positive_unflagged',
              'ratio', 'ci_low', 'ci_high', 'p_value', 'holm_p_value', 'reference_df', 'interval_status']
    w = csv.DictWriter(h, fields, extrasaction='ignore', lineterminator='\n')
    w.writeheader()
    w.writerows(models)
with (OUT/'category-event-counts.csv').open('w', newline='', encoding='utf8') as h:
    fields = ['repository', 'flag', 'file_observations', *ORDER]
    w = csv.DictWriter(h, fields, lineterminator='\n')
    w.writeheader()
    w.writerows(counts)
dump('models.json', models)

plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9,
                     'pdf.fonttype': 42, 'svg.fonttype': 'none'})
fig, axes = plt.subplots(1, 2, figsize=(11.5, 5.1), sharey=True, layout='constrained')
ticks = [.75, 1, 1.25, 1.5, 2, 3, 4]
for ax, repo, title in zip(axes, REPOS, ('Jenkins', 'Apache Tomcat')):
    ax.axvline(1, color='0.45', linestyle='--', linewidth=.9, zorder=1)
    ax.axhline(.5, color='0.75', linewidth=.7)
    for y, name in enumerate(ORDER):
        r = next(z for z in models if z['repository'] == repo and z['category'] == name)
        if r['status'] == 'fitted' and r.get('ci_low') is not None:
            value, low, high = r['ratio'], r['ci_low'], r['ci_high']
            colour = '#252525' if name == 'following365_raw_changes' else '#225b77'
            marker = 's' if name == 'following365_raw_changes' else 'o'
            ax.errorbar(value, y, xerr=[[value-low], [high-value]], fmt=marker,
                        color=colour, capsize=3, markersize=5, linewidth=1.15, zorder=3)
        else:
            ax.text(.96, y, 'Sparse', ha='right', va='center', color='0.45', fontsize=8,
                    transform=ax.get_yaxis_transform())
    ax.set_title(title, fontsize=10, pad=8)
    ax.set_xscale('log')
    ax.set_xlim(.68, 4.35)
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, pos: f'{x:g}'))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.grid(axis='x', color='0.88', linewidth=.6)
    ax.set_ylim(len(ORDER)-.5, -.5)
    ax.set_yticks(range(len(ORDER)), [LABELS[n] for n in ORDER])
    ax.spines[['top', 'right']].set_visible(False)
    ax.tick_params(axis='y', length=0)
for ax in axes:
    ax.tick_params(axis='y', labelleft=True)
fig.supxlabel('Adjusted mean change-count ratio (God Class flagged / unflagged)', fontsize=9)
fig.savefig(OUT/'god-class-change-categories.pdf', metadata={'CreationDate': None, 'ModDate': None})
fig.savefig(OUT/'god-class-change-categories.png', dpi=220,
            metadata={'Software': 'matplotlib'})
plt.close(fig)

dump('provenance.json', {'source': str(INPUT), 'source_sha256': sha(INPUT),
                         'upstream_manifest_sha256': sha(UPSTREAM),
                         'protocol_sha256': sha(BASE/'PROTOCOL.md'),
                         'script_sha256': sha(Path(__file__)),
                         'packages': {n: __import__(n).__version__ for n in
                                      ('numpy', 'scipy', 'pandas', 'statsmodels', 'patsy', 'matplotlib')}})
dump('SHA256SUMS.json', {p.name: sha(p) for p in sorted(OUT.iterdir()) if p.is_file()})
for row in models:
    if row['category'] in ('following365_raw_changes', 'fix_labelled'):
        print(row, flush=True)
