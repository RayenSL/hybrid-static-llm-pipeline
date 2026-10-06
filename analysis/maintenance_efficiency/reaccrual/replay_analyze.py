"""Measure replay branch states and compute the confirmatory contrasts (protocol v0.3, Sections 7.4 and 8.1).

Usage: python replay_analyze.py --manifest DIR --run DIR --repo REPO [--repairs DIR] --out report.json
"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import replay_core as core

REPO_ROOT = Path(__file__).resolve().parents[3]
METRICS_TOOL = REPO_ROOT / 'src/HybridLens.DesignQuality/bin/Debug/net10.0/HybridLens.DesignQuality.dll'
O_TRAJECTORIES = ('O1', 'O2', 'O3')


def h1_difference(series, metric):
    """Mean over agent trajectories with j >= 1 of the per-change accrual difference against the developers at the same j."""
    differences = []
    for name in O_TRAJECTORIES:
        trajectory = series.get(name)
        if not trajectory:
            continue
        j = len(trajectory[metric]) - 1
        if j >= 1:
            differences.append(core.accrual(trajectory[metric], j) - core.accrual(series['H'][metric], j))
    return sum(differences) / len(differences) if differences else None


def h2_difference(series):
    """A_O - A_R in decision burden, O trajectory 1 against the repaired trajectory on their common completed prefix."""
    if 'O1' not in series or 'R1' not in series:
        return None
    j = min(len(series['O1']['decisions']), len(series['R1']['decisions'])) - 1
    if j < 1:
        return None
    return core.accrual(series['O1']['decisions'], j) - core.accrual(series['R1']['decisions'], j)


SESOI = {'H1': 25, 'H1b': 1, 'H2': 1}


def summarise(values, sesoi):
    used = [v for v in values if v is not None]
    result = dict(targets=len(used), without_completed_steps=len(values) - len(used))
    if len(used) >= 2:
        low, high = core.t_interval(used, 0.95)
        low90, high90 = core.t_interval(used, 0.90)
        result.update(mean=sum(used) / len(used), ci95=[low, high], p_one_sided=core.sign_flip_greater(used),
                      ci90=[low90, high90], sesoi=sesoi, equivalent=bool(-sesoi < low90 and high90 < sesoi))
    return result


def confirmatory(differences):
    """differences: {'H1': [...], 'H2': [...]} per validation target, oriented so that the hypothesis predicts > 0."""
    report = {name: summarise(values, SESOI[name]) for name, values in differences.items()}
    names = [n for n in ('H1', 'H2') if 'p_one_sided' in report.get(n, {})]
    for name, adjusted in zip(names, core.holm([report[n]['p_one_sided'] for n in names])):
        report[name]['p_holm'] = adjusted
        report[name]['supported'] = adjusted < 0.05 and report[name]['ci95'][0] > 0
    return report


def file_metrics(texts):
    with tempfile.TemporaryDirectory() as tmp:
        for key, text in texts.items():
            Path(tmp, f'{key}.cs').write_text(text, encoding='utf-8')
        output = subprocess.run(['dotnet', str(METRICS_TOOL), '--file-metrics', tmp], capture_output=True, text=True, check=True).stdout
    return json.loads(output)


def git_show(repo, revision, path):
    data = subprocess.run(['git', '-C', str(repo), 'show', f'{revision}:{path}'], capture_output=True, check=True).stdout
    return core.decode_source(data)


def branch_series(manifest_target, run_dir, repo, repairs):
    """Metric series per branch: state 0 then each completed step's state."""
    tid, path = manifest_target['target_id'], manifest_target['path']
    texts = {'H_0': git_show(repo, manifest_target['t0'], path)}
    for step in manifest_target['steps']:
        texts[f"H_{step['step']}"] = git_show(repo, step['commit'], path)
    for branch_dir in sorted(p for p in (run_dir / tid).iterdir() if p.is_dir()) if (run_dir / tid).exists() else []:
        name = branch_dir.name
        if name.startswith('R'):
            repaired = repairs / tid / 'repaired.cs' if repairs else None
            if not repaired or not repaired.exists():
                continue
            texts[f'{name}_0'] = core.decode_source(repaired.read_bytes())
        else:
            texts[f'{name}_0'] = texts['H_0']
        for step in manifest_target['steps']:
            state = branch_dir / f"S{step['step']}" / 'state.cs'
            if not state.exists():
                break
            texts[f"{name}_{step['step']}"] = core.decode_source(state.read_bytes())
    metrics = file_metrics(texts)
    series = {}
    for key in sorted(metrics, key=lambda k: (k.rsplit('_', 1)[0], int(k.rsplit('_', 1)[1]))):
        name = key.rsplit('_', 1)[0]
        entry = series.setdefault(name, dict(tokens=[], decisions=[]))
        entry['tokens'].append(metrics[key]['tokens'])
        entry['decisions'].append(metrics[key]['decision_burden'])
    return series


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--repairs', type=Path)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    manifest = json.loads((a.manifest / 'manifest.json').read_text(encoding='utf-8'))
    per_target, differences = {}, {'H1': [], 'H1b': [], 'H2': []}
    for target in manifest['targets']:
        if target['role'] != 'validation' or not (a.run / target['target_id']).exists():
            continue
        series = branch_series(target, a.run, a.repo, a.repairs)
        row = dict(series=series, H1=h1_difference(series, 'tokens'), H1b=h1_difference(series, 'decisions'), H2=h2_difference(series))
        per_target[target['target_id']] = row
        for name in differences:
            differences[name].append(row[name])
    report = dict(confirmatory=confirmatory({'H1': differences['H1'], 'H2': differences['H2']}),
                  secondary=dict(H1b=summarise(differences['H1b'], SESOI['H1b'])), per_target=per_target)
    a.out.write_text(json.dumps(report, indent=1), encoding='utf-8')
    print(json.dumps(report['confirmatory'], indent=1))


if __name__ == '__main__':
    main()
