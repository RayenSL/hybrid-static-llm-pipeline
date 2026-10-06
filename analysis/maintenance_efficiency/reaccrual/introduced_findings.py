"""Secondary endpoint, Section 7.5: anti-pattern findings introduced into the target file, O versus R (stratum B). No model calls.

Usage: python introduced_findings.py --run DIR --scans DIR --out FILE
R-branch scans written by stratum_b_analyze.py are reused from --scans; O-branch states are scanned here.
Descriptive and two-sided: no direction was hypothesised for this endpoint.
"""
import argparse
import json
from pathlib import Path

import replay_core as core
from replay_analyze import summarise
from stratum_b_analyze import ROOT, scan

TYPES = ('godClass', 'longMethod')


def introduced(before, after, path):
    def keyed(findings):
        return {(f['type'], f['symbolName']) for f in findings if f['type'] in TYPES and f['filePath'].replace('\\', '/') == path}
    return keyed(after) - keyed(before)


def two_sided(differences):
    if not any(differences):
        return 1.0
    return min(1.0, 2 * min(core.sign_flip_greater(differences), core.sign_flip_greater([-d for d in differences])))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--scans', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    pairs = {x['target_id']: x for x in json.loads((ROOT / 'generated' / 'campaign.json').read_text(encoding='utf-8'))['pairs']}
    rows = []
    for folder in sorted(f for f in a.run.iterdir() if (f / 'complete.json').exists()):
        tid, pair = folder.name, pairs[folder.name]
        path = pair['relative_file']
        completed = {b: sum(1 for k in range(1, 5) if (folder / b / f'S{k}' / 'state.cs').exists()) for b in ('O1', 'R1')}
        j = min(completed.values())
        findings = {}
        for branch, start in (('O1', pair['baseline_path']), ('R1', pair['repaired_path'])):
            for k in (0, j):
                cached = a.scans / f'{tid}-{branch}-S{k}.json'
                if cached.exists():
                    findings[branch, k] = json.loads(cached.read_text(encoding='utf-8-sig'))['findings']
                    continue
                text = (ROOT / start).resolve().read_bytes() if k == 0 else (folder / branch / f'S{k}' / 'state.cs').read_bytes()
                findings[branch, k] = scan(path, core.decode_source(text), cached)
        new = {b: sorted(introduced(findings[b, 0], findings[b, j], path)) for b in ('O1', 'R1')}
        rows.append(dict(target_id=tid, steps_compared=j, introduced_O=new['O1'], introduced_R=new['R1'],
                         difference=len(new['R1']) - len(new['O1'])))
        print(json.dumps(rows[-1]), flush=True)
    differences = [r['difference'] for r in rows]
    report = dict(R_minus_O_new_findings=dict(summarise(differences, 1), p_two_sided=two_sided(differences)),
                  targets_with_new=dict(O=sum(bool(r['introduced_O']) for r in rows), R=sum(bool(r['introduced_R']) for r in rows), n=len(rows)),
                  discordant=dict(R_only=sum(bool(r['introduced_R']) and not r['introduced_O'] for r in rows),
                                  O_only=sum(bool(r['introduced_O']) and not r['introduced_R'] for r in rows)),
                  by_type={kind: dict(O=sum(any(t == kind for t, _ in r['introduced_O']) for r in rows),
                                      R=sum(any(t == kind for t, _ in r['introduced_R']) for r in rows)) for kind in TYPES},
                  targets=rows)
    a.out.write_text(json.dumps(report, indent=1), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'targets'}, indent=1))


if __name__ == '__main__':
    main()
