"""Classify God Class follow-up changes by conservative commit-title cues."""
import os
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
import argparse
import bisect
import collections
import csv
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
P = argparse.ArgumentParser()
P.add_argument('--packages', type=Path, required=True)
P.add_argument('--output', type=Path, required=True)
a = P.parse_args()
sys.path.insert(0, str(a.packages.resolve()))
import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm
from scipy import stats
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.sandwich_covariance import cov_cluster_2groups

OUT = a.output.resolve()
if OUT.exists() and any(OUT.iterdir()):
    raise SystemExit(f'Refusing to overwrite {OUT}')
OUT.mkdir(parents=True, exist_ok=True)
REPOS = ('jenkinsci__jenkins', 'apache__tomcat')
DAY = 86400
CATEGORIES = ('revert', 'security_labelled', 'documentation_or_tests',
              'issue_linked_fix_labelled', 'other_fix_labelled', 'feature_labelled',
              'update_build_labelled', 'refactor_cleanup_labelled', 'unclassified')
INPUT = ROOT/'analysis/maintenance_associations/results/final-automated-analysis-v0.7/analysis-input.csv.gz'
ARCHIVED_MODELS = ROOT/'analysis/maintenance_associations/results/final-automated-analysis-v0.7/models.json'


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def dump(name, data):
    (OUT/name).write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False)+'\n', encoding='utf8')


def write(name, rows, fields):
    with (OUT/name).open('w', newline='', encoding='utf8') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n', extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


SECURITY = re.compile(r'\b(?:CVE-\d+|CWE-\d+|SECURITY-\d+|vulnerabilit\w*|XSS|CSRF|XXE|exploit\w*|security\s+(?:fix|advisory|issue|hardening|patch))\b', re.I)
DOCUMENTATION = re.compile(r'\b(?:documentation|javadoc|docs|readme|translation\w*|tests?|TCK|typos?)\b', re.I)
FIX = re.compile(r'\b(?:fix|fixed|fixes|bug|correct|corrected|resolve|resolved|regression|prevent|avoid|repair)\b', re.I)
FEATURE = re.compile(r'\b(?:feature|add|added|implement\w*|introduce\w*|enable\w*|support|allow)\b', re.I)
UPDATE = re.compile(r'\b(?:update\w*|upgrade\w*|bump|dependenc\w*|version|release|build|maven|gradle|CI)\b', re.I)
REFACTOR = re.compile(r'\b(?:refactor\w*|clean[ -]?up|simplif\w*|rework\w*|rename\w*|format\w*)\b', re.I)
JENKINS_ISSUE = re.compile(r'\b(?:JENKINS|HUDSON)-\d+\b', re.I)
TOMCAT_ISSUE = re.compile(r'\b(?:BZ|Bug)\s*[-#:]?\s*\d+\b|https?://(?:issues\.apache\.org|bz\.apache\.org)/bugzilla/show_bug\.cgi\?id=\d+', re.I)
JENKINS_STRICT = re.compile(r'\b(?:fix|fixed|fixes|regression)\b', re.I)
TOMCAT_STRICT = re.compile(r'\b(?:fix|fixed|fixes|correct|resolve)\b', re.I)
MERGE = re.compile(r'^\s*Merge (?:pull request|branch|commit)\b', re.I)
REVERT = re.compile(r'^\s*(?:Revert|Re-apply)\b', re.I)


def title_for_classification(subject, body):
    if MERGE.search(subject):
        for line in body.splitlines():
            if line.strip():
                return line.strip(), 'merge_body_first_line'
        return '', 'generic_merge_without_title'
    return subject.strip(), 'subject'


