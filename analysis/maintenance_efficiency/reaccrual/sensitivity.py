"""Pre-specified sensitivity analyses (protocol v0.3, Section 8.3, and Deviation 1). No model calls.

Usage: python sensitivity.py --manifest DIR --run-a DIR --report-a FILE --p1-a FILE --run-b DIR --report-b FILE --out FILE
"""
import argparse
import json
from pathlib import Path

import replay_core as core
from replay_analyze import SESOI, confirmatory, file_metrics, h1_difference, h2_difference, summarise
from stratum_b_analyze import target_type

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PRIOR_KNOWLEDGE = ('GC-12', 'LM-13')
INVALID_STEPS = {('T18', 2), ('T19', 2)}


def retried(results):
    return any(len(r.get('calls', [])) > 1 for r in results)


def h2_full_prefix(series):
    if 'O1' not in series or 'R1' not in series:
        return None
    o, r = series['O1']['decisions'], series['R1']['decisions']
    if len(o) < 2 or len(r) < 2:
        return None
    return core.accrual(o, len(o) - 1) - core.accrual(r, len(r) - 1)


def impute(values, case):
    observed = [v for v in values if v is not None]
    fill = max(observed) if case == 'best' else min(observed)
    return [fill if v is None else v for v in values]


def p1_bounds(rows):
    recurred = sum(r['recurred'] for r in rows)
    return dict(best=dict(recurred=recurred, n=len(rows)),
                worst=dict(recurred=recurred + sum(r['censored'] and not r['recurred'] for r in rows), n=len(rows)))


def grew(before, after, symbol):
    key = '.'.join(symbol.split('.')[-2:])
    return after.get(key, 0) > before.get(key, 0)


