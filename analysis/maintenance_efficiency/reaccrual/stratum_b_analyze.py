"""Stratum-B replication of H2 and P1 (protocol v0.3, Sections 7.3, 7.4 and 8.1). No model calls.

Usage: python stratum_b_analyze.py --run DIR --out report.json
H2 is reported as a replication with its own interval, outside the confirmatory family.
"""
import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import replay_core as core
from recurrence import observation
from replay_analyze import SESOI, file_metrics, h2_difference, summarise

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = HERE.parents[2]
CORPUS = ROOT.parent / 'repair_design_quality/generated/baseline/corpus'
STEPS = 4


def target_type(target_id):
    return 'godClass' if target_id.startswith('GC') else 'longMethod'


def symbols(findings, path, anti_pattern):
    return {f['symbolName'] for f in findings if f['type'] == anti_pattern and f['filePath'].replace('\\', '/') == path}


def scan(path, text, output):
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copytree(CORPUS, tmp, dirs_exist_ok=True, ignore=shutil.ignore_patterns('bin', 'obj'))
        (Path(tmp) / path).write_bytes(text.encode('utf-8'))
        subprocess.run(['dotnet', 'run', '--project', str(REPO / 'src/HybridLens.CLI'), '--', 'analyse', '--target', str(Path(tmp) / 'Corpus.sln'),
                        '--dry-run', '--format', 'json', '--severity', 'Warning', '--output', str(output)], capture_output=True)
    if not output.exists():
        raise RuntimeError(f'Detector produced no output for {output.name}')
    return json.loads(output.read_text(encoding='utf-8-sig'))['findings']


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    pairs = {x['target_id']: x for x in json.loads((ROOT / 'generated' / 'campaign.json').read_text(encoding='utf-8'))['pairs']}
    scans = a.out.parent / f'{a.out.stem}-scans'
    scans.mkdir(parents=True, exist_ok=True)
    per_target, h2_values, observations, rows = {}, [], [], []
    for folder in sorted(p for p in a.run.iterdir() if (p / 'complete.json').exists()):
        tid, pair = folder.name, pairs[folder.name]
        path, kind = pair['relative_file'], target_type(tid)
        texts = {'O1_0': core.decode_source((ROOT / pair['baseline_path']).resolve().read_bytes()),
                 'R1_0': core.decode_source((ROOT / pair['repaired_path']).resolve().read_bytes())}
        for branch in ('O1', 'R1'):
            for k in range(1, STEPS + 1):
                state = folder / branch / f'S{k}' / 'state.cs'
                if not state.exists():
                    break
                texts[f'{branch}_{k}'] = core.decode_source(state.read_bytes())
        metrics = file_metrics(texts)
        series = {}
        for key in sorted(metrics, key=lambda k: (k.rsplit('_', 1)[0], int(k.rsplit('_', 1)[1]))):
            entry = series.setdefault(key.rsplit('_', 1)[0], dict(tokens=[], decisions=[]))
            entry['tokens'].append(metrics[key]['tokens'])
            entry['decisions'].append(metrics[key]['decision_burden'])
        h2 = h2_difference(series)
        h2_values.append(h2)
        completed_r = len(series['R1']['decisions']) - 1
        baseline = scan(path, texts['R1_0'], scans / f'{tid}-R1-S0.json')
        other = 'longMethod' if kind == 'godClass' else 'godClass'
        same, cross = symbols(baseline, path, kind), symbols(baseline, path, other)
        new_per_step, cross_per_step = [], []
        for k in range(1, completed_r + 1):
            findings = scan(path, texts[f'R1_{k}'], scans / f'{tid}-R1-S{k}.json')
            new_per_step.append(sorted(symbols(findings, path, kind) - same))
            cross_per_step.append(sorted(symbols(findings, path, other) - cross))
        time, recurred = observation([set(s) for s in new_per_step], completed_r)
        observations.append((time, recurred))
        rows.append(dict(target_id=tid, type=kind, completed=completed_r, time=time, recurred=recurred,
                         new_same_type=new_per_step, new_cross_type=cross_per_step, baseline_same_type=sorted(same)))
        per_target[tid] = dict(series=series, H2=h2, completed=dict(O1=len(series['O1']['decisions']) - 1, R1=completed_r))
        print(tid, json.dumps(dict(H2=h2, completed=per_target[tid]['completed'], recurred=recurred)), flush=True)
    full = [r for r in rows if r['completed'] == STEPS]
    recurred_full = sum(r['recurred'] for r in full)
    report = dict(H2_replication=summarise(h2_values, SESOI['H2']),
                  P1=dict(kaplan_meier_recurrence=core.kaplan_meier_recurrence(observations, STEPS) if observations else {},
                          crude=dict(recurred=recurred_full, completed_window=len(full),
                                     clopper_pearson_95=core.clopper_pearson(recurred_full, len(full)) if full else None),
                          targets=rows),
                  per_target=per_target)
    a.out.write_text(json.dumps(report, indent=1), encoding='utf-8')
    print(json.dumps(dict(H2_replication=report['H2_replication'], P1_crude=report['P1']['crude']), indent=1))


if __name__ == '__main__':
    main()