def classify(repo, title):
    strict = ((JENKINS_ISSUE.search(title) and JENKINS_STRICT.search(title)) if repo == 'jenkinsci__jenkins'
              else (TOMCAT_ISSUE.search(title) and TOMCAT_STRICT.search(title)))
    cues = {
        'revert': bool(REVERT.search(title)),
        'security_labelled': bool(SECURITY.search(title)),
        'documentation_or_tests': bool(DOCUMENTATION.search(title)),
        'issue_linked_fix_labelled': bool(strict),
        'other_fix_labelled': bool(FIX.search(title)),
        'feature_labelled': bool(FEATURE.search(title)),
        'update_build_labelled': bool(UPDATE.search(title)),
        'refactor_cleanup_labelled': bool(REFACTOR.search(title)),
    }
    matches = [k for k in CATEGORIES if cues.get(k)]
    return (matches[0] if matches else 'unclassified'), ','.join(matches)


def git_messages(repo):
    git = ROOT/'tmp/maintenance-associations/git'/repo
    head = subprocess.run(['git', '--git-dir='+str(git), 'rev-parse', 'HEAD'],
                          check=True, capture_output=True, text=True).stdout.strip()
    proc = subprocess.run(['git', '--git-dir='+str(git), 'log', '--first-parent',
                           '--format=%H%x1f%s%x1f%b%x1e', 'HEAD'],
                          check=True, capture_output=True, text=True)
    messages = {}
    for record in proc.stdout.split('\x1e'):
        record = record.strip('\n')
        if not record:
            continue
        fields = record.split('\x1f', 2)
        if len(fields) != 3 or len(fields[0]) != 40:
            raise ValueError('Unexpected Git message record')
        h, subject, body = fields
        if h in messages:
            raise ValueError('Repeated commit in first-parent history')
        messages[h] = (subject, body)
    return head, messages


def overlap(f):
    keep = []
    for year, g in f.groupby('snapshot'):
        if g.flag.nunique() != 2:
            continue
        mask = np.ones(len(g), dtype=bool)
        for cov in ('file_ploc', 'prior365_raw_changes'):
            bounds = g.groupby('flag')[cov].agg(['min', 'max'])
            mask &= g[cov].between(bounds['min'].max(), bounds['max'].min()).to_numpy()
        h = g[mask]
        if h.flag.nunique() == 2:
            keep.append(h)
    return pd.concat(keep) if keep else f.iloc[:0].copy()


def design(f):
    terms = ['flag', 'C(snapshot)']
    for name in ('logsize', 'logprior'):
        if f[name].nunique() >= 5:
            knot = float((f[name].min()+f[name].max())/2)
            terms.append(f'bs({name}, knots=({knot!r},), degree=3, include_intercept=False)')
        elif f[name].nunique() > 1:
            terms.append(name)
    return patsy.dmatrix('1+'+'+'.join(terms), f, return_type='dataframe')


def model(f, X, name):
    y = f[name].to_numpy(float)
    result = {'category': name, 'n': len(f), 'flagged_rows': int(f.flag.sum()),
              'positive_flagged_rows': int(((f.flag == 1)&(f[name] > 0)).sum()),
              'positive_unflagged_rows': int(((f.flag == 0)&(f[name] > 0)).sum()),
              'status': 'not_fitted'}
    why = []
    if f.snapshot.nunique() < 2:
        why.append('fewer_than_two_years')
    for flag in (0, 1):
        g = f[f.flag == flag]
        if g.lineage.nunique() < 20:
            why.append(f'flag_{flag}_fewer_than_20_lineages')
        if (g[name] > 0).sum() < 10 or (g[name] == 0).sum() < 10:
            why.append(f'flag_{flag}_fewer_than_10_positive_or_zero_rows')
    if why:
        result['reason'] = ';'.join(why)
        return result
    fit = sm.GLM(y, X, family=sm.families.Poisson()).fit(maxiter=100)
    if not fit.converged:
        result['reason'] = 'poisson_did_not_converge'
        return result
    idx = list(X.columns).index('flag')
    beta = float(fit.params.iloc[idx])
    covariance, _, _ = cov_cluster_2groups(
        fit, f.lineage.to_numpy(), pd.factorize(f.snapshot)[0], use_correction=True)
    variance = float(covariance[idx, idx])
    df = min(f.lineage.nunique(), f.snapshot.nunique())-1
    result.update(status='fitted', ratio=float(np.exp(beta)), reference_df=int(df),
                  pearson_dispersion=float(np.sum((y-fit.predict(X))**2/np.maximum(fit.predict(X), 1e-12))/(len(y)-X.shape[1])))
    if np.isfinite(variance) and variance > 0:
        se = variance**0.5
        crit = stats.t.ppf(.975, df)
        result.update(ci_low=float(np.exp(beta-crit*se)), ci_high=float(np.exp(beta+crit*se)),
                      p_value=float(2*stats.t.sf(abs(beta/se), df)))
    else:
        result['interval_status'] = 'unavailable_nonpositive_cluster_variance'
    return result


