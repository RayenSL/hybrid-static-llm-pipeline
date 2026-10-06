"""Repair acquisition at each replay target's t0 (protocol v0.3, Section 4.2). Makes model calls; refuses unless --live.

Usage: python acquire_repairs.py --manifest DIR --audit-dir DIR --clone CLONE --out DIR --live [--targets T01 ...] [--resume | --regate]
Up to three grounded single-shot attempts (the thesis arm, via the CLI); the first attempt passing every gate is accepted.
--regate re-evaluates the recorded attempts of --targets without model calls.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
STUBBER = REPO / 'src/HybridLens.ChangeStub/bin/Debug/net10.0/HybridLens.ChangeStub.dll'
SOLUTION = 'Ibis.Calculeren/IbisCalculeren.sln'
ROOT_SOLUTION = 'IbisCalculeren.root.sln'
TYPE_NAMES = {'godClass': 'GodClass', 'longMethod': 'LongMethod'}
GATES = ('built', 'resolved', 'no_new_same_type', 'api_preserved', 'tests_passed')
RESERVE_PER_TARGET = 300_000


PROJECT_LINE = re.compile(r'(Project\("\{[^}]+\}"\) = "[^"]*", ")([^"]+\.(?:cs|vb|fs|vcx|wix|wap|sql)proj)(")')


def root_solution_text(sln_text, folder):
    """Repository-root solution: the CLI copies the solution's folder, and Bouw projects reference paths above it."""
    return PROJECT_LINE.sub(lambda m: f'{m.group(1)}{folder}\\{m.group(2)}{m.group(3)}', sln_text)


# Some t0 packages need a UI-vendor version range only its licensed feed lists (HTTP 400); the pinned version is cached.
def nuget_config_text(packages_dir):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<configuration>\n  <packageSources>\n'
            f'    <add key="reaccrual-local-cache" value="{packages_dir}" />\n  </packageSources>\n'
            '  <disabledPackageSources>\n    <add key="Infragistics" value="true" />\n  </disabledPackageSources>\n</configuration>\n')


def cli_input(finding, solution_dir):
    return json.dumps(dict(anti_pattern_type=TYPE_NAMES[finding['type']], severity=finding['severity'],
                           symbol_name=finding['symbolName'], line=finding['line'], snippet=finding.get('snippet'),
                           file_path=str(solution_dir / finding['filePath'].replace('\\', '/')), metrics=finding['metrics']))


def in_target_file(finding, target):
    return finding['type'] == target['type'] and 'Ibis.Calculeren/' + finding['filePath'].replace('\\', '/') == target['path']


