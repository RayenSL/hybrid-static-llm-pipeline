"""Build the frozen stratum-A replay manifest from the feasibility audit and admitted oracle tests. No model calls.

Usage: python replay_prepare.py --audit-dir DIR --oracle-dir DIR --repo REPO --out DIR [--exclude-project NAME ...]
                                [--max-tokens 32000] [--seed reaccrual-v0.3]
The output contains proprietary commit text and diffs; --out must be outside the public repository.
"""
import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

QUALIFYING = {'test', 'stub'}
STUBBER = Path(__file__).resolve().parents[3] / 'src/HybridLens.ChangeStub/bin/Debug/net10.0/HybridLens.ChangeStub.dll'


def api_signatures(pre_bytes, post_bytes):
    """Accessible declarations the commit added or changed in the target file (amendment 0.3.2), bodies omitted."""
    with tempfile.TemporaryDirectory() as tmp:
        pre, post = Path(tmp, 'pre.cs'), Path(tmp, 'post.cs')
        pre.write_bytes(pre_bytes)
        post.write_bytes(post_bytes)
        output = subprocess.run(['dotnet', str(STUBBER), '--api-signatures', str(pre), str(post)], capture_output=True, text=True, check=True).stdout
    return json.loads(output)['added']


def project_name(key):
    name = Path(key.replace('\\', '/')).name
    return name[:-len('.csproj')] if name.endswith('.csproj') else name


def reference_outcomes(record, excluded, projects=None):
    return {p: dict(r['outcomes']) for p, r in record['post'].items()
            if r['status'] == 'ran' and project_name(p) not in excluded and (projects is None or p in projects)}


def qualified(outcomes_by_project):
    return {f'{project}::{test}': outcome for project, outcomes in outcomes_by_project.items() for test, outcome in outcomes.items()}


def developer_fail_to_pass(record, target, excluded, projects=None):
    """Tests passing after the commit that fail on the pre-commit file, or on the stubbed file when the pre-commit file does not build."""
    reference = reference_outcomes(record, excluded, projects)
    pre = record['pre'].get(target, {})
    builds = all(not (isinstance(v, dict) and v.get('status') == 'build_failed') for v in pre.values())
    runs = pre if builds else record.get('stub', {}).get(target, {})
    flips = set()
    for project, outcomes in reference.items():
        run = runs.get(project)
        if isinstance(run, dict) and run.get('status') == 'ran':
            flips |= {f'{project}::{t}' for t, o in outcomes.items() if o == 'Passed' and run['outcomes'].get(t) != 'Passed'}
    return flips


def qualifying_prefix(kinds, admitted):
    count = 0
    for kind, oracle in zip(kinds, admitted):
        if not (kind in QUALIFYING or (kind == 'unchecked' and oracle)):
            break
        count += 1
    return count


# A merge between two step commits can change the file, so the developer's next step builds on content the agent never saw.
def contiguous_prefix(parent_states, previous_states):
    count = 0
    for parent, previous in zip(parent_states, previous_states):
        if parent != previous:
            break
        count += 1
    return count


def rank(seed, target_id):
    return hashlib.sha256(f'{seed}|{target_id}'.encode()).hexdigest()


def select_calibration(targets, seed, n):
    god_classes = sorted((t for t in targets if t['type'] == 'godClass'), key=lambda t: rank(seed, t['target_id']))
    return sorted(t['target_id'] for t in god_classes[:n])


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, check=True).stdout