df = pd.read_csv(INPUT, compression='gzip', dtype={'snapshot': str})
if len(df) != 80993:
    raise ValueError('Unexpected corrected cohort size')
all_files = []
commit_audit = []
selected_event_audit = []
all_event_audit = []
input_hashes = {'analysis_input': sha(INPUT), 'archived_models': sha(ARCHIVED_MODELS),
                'protocol': sha(BASE/'PROTOCOL_v1_1.md'), 'pilot_protocol': sha(BASE/'PROTOCOL.md'), 'script': sha(Path(__file__)), 'histories': {}}
for repo in REPOS:
    sub = df[(df.rid == repo)&df.GodClass_findings.notna()&(df.classes > 0)].copy()
    sub['flag'] = (sub.GodClass_findings > 0).astype(int)
    dbpath = ROOT/f'tmp/maintenance-associations/file-events/{repo}.sqlite'
    conn = sqlite3.connect('file:'+str(dbpath)+'?mode=ro', uri=True)
    events = {int(s): (h, int(t)) for s, h, t in conn.execute('SELECT seq,commit_hash,timestamp FROM events')}
    hash_to_seq = {h: seq for seq, (h, t) in events.items()}
    bylineage = collections.defaultdict(set)
    for seq, lineage in conn.execute('SELECT seq,lineage FROM changes'):
        bylineage[int(lineage)].add(int(seq))
    bylineage = {k: sorted(v) for k, v in bylineage.items()}
    conn.close()
    head, messages = git_messages(repo)
    if not set(h for h, t in events.values()).issubset(messages):
        raise ValueError('Missing first-parent commit messages')
    categories = {}
    for seq, (h, t) in events.items():
        subject, body = messages[h]
        title, source = title_for_classification(subject, body)
        category, cues = classify(repo, title)
        categories[seq] = category
        commit_audit.append({'repository': repo, 'seq': seq, 'commit': h, 'timestamp': t,
                             'subject': subject, 'classification_title': title,
                             'title_source': source, 'category': category, 'matching_cues': cues})
    input_hashes['histories'][repo] = {'git_head': head, 'event_database_sha256': sha(dbpath),
                                       'first_parent_event_count': len(events)}
    for row in sub.itertuples():
        base_seq = hash_to_seq[row.baseline_commit]
        base_t = int(row.baseline_timestamp)
        seqs = bylineage.get(int(row.lineage), [])
        start = bisect.bisect_right(seqs, base_seq)
        selected = [s for s in seqs[start:] if base_t < events[s][1] <= base_t+365*DAY]
        if len(selected) != int(row.following365_raw_changes):
            raise ValueError(f'Change-count mismatch {repo} {row.snapshot} {row.baseline_path}')
        counts = collections.Counter(categories[s] for s in selected)
        for seq in selected:
            all_event_audit.append({'repository': repo, 'snapshot': row.snapshot, 'baseline_path': row.baseline_path,
                                    'lineage': int(row.lineage), 'flag': int(row.flag), 'seq': seq,
                                    'commit': events[seq][0], 'category': categories[seq]})
        rec = {'repository': repo, 'snapshot': row.snapshot, 'baseline_commit': row.baseline_commit,
               'baseline_path': row.baseline_path, 'lineage': int(row.lineage), 'flag': int(row.flag),
               'file_ploc': int(row.file_ploc), 'prior365_raw_changes': int(row.prior365_raw_changes),
               'following365_raw_changes': len(selected)}
        rec.update({category: counts[category] for category in CATEGORIES})
        all_files.append(rec)
    print(repo, 'eligible God Class file observations', len(sub), flush=True)

