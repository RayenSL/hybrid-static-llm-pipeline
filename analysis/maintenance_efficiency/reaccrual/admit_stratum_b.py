"""Admission of R2's stratum-B sequences, gates G1-G5 (STRATUM_B_TASK_SPEC.md). No model calls.

Usage: python admit_stratum_b.py <packets-dir> [--targets GC-02 ...] [--author-check]
--author-check writes author-check.json with per-variant outcomes and skips every gate that probes the repaired source (G1 repaired, G4).
The repaired source is used by the harness only and is never written into a packet.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = HERE.parents[2]
PROBE = ROOT / 'expanded_evaluator/bin/Debug/net10.0/Replay.dll'
METRICS = REPO / 'src/HybridLens.DesignQuality/bin/Debug/net10.0/HybridLens.DesignQuality.dll'
sys.path.insert(0, str(ROOT / 'benchmark'))
from build_spec import HEADER, FOOTER  # noqa: E402

CHECK = re.compile(r'Check\(\s*"([^"]+)"\s*,\s*(true|false)\s*,')


def step_gates(k, cases, retained, superseded, outcomes):
    """cases: step-k case name -> acceptance flag; outcomes: variant -> {case: passed} or None when it does not build."""
    failed = []
    acceptance = [c for c, flag in cases.items() if flag]
    lacking = ['previous'] + (['repaired'] if k == 1 else [])
    if any(outcomes.get(v) is not None and all(outcomes[v].get(c) for c in acceptance) for v in lacking):
        failed.append('G1')
    required = list(cases) + [c for c in retained if c not in superseded]
    reference = outcomes.get('reference')
    if reference is None or not all(reference.get(c) for c in required):
        failed.append('G2')
    for mutant in ('mutant1', 'mutant2'):
        result = outcomes.get(mutant)
        if result is None or all(result.get(c) for c in cases):
            failed.append(f'G3:{mutant}')
    return failed


# Per step, because a step whose tests use a new public member compiles against neither the original nor the repair.
def g4(per_step):
    return any(o is not None for o, _ in per_step) and all(o == r for o, r in per_step)


def case_name_problems(names_by_step):
    problems, seen = [], set()
    for k, names in sorted(names_by_step.items()):
        for name in names:
            if not name.startswith(f'S{k}-'):
                problems.append(f'case {name} in step {k} is not prefixed S{k}-')
            if name in seen:
                problems.append(f'duplicate case name {name}')
            seen.add(name)
    return problems


def probe(original, candidate, body, helpers):
    with tempfile.TemporaryDirectory() as tmp:
        tests, out = Path(tmp, 'tests.cs'), Path(tmp, 'out.json')
        tests.write_text(HEADER + body + FOOTER + helpers, encoding='utf-8')
        subprocess.run(['dotnet', str(PROBE), '--probe', str(original), str(candidate), str(tests), str(out)], capture_output=True, timeout=120)
        raw = json.loads(out.read_text(encoding='utf-8-sig')) if out.exists() else dict(build_passed=False)
    return {c['id']: bool(c['passed']) for c in raw['cases']} if raw.get('build_passed') else None


def decision_burden(path):
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, 'f.cs').write_bytes(Path(path).read_bytes())
        return json.loads(subprocess.run(['dotnet', str(METRICS), '--file-metrics', tmp], capture_output=True, text=True, check=True).stdout)['f']['decision_burden']


def admit_target(folder, pair, author=False):
    original = (ROOT / pair['baseline_path']).resolve()
    repaired = (ROOT / pair['repaired_path']).resolve()
    helpers = (folder / 'helpers.cs').read_text(encoding='utf-8') if (folder / 'helpers.cs').exists() else ''
    steps = {k: folder / 'steps' / f'S{k}' for k in range(1, 5)}
    if any(not (steps[k] / f).stat().st_size for k in steps for f in ('requirement.md', 'tests.cs', 'reference.cs', 'mutant1.cs', 'mutant2.cs')):
        return dict(status='incomplete')
    bodies = {k: (steps[k] / 'tests.cs').read_text(encoding='utf-8') for k in steps}
    cases = {k: {n: flag == 'true' for n, flag in CHECK.findall(bodies[k])} for k in steps}
    problems = case_name_problems({k: list(cases[k]) for k in steps})
    if problems:
        return dict(status='rejected', problems=problems)
    result, superseded = dict(steps={}), set()
    for k in steps:
        superseded |= {line.strip() for line in (steps[k] / 'superseded.txt').read_text(encoding='utf-8').splitlines() if line.strip()}
        body = ''.join(bodies[j] for j in range(1, k + 1))
        variants = dict(previous=original if k == 1 else steps[k - 1] / 'reference.cs', reference=steps[k] / 'reference.cs',
                        mutant1=steps[k] / 'mutant1.cs', mutant2=steps[k] / 'mutant2.cs')
        if k == 1 and not author:
            variants['repaired'] = repaired
        outcomes = {name: probe(original, path, body, helpers) for name, path in variants.items()}
        retained = [c for j in range(1, k) for c in cases[j]]
        result['steps'][k] = dict(failed=step_gates(k, cases[k], retained, superseded, outcomes),
                                  builds={n: o is not None for n, o in outcomes.items()})
        if author:
            result['steps'][k]['outcomes'] = outcomes
    result['G5'] = decision_burden(steps[4] / 'reference.cs') > decision_burden(original)
    if author:
        result['status'] = 'author-gates-passed' if all(not s['failed'] for s in result['steps'].values()) and result['G5'] else 'author-gates-failed'
        return result
    result['G4'] = g4([(probe(original, original, bodies[k], helpers), probe(original, repaired, bodies[k], helpers)) for k in steps])
    result['admitted'] = all(not s['failed'] for s in result['steps'].values()) and result['G4'] and result['G5']
    result['status'] = 'admitted' if result['admitted'] else 'rejected'
    return result


def main():
    packets = Path(sys.argv[1])
    author = '--author-check' in sys.argv
    only = [a for a in sys.argv[sys.argv.index('--targets') + 1:] if not a.startswith('--')] if '--targets' in sys.argv else None
    pairs = {p['target_id']: p for p in json.loads((ROOT / 'generated' / 'campaign.json').read_text(encoding='utf-8'))['pairs']}
    summary = {}
    for folder in sorted(p for p in packets.iterdir() if (p / 'target.json').exists()):
        if only and folder.name not in only:
            continue
        result = admit_target(folder, pairs[folder.name], author)
        (folder / ('author-check.json' if author else 'admission.json')).write_text(json.dumps(result, indent=1), encoding='utf-8')
        summary[folder.name] = result['status']
        print(folder.name, result['status'], json.dumps({k: v['failed'] for k, v in result.get('steps', {}).items()}), flush=True)
    if not author:
        (packets / 'admission-summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
