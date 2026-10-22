"""Freeze record for the stratum-A replay (protocol v0.3, gate G-FREEZE). No model calls.

Usage: python replay_freeze.py --manifest DIR --oracle-dir DIR --out freeze.json [--check]
--check lists unmet gates without writing. A freeze is refused while any gate is unmet.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
LEDGER = HERE.parent / 'budget-ledger.json'
CODE = [*sorted(HERE.glob('*.py')), HERE / 'PROTOCOL.md', HERE / 'ORACLE_TEST_SPEC.md', HERE / 'replay_settings.json',
        HERE.parent / 'natural_validation' / 'patches.py', HERE.parent / 'run_pilot.py', HERE.parent / 'accounting.py',
        REPO / 'src/HybridLens.ChangeStub/bin/Debug/net10.0/HybridLens.ChangeStub.dll',
        REPO / 'src/HybridLens.DesignQuality/bin/Debug/net10.0/HybridLens.DesignQuality.dll']


def used_oracles(manifest):
    return sorted({o['step_id'] for t in manifest['targets'] for s in t['steps'] for o in s['oracle_classes']})


def gate_problems(manifest, decisions, settings, ledger):
    problems = []
    for sid in used_oracles(manifest):
        decision = decisions.get(sid, {}).get('decision')
        if decision is None:
            problems.append(f'oracle review pending: {sid}')
        elif decision == 'reject':
            problems.append(f'manifest uses rejected oracle class {sid}; rebuild the manifest')
    window = settings.get('context_window_confirmed_tokens')
    needed = settings['input_bound_tokens'] + settings['max_completion_tokens_per_call']
    if not window or window < needed:
        problems.append(f'context window not confirmed to exceed {needed} tokens')
    if not settings.get('organisational_approval_recorded'):
        problems.append('organisational approval for sending Bouw source not recorded')
    if ledger['authorised_ceiling'] < settings['required_ceiling_tokens']:
        problems.append(f"ledger ceiling {ledger['authorised_ceiling']} below required {settings['required_ceiling_tokens']}")
    if any(e['status'] != 'completed' or e.get('reserved_tokens', 0) for e in ledger['entries']):
        problems.append('ledger has an unreconciled entry')
    return problems


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def hash_files(paths):
    return {str(p): sha(p) for p in paths}


def changed_files(record):
    return [p for p, h in record.items() if not Path(p).exists() or sha(p) != h]


def repair_inputs(repairs):
    return [repairs / 'acquisition.json', *sorted(repairs.glob('T*/repaired.cs'))]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--oracle-dir', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--check', action='store_true')
    p.add_argument('--repairs', type=Path)
    a = p.parse_args()
    manifest = json.loads((a.manifest / 'manifest.json').read_text(encoding='utf-8'))
    decisions = json.loads((a.oracle_dir / 'review-decisions.json').read_text(encoding='utf-8'))
    settings = json.loads((HERE / 'replay_settings.json').read_text(encoding='utf-8'))
    ledger = json.loads(LEDGER.read_text(encoding='utf-8'))
    problems = gate_problems(manifest, decisions, settings, ledger)
    if a.check or problems:
        print(json.dumps(dict(gates_met=not problems, problems=problems), indent=1))
        raise SystemExit(0 if a.check else 1)
    if a.out.exists():
        raise SystemExit('Freeze record exists; a freeze is never overwritten')
    inputs = [a.manifest / 'manifest.json', *sorted((a.manifest / 'diffs').glob('*.diff')),
              *[a.oracle_dir / sid / 'submission' / f'Step_{sid}.cs' for sid in used_oracles(manifest)],
              a.oracle_dir / 'review-decisions.json', *(repair_inputs(a.repairs) if a.repairs else [])]
    record = dict(schema_version='reaccrual-freeze/0.1', manifest=str(a.manifest), seed=manifest['seed'],
                  pipeline_commit=subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip(),
                  dotnet_sdk=subprocess.run(['dotnet', '--version'], capture_output=True, text=True).stdout.strip(),
                  starting_ledger=dict(authorised_ceiling=ledger['authorised_ceiling'], cumulative_recorded_tokens=ledger['cumulative_recorded_tokens']),
                  settings=settings, inputs=hash_files(inputs), code=hash_files(CODE))
    a.out.write_text(json.dumps(record, indent=1), encoding='utf-8')
    print(f'Frozen: {len(record["inputs"])} inputs, {len(record["code"])} code files')


if __name__ == '__main__':
    main()
