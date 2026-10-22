"""Protocol v0.5 analysis (Sections 7 and 8): primary interval, secondary test, gate flow, sensitivity analyses, gaming checks and the
review packet for R2. Makes no model calls. Output stays private: it names real files and methods.

Usage: python v05_analyze.py --manifest DIR --run DIR --introductions DIR --head-findings FILE --out DIR
"""
import argparse
import collections
import difflib
import json
import random
import statistics
from pathlib import Path

from scipy import stats

import introduction_audit as audit
import replay_core as core
from replay_analyze import file_metrics
from shadow_frame import rank

SEED = 'reaccrual-v0.5'
BOUND = 0.75
NEAR = (8, 10)


def edit_footprint(post, candidate):
    diff = [line for line in difflib.unified_diff(post.splitlines(), candidate.splitlines(), lineterm='', n=0)
            if not line.startswith(('---', '+++', '@@'))]
    return dict(added=sum(line.startswith('+') for line in diff), removed=sum(line.startswith('-') for line in diff))


def first_per_file(units, seed):
    best = {}
    for u in units:
        key = u['file'].lower()
        if key not in best or rank(seed, u['commit'], u['symbols'][0]) < rank(seed, best[key]['commit'], best[key]['symbols'][0]):
            best[key] = u
    return list(best.values())


def clustered_interval(by_file, reps=2000, seed=1):
    """Percentile bootstrap of the success proportion, resampling files (clusters) with replacement."""
    rng = random.Random(seed)
    files = list(by_file)
    values = []
    for _ in range(reps):
        picked = [rng.choice(files) for _ in files]
        outcomes = [x for f in picked for x in by_file[f]]
        values.append(sum(outcomes) / len(outcomes))
    values.sort()
    return values[int(0.025 * (reps - 1))], values[int(0.975 * (reps - 1))]


def complexity_profile(before, after, symbols):
    b, a = audit.by_symbol(before), audit.by_symbol(after)
    new = [m for s, m in a.items() if s not in b]
    return dict(before={s: b[s]['complexity'] for s in symbols if s in b}, after={s: a[s]['complexity'] for s in symbols if s in a},
                new_methods=len(new), new_max_complexity=max((m['complexity'] for m in new), default=None))


def near_threshold(methods):
    return sum(NEAR[0] <= m['complexity'] <= NEAR[1] for m in methods)


def proportion(pairs):
    k, n = sum(pairs), len(pairs)
    if n == 0:
        return dict(successes=0, n=0)
    lo, hi = core.clopper_pearson(k, n)
    return dict(successes=k, n=n, proportion=k / n, ci95=[lo, hi])


