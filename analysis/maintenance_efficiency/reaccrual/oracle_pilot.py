"""Oracle pilot for the shadow-loop study (protocol v0.5, Section 8). Makes no model calls.

Usage: python oracle_pilot.py --frame frame.json --clone CLONE --out DIR [--per-stratum N] [--targets-file F]
For the first N candidates of each stratum (frame order), checks out the post-commit state, builds the whole solution and runs the
test projects that reference the file's project (database-integration, UI-dialog and end-to-end projects excluded, as in v0.3).
The clone is force-checked-out and must be a disposable local clone.
"""
import argparse
import collections
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import feasibility_audit as fa
from acquire_repairs import ROOT_SOLUTION, SOLUTION, nuget_config_text, root_solution_text

MIN_PASSING = 10
EXCLUDED = {'Ibis.Calculeren.IntegratieTests', 'Ibis.Calculeren.UI.Tests'}


def has_oracle(row):
    if not row['solution_built']:
        return False
    return sum(p['passed'] for p in row['test_projects'] if p['status'] == 'ran') >= MIN_PASSING


def yield_by_stratum(rows):
    out = collections.defaultdict(lambda: dict(checked=0, with_oracle=0))
    for r in rows:
        out[r['stratum']]['checked'] += 1
        out[r['stratum']]['with_oracle'] += has_oracle(r)
    return dict(out)


def check(clone, candidate, results_dir):
    commit, path = candidate['commit'], candidate['file']
    fa.git(clone, 'checkout', '-f', '-q', commit)
    fa.git(clone, 'clean', '-ffdxq')
    sln = clone / SOLUTION
    if not sln.exists():
        return dict(solution_built=False, reason='no solution file', test_projects=[])
    (clone / ROOT_SOLUTION).write_text(root_solution_text(sln.read_text(encoding='utf-8-sig'), 'Ibis.Calculeren'), encoding='utf-8')
    (clone / 'NuGet.Config').write_text(nuget_config_text(Path.home() / '.nuget' / 'packages'), encoding='utf-8')
    code, log, seconds = fa.run(['dotnet', 'build', str(clone / ROOT_SOLUTION), '--nologo', '-v', 'q', '-p:TreatWarningsAsErrors=false', '-p:NuGetAudit=false'],
                                clone, timeout=1500)
    built = code == 0
    errors = sorted({line.strip().split(': error ')[-1][:80] for line in log.splitlines() if ': error ' in line})[:3]
    projects = []
    fa.EXCLUDED.update(EXCLUDED)
    if built:
        for project in fa.test_projects_for(clone, path, []):
            r = fa.run_tests(clone, project, results_dir, None, no_restore=True)
            projects.append(dict(project=project.stem, status=r['status'], seconds=r['seconds'],
                                 passed=sum(o == 'Passed' for o in r['outcomes'].values()), failed=sum(o == 'Failed' for o in r['outcomes'].values())))
    return dict(solution_built=built, build_seconds=seconds, build_errors=errors, test_projects=projects)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--frame', type=Path, required=True)
    p.add_argument('--clone', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--per-stratum', type=int, default=3)
    a = p.parse_args()
    frame = json.loads(a.frame.read_text(encoding='utf-8'))
    taken = collections.Counter()
    picks = []
    for candidate in frame['candidates']:
        if taken[candidate['stratum']] < a.per_stratum:
            taken[candidate['stratum']] += 1
            picks.append(candidate)
    a.out.mkdir(parents=True, exist_ok=True)
    results = a.out / 'trx'
    results.mkdir(exist_ok=True)
    rows = []
    for candidate in picks:
        row = dict(commit=candidate['commit'], symbol=candidate['symbol'], file=candidate['file'], stratum=candidate['stratum'],
                   complexity=candidate['complexity'], **check(a.clone, candidate, results))
        rows.append(row)
        (a.out / 'pilot.json').write_text(json.dumps(rows, indent=1), encoding='utf-8')
        print(json.dumps(dict(stratum=row['stratum'], built=row['solution_built'], oracle=has_oracle(row))), flush=True)
    summary = dict(checked=len(rows), with_oracle=sum(has_oracle(r) for r in rows), by_stratum=yield_by_stratum(rows),
                   build_failures=collections.Counter(e for r in rows if not r['solution_built'] for e in r.get('build_errors', [])[:1]).most_common(5))
    (a.out / 'pilot-summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