def load_oracles(oracle_dir):
    oracles = {}
    decisions_path = oracle_dir / 'review-decisions.json'
    decisions = json.loads(decisions_path.read_text(encoding='utf-8')) if decisions_path.exists() else {}
    for step_path in oracle_dir.glob('T*/step.json'):
        validation_path = step_path.parent / 'validation.json'
        if not validation_path.exists():
            continue
        validation = json.loads(validation_path.read_text(encoding='utf-8'))
        step = json.loads(step_path.read_text(encoding='utf-8'))
        review = decisions.get(step['step_id'], {}).get('decision')
        if validation['admitted'] and review != 'reject':
            oracles[(step['commit'], step['target_file'])] = dict(step=step, validation=validation, review=review)
    return oracles


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--audit-dir', type=Path, required=True)
    p.add_argument('--oracle-dir', type=Path, required=True)
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--exclude-project', action='append', default=[])
    p.add_argument('--max-tokens', type=int, default=32000)
    p.add_argument('--seed', default='reaccrual-v0.3')
    a = p.parse_args()
    excluded = set(a.exclude_project)
    if a.out.exists():
        raise SystemExit('Output exists: use a new manifest directory')
    records = {}
    for line in (a.audit_dir / 'f2p-results.jsonl').read_text(encoding='utf-8').splitlines():
        if line.strip():
            r = json.loads(line)
            records[r['commit']] = r
    commits = json.loads((a.audit_dir / 'phase1-candidates.json').read_text(encoding='utf-8'))['commits']
    eligible = sorted((t for t in json.loads((a.audit_dir / 'eligible-targets.json').read_text(encoding='utf-8'))
                       if t['approx_tokens_t0'] <= a.max_tokens), key=lambda t: t['path'])
    oracles = load_oracles(a.oracle_dir)
    (a.out / 'diffs').mkdir(parents=True)
    targets, excluded_targets = [], []
    for index, t in enumerate(eligible, 1):
        target_id, path = f'T{index:02d}', t['path']
        admitted = [(h, path) in oracles for h, _ in t['steps']]
        k = qualifying_prefix(t['f2p_kinds'], admitted)
        window = [h for h, _ in t['steps'][:k]]
        k = contiguous_prefix([git(a.repo, 'show', f'{h}^:{path}') for h in window],
                              [git(a.repo, 'show', f'{h}:{path}') for h in [t['t0'], *window[:-1]]])
        if k < 2:
            excluded_targets.append(dict(target_id=target_id, reason='fewer than two qualifying steps', k=k))
            continue
        steps = []
        for number, (commit, kind) in enumerate(t['steps'][:k], 1):
            record = records[commit]
            projects = [p for p in record['target_projects'][path] if project_name(p) not in excluded]
            others = [f for f in commits[commit]['files'] if f.endswith('.cs') and f != path and 'test' not in f.lower()]
            diff = git(a.repo, 'diff', f'{commit}^', commit, '--', *others) if others else b''
            diff_path = a.out / 'diffs' / f'{target_id}-S{number}.diff'
            diff_path.write_bytes(diff)
            reference = reference_outcomes(record, excluded, projects)
            fail_to_pass = sorted(developer_fail_to_pass(record, path, excluded, projects))
            installed = []
            for earlier in t['steps'][:number]:
                oracle = oracles.get((earlier[0], path))
                if oracle is None:
                    continue
                v = oracle['validation']
                sid = oracle['step']['step_id']
                if earlier[0] == commit:
                    reference[f'oracle/{sid}'] = dict(v['post_runs'][0]['outcomes'])
                    fail_to_pass += [f'oracle/{sid}::{t_name}' for t_name in v['stub_failing_tests']]
                    installed.append(dict(step_id=sid, test_project=oracle['step']['test_project'], own=True))
                else:
                    later = next((r for r in v.get('retention', []) if r['commit'] == commit), None)
                    if later and later['retained']:
                        reference[f'oracle/{sid}'] = dict(later['outcomes'])
                        installed.append(dict(step_id=sid, test_project=oracle['step']['test_project'], own=False))
            message = git(a.repo, 'log', '-1', '--format=%B', commit).decode('utf-8', errors='replace').strip()
            signatures = api_signatures(git(a.repo, 'show', f'{commit}^:{path}'), git(a.repo, 'show', f'{commit}:{path}'))
            steps.append(dict(step=number, commit=commit, kind=kind if kind != 'unchecked' else 'oracle', message=message,
                              other_files=others, diff=diff_path.name, test_projects=projects, reference_outcomes=reference,
                              fail_to_pass=sorted(set(fail_to_pass)), oracle_classes=installed, api_signatures=signatures))
        targets.append(dict(target_id=target_id, path=path, symbol=t['symbol'], type=t['type'], band=t['band'], metrics=t['metrics'],
                            t0=t['t0'], k=k, approx_tokens_t0=t['approx_tokens_t0'], steps=steps))
    calibration = select_calibration(targets, a.seed, 2)
    for t in targets:
        t['role'] = 'calibration' if t['target_id'] in calibration else 'validation'
    order = sorted((t['target_id'] for t in targets if t['role'] == 'validation'), key=lambda tid: rank(a.seed, tid))
    manifest = dict(schema_version='reaccrual-replay-manifest/0.1', seed=a.seed, excluded_projects=sorted(excluded),
                    max_tokens=a.max_tokens, validation_order=order, calibration=calibration,
                    excluded_targets=excluded_targets, targets=targets)
    (a.out / 'manifest.json').write_text(json.dumps(manifest, indent=1), encoding='utf-8')
    by_type = {ty: sum(1 for t in targets if t['role'] == 'validation' and t['type'] == ty) for ty in ('godClass', 'longMethod')}
    print(json.dumps(dict(targets=len(targets), validation=len(order), calibration=calibration, validation_by_type=by_type,
                          excluded=excluded_targets), indent=1))


if __name__ == '__main__':
    main()
