"""Protocol v0.4 analysis: H3 and H4, secondary endpoints, threshold-gaming checks and sensitivity analyses. No model calls.

Usage: python v04_analyze.py --run DIR --out FILE
R-L scans written during the run are reused; other states are scanned here (CLI analyser, v0.3 configuration).
"""
import argparse
import json
from pathlib import Path

import replay_core as core
from replay_analyze import file_metrics
from stratum_b_analyze import ROOT, scan, target_type
from v04_run import ARMS, new_findings

SESOI = 0.5
STEPS = 4
NEAR_CALLABLE = (8, 10)
NEAR_CLASS = (40, 46)


def summary(values, sesoi):
    used = [v for v in values if v is not None]
    result = dict(targets=len(used), without_completed_steps=len(values) - len(used))
    if len(used) >= 2:
        low, high = core.t_interval(used, 0.95)
        low90, high90 = core.t_interval(used, 0.90)
        result.update(mean=sum(used) / len(used), ci95=[low, high], ci90=[low90, high90], p_one_sided=core.sign_flip_greater(used),
                      sesoi=sesoi, equivalent=bool(-sesoi < low90 and high90 < sesoi))
    return result


def confirmatory(differences):
    report = {name: summary(values, SESOI) for name, values in differences.items()}
    names = [n for n in ('H3', 'H4') if 'p_one_sided' in report[n]]
    for name, adjusted in zip(names, core.holm([report[n]['p_one_sided'] for n in names])):
        report[name]['p_holm'] = adjusted
        report[name]['supported'] = bool(adjusted < 0.05 and report[name]['ci95'][0] > 0)
    return report


def near_threshold_share(values, low, high):
    values = list(values.values()) if isinstance(values, dict) else list(values)
    return sum(low <= v <= high for v in values) / len(values) if values else None


def gaming_verdict(accrual_ci90_upper, near_threshold_increase):
    return 'debt_prevention' if accrual_ci90_upper < 1 and near_threshold_increase <= 0.10 else 'metric_suppression'