files = pd.DataFrame(all_files)
models = []
support = []
descriptive = []
selected_outcomes = []
for repo in REPOS:
    f = files[files.repository == repo].copy()
    chosen = overlap(f)
    chosen['logsize'] = np.log1p(chosen.file_ploc)
    chosen['logprior'] = np.log1p(chosen.prior365_raw_changes)
    X = design(chosen)
    if np.linalg.matrix_rank(X.to_numpy()) != X.shape[1]:
        raise ValueError('Rank-deficient design')
    if not (chosen[list(CATEGORIES)].sum(axis=1) == chosen.following365_raw_changes).all():
        raise ValueError('Category partition mismatch')
    expected_n = 1070 if repo == 'jenkinsci__jenkins' else 4297
    expected_flagged = 412 if repo == 'jenkinsci__jenkins' else 1054
    if len(chosen) != expected_n or int(chosen.flag.sum()) != expected_flagged:
        raise ValueError('Comparison cohort differs from archived God Class cohort')
    support.append({'repository': repo, 'eligible_rows': len(f), 'comparison_rows': len(chosen),
                    'flagged_rows': int(chosen.flag.sum()), 'years': int(chosen.snapshot.nunique()),
                    'lineages': int(chosen.lineage.nunique())})
    for flag, g in chosen.groupby('flag'):
        record = {'repository': repo, 'flag': int(flag), 'comparison_rows': len(g),
                  'total_file_events': int(g.following365_raw_changes.sum())}
        record.update({category: int(g[category].sum()) for category in CATEGORIES})
        descriptive.append(record)
    all_models = [model(chosen, X, name) for name in ('following365_raw_changes', *CATEGORIES)]
    for m in all_models:
        m['repository'] = repo
        models.append(m)
    archived = next(r for r in json.loads(ARCHIVED_MODELS.read_text())
                    if r['repository'] == repo and r['rule'] == 'GodClass' and r['endpoint'] == 'count')
    if abs(all_models[0]['ratio']-archived['effect']) > 1e-8:
        raise ValueError('Total-change ratio does not reproduce original model')
    selected_outcomes.extend(chosen.drop(columns=['logsize', 'logprior']).to_dict('records'))
    keys = set(zip(chosen.snapshot, chosen.baseline_path, chosen.lineage))
    selected_event_audit.extend(r for r in all_event_audit if r['repository'] == repo and
                                (r['snapshot'], r['baseline_path'], r['lineage']) in keys)
    print(repo, 'total ratio', all_models[0]['ratio'], 'category fits',
          sum(m['status'] == 'fitted' for m in all_models[1:]), flush=True)

# Keep a file-observation-level audit of all category outcomes, including excluded observations.
fields = ['repository', 'snapshot', 'baseline_commit', 'baseline_path', 'lineage', 'flag',
          'file_ploc', 'prior365_raw_changes', 'following365_raw_changes', *CATEGORIES]
write('file-category-counts.csv', all_files, fields)
write('comparison-file-counts.csv', selected_outcomes, fields)
write('comparison-event-audit.csv', selected_event_audit,
      ['repository', 'snapshot', 'baseline_path', 'lineage', 'flag', 'seq', 'commit', 'category'])
write('commit-categories.csv', sorted(commit_audit, key=lambda r:(r['repository'], r['seq'])),
      ['repository', 'seq', 'commit', 'timestamp', 'subject', 'classification_title',
       'title_source', 'category', 'matching_cues'])
valid = [m for m in models if m['category'] != 'following365_raw_changes' and m.get('p_value') is not None]
if valid:
    for m, p in zip(valid, multipletests([m['p_value'] for m in valid], method='holm')[1]):
        m['holm_p_value'] = float(p)
dump('models.json', models)
dump('support.json', support)
dump('descriptive.json', descriptive)
dump('provenance.json', input_hashes)
dump('SHA256SUMS.json', {p.name: sha(p) for p in sorted(OUT.iterdir()) if p.is_file()})