def results_of(run, tid):
    return [json.loads(p.read_text(encoding='utf-8')) for p in (run / tid).glob('*/S*/result.json')]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--run-a', type=Path, required=True)
    p.add_argument('--report-a', type=Path, required=True)
    p.add_argument('--p1-a', type=Path, required=True)
    p.add_argument('--run-b', type=Path, required=True)
    p.add_argument('--report-b', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    manifest = json.loads((a.manifest / 'manifest.json').read_text(encoding='utf-8'))
    report_a = json.loads(a.report_a.read_text(encoding='utf-8'))
    p1_a = json.loads(a.p1_a.read_text(encoding='utf-8'))
    report_b = json.loads(a.report_b.read_text(encoding='utf-8'))
    series_a = {tid: row['series'] for tid, row in report_a['per_target'].items()}
    series_b = {tid: row['series'] for tid, row in report_b['per_target'].items()}
    out = {}

    # 1. Exclude targets where any step needed the retry call.
    retried_a = sorted(t for t in series_a if retried(results_of(a.run_a, t)))
    retried_b = sorted(t for t in series_b if retried(results_of(a.run_b, t)))
    kept_a = [t for t in series_a if t not in retried_a]
    out['1_exclude_retried'] = dict(
        retried_a=retried_a, retried_b=retried_b,
        stratum_a=confirmatory({'H1': [h1_difference(series_a[t], 'tokens') for t in kept_a],
                                'H2': [h2_difference(series_a[t]) for t in kept_a]}),
        stratum_b_H2=summarise([h2_difference(series_b[t]) for t in series_b if t not in retried_b], SESOI['H2']))

    # 2. Stratum B without the targets with prior detailed knowledge of the repairs.
    rows_b = report_b['P1']['targets']
    kept_rows = [r for r in rows_b if r['target_id'] not in PRIOR_KNOWLEDGE]
    full = [r for r in kept_rows if r['completed'] == 4]
    recurred = sum(r['recurred'] for r in full)
    out['2_stratum_b_without_GC-12_LM-13'] = dict(
        H2=summarise([h2_difference(series_b[t]) for t in series_b if t not in PRIOR_KNOWLEDGE], SESOI['H2']),
        P1=dict(recurred=recurred, completed_window=len(full), clopper_pearson_95=core.clopper_pearson(recurred, len(full))))

    # 3. Clear-cut versus borderline. Stratum A has only clear-cut validation targets.
    # Stratum-B bands come from the census findings that selected the targets; the CLI analyser does not flag GC-03 at all.
    pairs = {x['target_id']: x for x in json.loads((ROOT / 'generated' / 'campaign.json').read_text(encoding='utf-8'))['pairs']}
    census = json.loads((ROOT.parent / 'repair_design_quality/generated/structural-facts.jsonl').read_text(encoding='utf-8').splitlines()[0])
    bands = {}
    for tid in series_b:
        kind, path = target_type(tid), pairs[tid]['relative_file']
        census_type = 'GodClass' if kind == 'godClass' else 'LongMethod'
        metrics = next(f['metrics'] for f in census['solution_findings_before'] if f['type'] == census_type and f['file'] == path)
        borderline = abs(metrics['WMC'] - 47) <= 4.7 if kind == 'godClass' else metrics['CyclomaticComplexity'] == 11
        bands[tid] = 'borderline' if borderline else 'clear_cut'
    out['3_band'] = dict(
        stratum_a='not estimable: all 13 validation targets are clear-cut',
        stratum_b_bands=bands,
        stratum_b={band: dict(H2=summarise([h2_difference(series_b[t]) for t in series_b if bands[t] == band], SESOI['H2']),
                              P1_recurred=sum(r['recurred'] for r in rows_b if bands[r['target_id']] == band),
                              P1_n=sum(1 for r in rows_b if bands[r['target_id']] == band))
                   for band in sorted(set(bands.values()))})

    # 4. P1 counting only recurrences whose symbol owns more decisions than at step 0 (excludes pure relocation).
    grown = []
    for r in rows_b:
        if not r['recurred']:
            continue
        tid, step = r['target_id'], r['time']
        pair = pairs[tid]
        texts = {'R0': core.decode_source((ROOT / pair['repaired_path']).resolve().read_bytes()),
                 'Rk': core.decode_source((a.run_b / tid / 'R1' / f'S{step}' / 'state.cs').read_bytes())}
        metrics = file_metrics(texts)
        symbol = r['new_same_type'][step - 1][0]
        grown.append(dict(target_id=tid, step=step, symbol=symbol, before=metrics['R0']['callables'].get('.'.join(symbol.split('.')[-2:])),
                          after=metrics['Rk']['callables'].get('.'.join(symbol.split('.')[-2:])),
                          counted=grew(metrics['R0']['callables'], metrics['Rk']['callables'], symbol)))
    counted = sum(g['counted'] for g in grown)
    out['4_p1_growth_only'] = dict(stratum_a='no recurrence observed', stratum_b=dict(
        recurrences=grown, recurred=counted, completed_window=sum(1 for r in rows_b if r['completed'] == 4),
        clopper_pearson_95=core.clopper_pearson(counted, sum(1 for r in rows_b if r['completed'] == 4))))

    # 5. Censored or instrument-failed branches as best and as worst case (includes Deviation 1).
    censored_a = [dict(target_id=r['target_id'], recurred=r['recurred'],
                       censored=r['completed'] < next(t['k'] for t in manifest['targets'] if t['target_id'] == r['target_id']))
                  for r in p1_a['targets']]
    censored_b = [dict(target_id=r['target_id'], recurred=r['recurred'], censored=r['completed'] < 4) for r in rows_b]
    h1 = [h1_difference(series_a[t], 'tokens') for t in series_a]
    h2_b = [h2_difference(series_b[t]) for t in series_b]
    steps = [(t['target_id'], s['step']) for t in manifest['targets'] if t['target_id'] in series_a for s in t['steps']]
    completion = {}
    for case, invalid_is_failure in (('invalid_steps_censored', False), ('invalid_steps_as_failures', True)):
        done = total = 0
        for tid in series_a:
            for branch, s in series_a[tid].items():
                if branch == 'H':
                    continue
                valid = [n for t, n in steps if t == tid and (invalid_is_failure or (t, n) not in INVALID_STEPS)]
                done += min(len(s['tokens']) - 1, len(valid))
                total += len(valid)
        completion[case] = dict(completed_steps=done, attempted_steps=total, rate=done / total)
    out['5_best_worst'] = dict(
        P1_stratum_a=dict(censored=[r['target_id'] for r in censored_a if r['censored']], **p1_bounds(censored_a)),
        P1_stratum_b=dict(censored=[r['target_id'] for r in censored_b if r['censored']], **p1_bounds(censored_b)),
        H1_stratum_a={case: summarise(impute(h1, case), SESOI['H1']) for case in ('best', 'worst')},
        H2_stratum_b={case: summarise(impute(h2_b, case), SESOI['H2']) for case in ('best', 'worst')},
        step_completion_stratum_a=completion)

    # 6. H2 on each branch's full completed prefix (unpaired in steps).
    out['6_h2_full_prefix'] = dict(stratum_a=summarise([h2_full_prefix(series_a[t]) for t in series_a], SESOI['H2']),
                                   stratum_b=summarise([h2_full_prefix(series_b[t]) for t in series_b], SESOI['H2']))

    # 7. Prompts carried commit messages only; no linked work-item text was ever retrieved, so every commit qualifies.
    out['7_work_item_text'] = 'not applicable: no work-item text was used in any prompt; the analysis equals the main analysis'
    a.out.write_text(json.dumps(out, indent=1), encoding='utf-8')
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