def load_target(folder, pair, scans):
    path = pair['relative_file']
    starts = {'original': (ROOT / pair['baseline_path']).resolve(), 'repair': (ROOT / pair['repaired_path']).resolve()}
    texts, found, calls = {}, {}, {}
    for arm in ARMS:
        texts[arm, 0] = core.decode_source(starts[ARMS[arm]['start']].read_bytes())
        calls[arm] = dict(main=0, quality=0, retried=False, triggered=0, accepted=0)
        for k in range(1, STEPS + 1):
            step = folder / arm / f'S{k}'
            if (step / 'result.json').exists():
                result = json.loads((step / 'result.json').read_text(encoding='utf-8'))
                calls[arm]['main'] += sum((c.get('input_tokens') or 0) + (c.get('output_tokens') or 0) for c in result.get('calls', []))
                calls[arm]['retried'] |= len(result.get('calls', [])) > 1
                quality = result.get('quality') or {}
                calls[arm]['triggered'] += bool(quality.get('triggered'))
                calls[arm]['accepted'] += bool(quality.get('accepted'))
                call = quality.get('call') or {}
                calls[arm]['quality'] += (call.get('input_tokens') or 0) + (call.get('output_tokens') or 0)
            if not (step / 'state.cs').exists():
                break
            texts[arm, k] = core.decode_source((step / 'state.cs').read_bytes())
    for (arm, k), text in texts.items():
        saved = folder / f'{arm}-S0-scan.json' if k == 0 else folder / arm / f'S{k}' / ('scan-after-quality.json' if (folder / arm / f'S{k}' / 'scan-after-quality.json').exists() else 'scan.json')
        if not saved.exists():
            saved = scans / f'{folder.name}-{arm}-S{k}.json'
            if not saved.exists():
                scan(path, text, saved)
        found[arm, k] = json.loads(saved.read_text(encoding='utf-8-sig'))['findings']
    metrics = file_metrics({f'{arm}_{k}': text for (arm, k), text in texts.items()})
    completed = {arm: max(k for a, k in texts if a == arm) for arm in ARMS}
    return path, texts, found, metrics, completed, calls


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    pairs = {x['target_id']: x for x in json.loads((ROOT / 'generated' / 'campaign.json').read_text(encoding='utf-8'))['pairs']}
    scans = a.out.parent / f'{a.out.stem}-scans'
    scans.mkdir(parents=True, exist_ok=True)
    rows = []
    for folder in sorted(f for f in a.run.iterdir() if (f / 'complete.json').exists()):
        tid = folder.name
        path, texts, found, metrics, completed, calls = load_target(folder, pairs[tid], scans)
        kind = target_type(tid)

        def n_new(arm, j):
            return len(new_findings(found[arm, 0], found[arm, j], path))

        def accrual(arm, j, key):
            series = [metrics[f'{arm}_{k}'][key] for k in range(0, j + 1)]
            return core.accrual(series, j)

        def paired(x, y, fn):
            j = min(completed[x], completed[y])
            return None if j < 1 else fn(x, j) - fn(y, j)

        row = dict(target_id=tid, type=kind, completed=completed, calls=calls,
                   H3=paired('R-N', 'R-L', n_new), H4=paired('R-N', 'R-D', n_new),
                   new_findings={arm: n_new(arm, completed[arm]) for arm in ARMS},
                   replication_N=paired('R-N', 'O-N', n_new),
                   replication_A=paired('O-N', 'R-N', lambda arm, j: accrual(arm, j, 'decision_burden')),
                   A_RL_minus_RN=paired('R-L', 'R-N', lambda arm, j: accrual(arm, j, 'decision_burden')),
                   A_RD_minus_RN=paired('R-D', 'R-N', lambda arm, j: accrual(arm, j, 'decision_burden')),
                   V_RL_minus_RN=paired('R-L', 'R-N', lambda arm, j: accrual(arm, j, 'tokens')),
                   V_RD_minus_RN=paired('R-D', 'R-N', lambda arm, j: accrual(arm, j, 'tokens')))
        recurrence = {}
        for arm in ('R-N', 'R-D', 'R-L'):
            first = next((k for k in range(1, completed[arm] + 1)
                          if any(f['type'] == kind for f in new_findings(found[arm, 0], found[arm, k], path))), None)
            recurrence[arm] = dict(time=first or completed[arm], recurred=first is not None, completed=completed[arm])
        row['recurrence'] = recurrence
        # R-L and R-N share the gaming check's prefix; R-D can stop earlier, so its descriptive share uses its own prefix with R-N.
        prefix = {'R-N': min(completed['R-L'], completed['R-N']), 'R-L': min(completed['R-L'], completed['R-N']),
                  'R-D': min(completed['R-D'], completed['R-N'])}
        near = {arm: dict(callable=near_threshold_share(metrics[f'{arm}_{j}']['callables'], *NEAR_CALLABLE),
                          klass=near_threshold_share(metrics[f'{arm}_{j}']['class_wmc'], *NEAR_CLASS)) for arm, j in prefix.items()}
        row['near_threshold'] = near
        row['max_callable'] = {arm: metrics[f'{arm}_{completed[arm]}']['max_callable_complexity'] for arm in ARMS}
        rows.append(row)
        print(json.dumps({k: row[k] for k in ('target_id', 'H3', 'H4', 'new_findings', 'completed')}), flush=True)

    def collect(key, keep=lambda r: True):
        return [r[key] for r in rows if keep(r)]

    report = dict(confirmatory=confirmatory({'H3': collect('H3'), 'H4': collect('H4')}))
    report['secondary'] = dict(
        new_findings_per_arm={arm: dict(mean=sum(r['new_findings'][arm] for r in rows) / len(rows),
                                        targets_with_new=sum(r['new_findings'][arm] > 0 for r in rows)) for arm in ARMS},
        recurrence={arm: dict(recurred=sum(r['recurrence'][arm]['recurred'] for r in rows if r['type'] == 'longMethod'),
                              long_method_targets=sum(1 for r in rows if r['type'] == 'longMethod')) for arm in ('R-N', 'R-D', 'R-L')},
        completion={arm: sum(r['completed'][arm] for r in rows) / (STEPS * len(rows)) for arm in ARMS},
        tokens_per_completed_step={arm: (sum(r['calls'][arm]['main'] + r['calls'][arm]['quality'] for r in rows)
                                         / max(1, sum(r['completed'][arm] for r in rows))) for arm in ARMS},
        loop=dict(triggers=sum(r['calls']['R-L']['triggered'] for r in rows), accepted=sum(r['calls']['R-L']['accepted'] for r in rows),
                  quality_tokens=sum(r['calls']['R-L']['quality'] for r in rows)),
        A_RL_minus_RN=summary(collect('A_RL_minus_RN'), 1), A_RD_minus_RN=summary(collect('A_RD_minus_RN'), 1),
        V_RL_minus_RN=summary(collect('V_RL_minus_RN'), 25), V_RD_minus_RN=summary(collect('V_RD_minus_RN'), 25),
        replication=dict(N_RN_minus_ON=summary(collect('replication_N'), 1), A_ON_minus_RN=summary(collect('replication_A'), 1)))
    shares = [(r['near_threshold']['R-L']['callable'], r['near_threshold']['R-N']['callable']) for r in rows
              if r['near_threshold']['R-L']['callable'] is not None and r['near_threshold']['R-N']['callable'] is not None]
    increase = sum(x - y for x, y in shares) / len(shares) if shares else 0.0
    class_shares = [(r['near_threshold']['R-L']['klass'], r['near_threshold']['R-N']['klass']) for r in rows
                    if r['near_threshold']['R-L']['klass'] is not None and r['near_threshold']['R-N']['klass'] is not None]
    accrual_upper = report['secondary']['A_RL_minus_RN'].get('ci90', [0, 0])[1]
    report['threshold_gaming'] = dict(near_threshold_callable_increase_RL_vs_RN=increase,
                                      near_threshold_class_increase_RL_vs_RN=(sum(x - y for x, y in class_shares) / len(class_shares)) if class_shares else None,
                                      A_RL_minus_RN_ci90_upper=accrual_upper, H3_reading=gaming_verdict(accrual_upper, increase))
    retried = {r['target_id'] for r in rows if any(r['calls'][arm]['retried'] for arm in ARMS)}
    full = {r['target_id'] for r in rows if all(r['completed'][arm] == STEPS for arm in ARMS)}
    report['sensitivity'] = {
        '1_without_GC-03': confirmatory({h: collect(h, lambda r: r['target_id'] != 'GC-03') for h in ('H3', 'H4')}),
        '2_without_GC-12_LM-13': confirmatory({h: collect(h, lambda r: r['target_id'] not in ('GC-12', 'LM-13')) for h in ('H3', 'H4')}),
        '3_by_type': {kind: confirmatory({h: collect(h, lambda r, kind=kind: r['type'] == kind) for h in ('H3', 'H4')}) for kind in ('godClass', 'longMethod')},
        '4_without_retried': dict(excluded=sorted(retried), **confirmatory({h: collect(h, lambda r: r['target_id'] not in retried) for h in ('H3', 'H4')})),
        '5_step_4_all_arms_complete': dict(targets=sorted(full), **confirmatory({h: collect(h, lambda r: r['target_id'] in full) for h in ('H3', 'H4')})),
    }
    report['targets'] = rows
    a.out.write_text(json.dumps(report, indent=1), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('targets', 'sensitivity')}, indent=1))


if __name__ == '__main__':
    main()
