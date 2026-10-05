"""Repair acquisition at each replay target's t0 (protocol v0.3, Section 4.2). Makes model calls; refuses unless --live.

Usage: python acquire_repairs.py --manifest DIR --audit-dir DIR --clone CLONE --out DIR --live [--targets T01 ...]
Up to three grounded single-shot attempts (the thesis arm, via the CLI); the first attempt passing every gate is accepted.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
STUBBER = REPO / 'src/HybridLens.ChangeStub/bin/Debug/net10.0/HybridLens.ChangeStub.dll'
SOLUTION = 'Ibis.Calculeren/IbisCalculeren.sln'
TYPE_NAMES = {'godClass': 'GodClass', 'longMethod': 'LongMethod'}
GATES = ('built', 'resolved', 'no_new_same_type', 'api_preserved', 'tests_passed')


def cli_input(finding, solution_dir):
    return json.dumps(dict(anti_pattern_type=TYPE_NAMES[finding['type']], severity=finding['severity'],
                           symbol_name=finding['symbolName'], line=finding['line'], snippet=finding.get('snippet'),
                           file_path=str(solution_dir / finding['filePath'].replace('\\', '/')), metrics=finding['metrics']))


def gate_results(attempt):
    return dict(built=attempt['build'], resolved=attempt['resolved'], no_new_same_type=attempt['new_same_type'] == 0,
                api_preserved=not attempt['api_missing'], tests_passed=attempt['tests_ok'])


def accept(attempts):
    """Return (accepted run number or None, cumulative flow counts over the gates in order)."""
    flow = dict(attempted=len(attempts), **{g: 0 for g in GATES}, accepted=0)
    accepted = None
    for attempt in attempts:
        results = gate_results(attempt)
        for gate in GATES:
            if not results[gate]:
                break
            flow[gate] += 1
        else:
            if accepted is None:
                accepted = attempt['run']
    flow['accepted'] = int(accepted is not None)
    return accepted, flow


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--audit-dir', type=Path, required=True)
    p.add_argument('--clone', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--targets', nargs='*')
    p.add_argument('--live', action='store_true')
    p.add_argument('--freeze', type=Path)
    a = p.parse_args()
    if not a.live:
        raise SystemExit('Repair acquisition makes model calls; pass --live only after the freeze and ceiling authorisation.')
    sys.path.insert(0, str(HERE))
    from replay_freeze import changed_files
    if not a.freeze or not a.freeze.exists():
        raise SystemExit('Repair acquisition requires the freeze record (--freeze)')
    frozen = json.loads(a.freeze.read_text(encoding='utf-8'))
    drift = changed_files(frozen['inputs']) + changed_files(frozen['code'])
    if drift:
        raise SystemExit(f'Frozen inputs or code changed: {drift[:5]}')
    from feasibility_audit import git, run_tests
    from replay_prepare import qualified
    from replay_core import decode_source
    manifest = json.loads((a.manifest / 'manifest.json').read_text(encoding='utf-8'))
    a.out.mkdir(parents=True, exist_ok=False)
    table = []
    for target in manifest['targets']:
        if a.targets and target['target_id'] not in a.targets:
            continue
        tid, path, t0 = target['target_id'], target['path'], target['t0']
        work = a.out / tid
        work.mkdir()
        findings = json.loads((a.audit_dir / 't0-findings' / f'{t0}.json').read_text(encoding='utf-8-sig'))['findings']
        finding = next(f for f in findings if f['symbolName'] == target['symbol'] and f['type'] == target['type']
                       and 'Ibis.Calculeren/' + f['filePath'].replace('\\', '/') == path)
        before_same = {f['symbolName'] for f in findings if f['type'] == target['type'] and 'Ibis.Calculeren/' + f['filePath'].replace('\\', '/') == path}
        git(a.clone, 'checkout', '-f', '-q', t0)
        original = decode_source(git(a.clone, 'show', f'{t0}:{path}'))
        (work / 'input.jsonl').write_text(cli_input(finding, a.clone / 'Ibis.Calculeren') + '\n', encoding='utf-8')
        subprocess.run(['dotnet', 'run', '--project', str(REPO / 'src/HybridLens.CLI'), '--', 'factorial-single-shot',
                        '--from', str(work / 'input.jsonl'), '--target', str(a.clone / SOLUTION), '--model', 'gpt-5.6-sol',
                        '--runs', '3', '--grounded'], cwd=work, check=True)
        trace = next((work / 'runs').glob('*.jsonl'))
        projects = target['steps'][0]['test_projects']
        reference = {}
        for project in projects:
            reference[project] = run_tests(a.clone, a.clone / project, work, None)['outcomes']
        attempts = []
        for record in map(json.loads, trace.read_text(encoding='utf-8').splitlines()):
            attempt = dict(run=record['run_number'], build=bool(record.get('build_passed')), resolved=bool(record.get('verified_repair_success')),
                           new_same_type=0, api_missing=[], tests_ok=False, input_tokens=record.get('input_tokens'), output_tokens=record.get('output_tokens'))
            if attempt['build'] and attempt['resolved'] and record.get('materialized_source_ref'):
                repaired = json.loads((work / record['materialized_source_ref']).read_text(encoding='utf-8'))['final_source']
                with tempfile.TemporaryDirectory() as tmp:
                    Path(tmp, 'a.cs').write_text(original, encoding='utf-8')
                    Path(tmp, 'b.cs').write_text(repaired, encoding='utf-8')
                    attempt['api_missing'] = json.loads(subprocess.run(['dotnet', str(STUBBER), '--missing-api', str(Path(tmp, 'a.cs')), str(Path(tmp, 'b.cs'))],
                                                                       capture_output=True, text=True, check=True).stdout)['missing']
                git(a.clone, 'checkout', '-f', '-q', t0)
                (a.clone / path).write_text(repaired, encoding='utf-8')
                scan = work / f'scan-run{attempt["run"]}.json'
                subprocess.run(['dotnet', 'run', '--project', str(REPO / 'src/HybridLens.CLI'), '--', 'analyse', '--target', str(a.clone / SOLUTION),
                                '--dry-run', '--format', 'json', '--severity', 'Warning', '--output', str(scan)], capture_output=True)
                after = json.loads(scan.read_text(encoding='utf-8-sig'))['findings'] if scan.exists() else []
                attempt['new_same_type'] = len({f['symbolName'] for f in after if f['type'] == target['type']
                                                and 'Ibis.Calculeren/' + f['filePath'].replace('\\', '/') == path} - before_same) if scan.exists() else 1
                candidate = {pr: run_tests(a.clone, a.clone / pr, work, None)['outcomes'] for pr in projects}
                required = {t for t, o in qualified(reference).items() if o == 'Passed'}
                attempt['tests_ok'] = all(qualified(candidate).get(t) == 'Passed' for t in required)
                if not attempt['api_missing'] and attempt['tests_ok'] and attempt['new_same_type'] == 0:
                    (work / f'repaired-run{attempt["run"]}.cs').write_text(repaired, encoding='utf-8')
            attempts.append(attempt)
        accepted, flow = accept(attempts)
        if accepted is not None:
            (work / 'repaired.cs').write_bytes((work / f'repaired-run{accepted}.cs').read_bytes())
        table.append(dict(target_id=tid, accepted_run=accepted, flow=flow, attempts=attempts))
        (a.out / 'acquisition.json').write_text(json.dumps(table, indent=1), encoding='utf-8')
        print(json.dumps(dict(target=tid, accepted=accepted, flow=flow)), flush=True)


if __name__ == '__main__':
    main()