def band_of(stratum):
    return stratum.split('|')[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--introductions', type=Path, required=True)
    p.add_argument('--head-findings', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    ids = json.loads((a.manifest / 'manifest.json').read_text(encoding='utf-8'))['units']
    units = [json.loads((a.manifest / uid / 'unit.json').read_text(encoding='utf-8')) for uid in ids]
    commits = {}
    for line in (a.introductions / 'introductions.jsonl').read_text(encoding='utf-8').splitlines():
        record = json.loads(line)
        commits[record['commit']] = record
    findings = json.loads(a.head_findings.read_text(encoding='utf-8-sig'))
    head_long = {f['symbolName'] for f in (findings['findings'] if isinstance(findings, dict) else findings) if f['type'] == 'longMethod'}
    rows = []
    for u in units:
        if not u['eligible']:
            continue
        r = json.loads((a.run / u['unit_id'] / 'result.json').read_text(encoding='utf-8'))
        post = core.decode_source((a.manifest / u['unit_id'] / 'post.cs').read_bytes())
        candidate_path = a.run / u['unit_id'] / 'candidate.cs'
        candidate = core.decode_source(candidate_path.read_bytes()) if candidate_path.exists() else None
        record = commits[u['commit']]
        row = dict(u, success=r['success'], stage=r['stage'], attempts=r.get('attempts'), tokens=r['tokens'], calls=len(r['calls']), seconds=r['seconds'],
                   success_without_new_debt=r.get('success_without_new_debt'), gates=r.get('gates'), production_files=len(record['production_files']),
                   touches_tests=record['touches_tests'], first_call=bool(r['success'] and r.get('attempts') == 1),
                   persists_at_head=any(s in head_long for s in u['symbols']))
        if candidate is not None:
            facts = audit.measure({'post': post.encode('utf-8'), 'candidate': candidate.encode('utf-8')})
            metrics = file_metrics({'post': post, 'candidate': candidate})
            row.update(footprint=edit_footprint(post, candidate), profile=complexity_profile(facts['post']['methods'], facts['candidate']['methods'], u['reproduced']),
                       near_before=near_threshold(facts['post']['methods']), near_after=near_threshold(facts['candidate']['methods']),
                       decision_burden_delta=metrics['candidate']['decision_burden'] - metrics['post']['decision_burden'],
                       tokens_delta=metrics['candidate']['tokens'] - metrics['post']['tokens'])
        rows.append(row)

    def success(rs):
        return [r['success'] for r in rs]

    oracle = [r for r in rows if r['tests_applicable']]
    static_only = [r for r in rows if not r['tests_applicable']]
    primary = proportion(success(oracle))
    primary['reading'] = ('fixes usually work' if primary.get('ci95', [0])[0] > 0.5 else 'usually does not work' if primary.get('ci95', [0, 1])[1] < 0.5 else 'inconclusive')
    if len(oracle) >= 30:
        primary['secondary_test'] = dict(null=f'p <= {BOUND}', p_one_sided=float(stats.binom.sf(sum(success(oracle)) - 1, len(oracle), BOUND)))
    report = dict(primary_oracle_units=primary, static_only_units=proportion(success(static_only)), all_eligible=proportion(success(rows)))
    flow = collections.OrderedDict()
    alive = rows
    for gate in ('build', 'api', 'tests', 'resolved', 'no_new_debt'):
        alive = [r for r in alive if r['gates'] and r['gates'].get(gate)]
        flow[gate] = len(alive)
    report['gate_flow'] = dict(eligible=len(rows), **flow)
    report['by_stratum'] = {s: proportion(success([r for r in rows if r['stratum'] == s])) for s in sorted({r['stratum'] for r in rows})}
    report['by_layer'] = {s: proportion(success([r for r in rows if r['layer'] == s])) for s in sorted({r['layer'] for r in rows})}
    report['sensitivity'] = {
        '1_first_call_only': proportion([r['first_call'] for r in oracle]),
        '2_at_most_3_files': proportion(success([r for r in oracle if r['production_files'] <= 3])),
        '2_at_most_30_files': proportion(success([r for r in oracle if r['production_files'] <= 30])),
        '3_without_units_whose_commit_changed_tests': proportion(success([r for r in oracle if not r['touches_tests']])),
        '4_complexity_11': proportion(success([r for r in oracle if band_of(r['stratum']) == '11'])),
        '4_complexity_12_and_above': proportion(success([r for r in oracle if band_of(r['stratum']) != '11'])),
        '5_crossing': proportion(success([r for r in oracle if r['stratum'].startswith('crossing')])),
        '5_new_method': proportion(success([r for r in oracle if r['stratum'].startswith('new_method')])),
        '6_without_the_new_debt_gate': proportion([bool(r['success_without_new_debt']) for r in oracle]),
    }
    one = first_per_file(oracle, SEED)
    by_file = collections.defaultdict(list)
    for r in oracle:
        by_file[r['file'].lower()].append(int(r['success']))
    lo, hi = clustered_interval(by_file)
    report['sensitivity']['7_one_unit_per_file'] = proportion(success(one))
    report['sensitivity']['7_file_clustered_bootstrap'] = dict(files=len(by_file), ci95=[lo, hi])
    done = [r for r in rows if 'footprint' in r]
    after_cc = [c for r in done for c in r['profile']['after'].values()]
    report['gaming_checks'] = dict(
        unit_symbol_complexity_after=dict(collections.Counter('exactly 10' if c == 10 else '9' if c == 9 else '8 or less' if c <= 8 else 'above 10' for c in after_cc)),
        unit_symbols_no_longer_present=sum(len(r['reproduced']) - len(r['profile']['after']) for r in done),
        new_methods_per_unit=dict(mean=statistics.mean(r['profile']['new_methods'] for r in done), max=max(r['profile']['new_methods'] for r in done)),
        new_method_max_complexity=dict(collections.Counter(r['profile']['new_max_complexity'] for r in done)),
        decision_burden_delta=dict(mean=statistics.mean(r['decision_burden_delta'] for r in done), median=statistics.median(r['decision_burden_delta'] for r in done),
                                   units_increased=sum(r['decision_burden_delta'] > 0 for r in done), units_decreased=sum(r['decision_burden_delta'] < 0 for r in done)),
        near_threshold_methods=dict(before=sum(r['near_before'] for r in done), after=sum(r['near_after'] for r in done),
                                    units_increased=sum(r['near_after'] > r['near_before'] for r in done)))
    report['cost'] = dict(tokens_total=sum(r['tokens'] for r in rows), tokens_per_unit=dict(mean=statistics.mean(r['tokens'] for r in rows), median=statistics.median(r['tokens'] for r in rows),
                                                                                       max=max(r['tokens'] for r in rows)),
                          calls=dict(collections.Counter(r['calls'] for r in rows)), seconds_per_unit=statistics.mean(r['seconds'] for r in rows),
                          edit_footprint=dict(added_mean=statistics.mean(r['footprint']['added'] for r in done), removed_mean=statistics.mean(r['footprint']['removed'] for r in done)),
                          tokens_delta_mean=statistics.mean(r['tokens_delta'] for r in done))
    report['persistence_in_the_developers_own_history'] = dict(units_whose_method_is_still_long_at_head=sum(r['persists_at_head'] for r in rows), units=len(rows))
    (a.out / 'report.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
    review = a.out / 'review'
    review.mkdir(exist_ok=True)
    table = ['# Behaviour-preservation review (protocol v0.5, Section 7.2)', '',
             'For each unit judge, from the diff alone, whether the candidate is a behaviour-preserving restructuring of the post-commit file: '
             '`preserving`, `not preserving` or `cannot tell`. Record the judgement in `review-decisions.json` before looking at any other result.', '',
             '| Unit | File | Layer | Lines added | Lines removed |', '|---|---|---|---|---|']
    decisions = {}
    for r in done:
        post = core.decode_source((a.manifest / r['unit_id'] / 'post.cs').read_bytes())
        candidate = core.decode_source((a.run / r['unit_id'] / 'candidate.cs').read_bytes())
        diff = difflib.unified_diff(post.splitlines(), candidate.splitlines(), 'post-commit', 'candidate', lineterm='', n=4)
        (review / f"{r['unit_id']}.diff").write_text('\n'.join(diff) + '\n', encoding='utf-8')
        table.append(f"| {r['unit_id']} | `{r['file']}` | {r['layer']} | {r['footprint']['added']} | {r['footprint']['removed']} |")
        decisions[r['unit_id']] = dict(judgement=None, reviewer='R2', note='')
    (review / 'REVIEW.md').write_text('\n'.join(table) + '\n', encoding='utf-8')
    (review / 'review-decisions.json').write_text(json.dumps(decisions, indent=1), encoding='utf-8')
    print(json.dumps(report, indent=1))


if __name__ == '__main__':
    main()