# The CLI verifier matches simple-name substrings, so another method named like the target's prefix stands in for it.
def target_resolved(after, target):
    return not any(in_target_file(f, target) and f['symbolName'] == target['symbol'] for f in after)


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
    p.add_argument('--resume', action='store_true')
    p.add_argument('--regate', action='store_true')
    a = p.parse_args()
    if not a.live and not a.regate:
        raise SystemExit('Repair acquisition makes model calls; pass --live only after the freeze and ceiling authorisation.')
    if a.regate and not (a.targets and a.out.exists()):
        raise SystemExit('--regate needs --targets and an existing --out')
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
    import replay_ledger as ledger
    ledger_path = HERE.parent / 'budget-ledger.json'
    prefix = f'reaccrual-acquisition-{a.out.name}'
    manifest = json.loads((a.manifest / 'manifest.json').read_text(encoding='utf-8'))
    if a.out.exists() and not (a.resume or a.regate):
        raise SystemExit('Output exists: use a new directory, or --resume to continue it')
    a.out.mkdir(parents=True, exist_ok=True)
    table_path = a.out / 'acquisition.json'
    table = json.loads(table_path.read_text(encoding='utf-8')) if table_path.exists() else []
    done = set() if a.regate else {row['target_id'] for row in table}
    if not a.regate:
        ledger.recover_interrupted(ledger_path, f'interrupted {prefix} run, resumed', prefix=prefix)
        previous = sum(1 for e in json.loads(ledger_path.read_text(encoding='utf-8'))['entries'] if e['experiment'].startswith(prefix))
        experiment = f'{prefix}-{previous + 1}'
        ledger.open_entry(ledger_path, experiment, a.out)
    for target in manifest['targets']:
        if (a.targets and target['target_id'] not in a.targets) or target['target_id'] in done:
            continue
        tid, path, t0 = target['target_id'], target['path'], target['t0']
        work = a.out / tid
        if not a.regate:
            if work.exists():
                work.rename(a.out / f'_aborted-{tid}-{len(list(a.out.glob(f"_aborted-{tid}-*"))) + 1}')
            work.mkdir()
        findings = json.loads((a.audit_dir / 't0-findings' / f'{t0}.json').read_text(encoding='utf-8-sig'))['findings']
        finding = next(f for f in findings if f['symbolName'] == target['symbol'] and in_target_file(f, target))
        before_same = {f['symbolName'] for f in findings if in_target_file(f, target)}
        git(a.clone, 'checkout', '-f', '-q', t0)
        original = decode_source(git(a.clone, 'show', f'{t0}:{path}'))
        (a.clone / ROOT_SOLUTION).write_text(root_solution_text((a.clone / SOLUTION).read_text(encoding='utf-8-sig'), 'Ibis.Calculeren'), encoding='utf-8')
        (a.clone / 'NuGet.Config').write_text(nuget_config_text(Path.home() / '.nuget' / 'packages'), encoding='utf-8')
        if not a.regate:
            (work / 'input.jsonl').write_text(cli_input(finding, a.clone / 'Ibis.Calculeren') + '\n', encoding='utf-8')
            ledger.reserve(ledger_path, experiment, RESERVE_PER_TARGET)
            subprocess.run(['dotnet', 'run', '--project', str(REPO / 'src/HybridLens.CLI'), '--', 'factorial-single-shot',
                            '--from', str(work / 'input.jsonl'), '--target', str(a.clone / ROOT_SOLUTION), '--model', 'gpt-5.6-sol',
                            '--runs', '3', '--grounded'], cwd=work)
        traces = list((work / 'runs').glob('*.jsonl')) if (work / 'runs').exists() else []
        records = [json.loads(line) for line in traces[0].read_text(encoding='utf-8').splitlines()] if traces else []
        unknown = not traces or any(r.get('error_status') == 'api_failure' or
                                    (r.get('raw_llm_output') is not None and (r.get('input_tokens') is None or r.get('output_tokens') is None))
                                    for r in records)
        used = RESERVE_PER_TARGET if unknown else sum((r.get('input_tokens') or 0) + (r.get('output_tokens') or 0) for r in records)
        if not a.regate:
            ledger.reconcile(ledger_path, experiment, reserved=RESERVE_PER_TARGET, used=used)
        if unknown:
            raise SystemExit(f'{tid}: missing trace or usage; the full reservation was charged and acquisition halted for inspection')
        projects = target['steps'][0]['test_projects']
        reference = {}
        for project in projects:
            reference[project] = run_tests(a.clone, a.clone / project, work, None)['outcomes']
        attempts = []
        for record in records:
            attempt = dict(run=record['run_number'], build=bool(record.get('build_passed')), resolved=False,
                           cli_resolved=bool(record.get('verified_repair_success')), new_same_type=0, api_missing=[], tests_ok=False,
                           input_tokens=record.get('input_tokens'), output_tokens=record.get('output_tokens'))
            if attempt['build'] and record.get('materialized_source_ref'):
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
                after = json.loads(scan.read_text(encoding='utf-8-sig'))['findings'] if scan.exists() else None
                attempt['resolved'] = after is not None and target_resolved(after, target)
                attempt['new_same_type'] = len({f['symbolName'] for f in after if in_target_file(f, target)} - before_same) if after is not None else 1
                if attempt['resolved']:
                    candidate = {pr: run_tests(a.clone, a.clone / pr, work, None)['outcomes'] for pr in projects}
                    required = {t for t, o in qualified(reference).items() if o == 'Passed'}
                    attempt['tests_ok'] = all(qualified(candidate).get(t) == 'Passed' for t in required)
                if not attempt['api_missing'] and attempt['tests_ok'] and attempt['new_same_type'] == 0:
                    (work / f'repaired-run{attempt["run"]}.cs').write_text(repaired, encoding='utf-8')
            attempts.append(attempt)
        accepted, flow = accept(attempts)
        if accepted is not None:
            (work / 'repaired.cs').write_bytes((work / f'repaired-run{accepted}.cs').read_bytes())
        table = [row for row in table if row['target_id'] != tid]
        table.append(dict(target_id=tid, accepted_run=accepted, flow=flow, attempts=attempts, regated=a.regate))
        table_path.write_text(json.dumps(table, indent=1), encoding='utf-8')
        print(json.dumps(dict(target=tid, accepted=accepted, flow=flow, tokens=used)), flush=True)
    if not a.regate:
        ledger.close_entry(ledger_path, experiment)


if __name__ == '__main__':
    main()
