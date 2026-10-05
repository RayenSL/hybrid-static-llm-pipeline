"""P1: recurrence of the repaired anti-pattern in the R branch (protocol v0.3, Section 7.3). No model calls.

Usage: python recurrence.py --manifest DIR --run DIR --repairs DIR --clone CLONE --out p1.json
"""
import argparse
import json
import subprocess
from pathlib import Path

import replay_core as core

REPO = Path(__file__).resolve().parents[3]
SOLUTION = 'Ibis.Calculeren/IbisCalculeren.sln'


def in_file(finding, path):
    return 'Ibis.Calculeren/' + finding['filePath'].replace('\\', '/') == path


def new_same_type(findings, path, anti_pattern, baseline):
    return {f['symbolName'] for f in findings if f['type'] == anti_pattern and in_file(f, path)} - baseline


def observation(new_per_step, completed):
    """(time, recurred): the first completed step with a new same-type finding, else censored at the last completed step."""
    for step, new in enumerate(new_per_step[:completed], 1):
        if new:
            return step, True
    return completed, False


def scan(clone, commit, path, state_text, output):
    subprocess.run(['git', '-C', str(clone), 'checkout', '-f', '-q', commit], check=True)
    (clone / path).write_bytes(state_text.encode('utf-8'))
    subprocess.run(['dotnet', 'run', '--project', str(REPO / 'src/HybridLens.CLI'), '--', 'analyse', '--target', str(clone / SOLUTION),
                    '--dry-run', '--format', 'json', '--severity', 'Warning', '--output', str(output)], capture_output=True)
    if not output.exists():
        raise RuntimeError(f'Detector produced no output for {commit}')
    return json.loads(output.read_text(encoding='utf-8-sig'))['findings']


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--repairs', type=Path, required=True)
    p.add_argument('--clone', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    manifest = json.loads((a.manifest / 'manifest.json').read_text(encoding='utf-8'))
    acquisition = {r['target_id']: r for r in json.loads((a.repairs / 'acquisition.json').read_text(encoding='utf-8'))}
    rows, observations = [], []
    scans = a.out.parent / 'p1-scans'
    scans.mkdir(parents=True, exist_ok=True)
    for target in manifest['targets']:
        tid, path = target['target_id'], target['path']
        accepted = acquisition.get(tid, {}).get('accepted_run')
        if target['role'] != 'validation' or accepted is None:
            continue
        baseline_scan = json.loads((a.repairs / tid / f'scan-run{accepted}.json').read_text(encoding='utf-8-sig'))['findings']
        same = {f['symbolName'] for f in baseline_scan if f['type'] == target['type'] and in_file(f, path)}
        other_type = 'longMethod' if target['type'] == 'godClass' else 'godClass'
        cross_baseline = {f['symbolName'] for f in baseline_scan if f['type'] == other_type and in_file(f, path)}
        new_per_step, cross_per_step = [], []
        for step in target['steps']:
            state = a.run / tid / 'R1' / f"S{step['step']}" / 'state.cs'
            if not state.exists():
                break
            findings = scan(a.clone, step['commit'], path, core.decode_source(state.read_bytes()), scans / f"{tid}-S{step['step']}.json")
            new_per_step.append(sorted(new_same_type(findings, path, target['type'], same)))
            cross_per_step.append(sorted(new_same_type(findings, path, other_type, cross_baseline)))
        time, recurred = observation([set(s) for s in new_per_step], len(new_per_step))
        observations.append((time, recurred))
        rows.append(dict(target_id=tid, type=target['type'], band=target['band'], completed=len(new_per_step), time=time,
                         recurred=recurred, new_same_type=new_per_step, new_cross_type=cross_per_step))
    horizon = max((t['k'] for t in manifest['targets']), default=0)
    completed_all = [r for r in rows if r['completed'] == next(t['k'] for t in manifest['targets'] if t['target_id'] == r['target_id'])]
    recurred_all = sum(r['recurred'] for r in completed_all)
    report = dict(kaplan_meier_recurrence=core.kaplan_meier_recurrence(observations, horizon) if observations else {},
                  crude=dict(recurred=recurred_all, completed_window=len(completed_all),
                             clopper_pearson_95=core.clopper_pearson(recurred_all, len(completed_all)) if completed_all else None),
                  targets=rows)
    a.out.write_text(json.dumps(report, indent=1), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'targets'}, indent=1))


if __name__ == '__main__':
    main()
