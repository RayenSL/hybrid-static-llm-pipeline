"""Shadow-loop study on industrial history (protocol v0.5, Sections 4 to 6). Prepare makes no model calls; run makes them only with --provider live.

  python v05_run.py prepare --frame F --oracle-rows R --introductions DIR --clone CLONE --out DIR
  python v05_run.py freeze  --manifest DIR --out FILE
  python v05_run.py run     --manifest DIR --clone CLONE --out DIR --provider identity|truncate|revert|live [--freeze F] [--units U01 ...] [--resume]

The clone is force-checked-out and cleaned per unit and must be a disposable local clone. The stub providers check the instrument: identity
must fail the resolved gate on every unit, truncate must fail the build gate, and revert (the parent version of the file) is a positive
control that can succeed on units whose commit only changed method bodies.
"""
import argparse
import collections
import json
import subprocess
import time
from pathlib import Path

import feasibility_audit as fa
import oracle_pilot as op
import stratum_b_run as b
import v04_run as v04
from acquire_repairs import ROOT_SOLUTION, SOLUTION, root_solution_text
from replay_prepare import qualified
from stratum_b_run import rr, core, ledger, ROOT, HERE

REPO = HERE.parents[2]
CLI_DLL = REPO / 'src/HybridLens.CLI/bin/Debug/net10.0/HybridLens.CLI.dll'
SEED = 'reaccrual-v0.5'
ALLOCATION = 120_000
TYPES = ('godClass', 'longMethod')
GATES = ('build', 'api', 'tests', 'resolved', 'no_new_debt')


def unit_id(index):
    return f'U{index + 1:02d}'


def layer(path):
    parts = path.split('/')
    top = parts[1] if len(parts) > 2 and parts[0] == 'Ibis.Calculeren' else parts[0]
    top = top.lower()
    return 'ui' if top == 'ui' else 'business' if top in ('bl', 'business') else 'data' if top.startswith('data') else 'other'


def in_file(finding, path):
    # Folder case follows whichever commit the clone last had checked out, so paths are compared without case.
    return finding['type'] in TYPES and ('Ibis.Calculeren/' + finding['filePath'].replace('\\', '/')).lower() == path.lower()


def file_findings(findings, path):
    return [f for f in findings if in_file(f, path)]


def unit_findings(before, symbols, path):
    """The audit's symbols that the full detector also reports in the file at the post-commit state, and those it does not."""
    reproduced = [f for f in file_findings(before, path) if f['type'] == 'longMethod' and f['symbolName'] in symbols]
    found = {f['symbolName'] for f in reproduced}
    return reproduced, [s for s in symbols if s not in found]


def required_tests(outcomes):
    return {name: outcome for name, outcome in outcomes.items() if outcome == 'Passed'}


def verdict(build_ok, api_missing, required, outcomes, unit_symbols, before, after, path):
    """Gates of protocol Section 4.3, in order; a gate after the first failure is not evaluated (None)."""
    gates = dict.fromkeys(GATES)
    gates['build'] = bool(build_ok)
    if gates['build']:
        gates['api'] = not api_missing
    if gates['api']:
        gates['tests'] = all((outcomes or {}).get(name) == 'Passed' for name in required)
    before_keys = {(f['type'], f['symbolName']) for f in file_findings(before, path)}
    after_keys = {(f['type'], f['symbolName']) for f in file_findings(after or [], path)}
    unit_keys = {('longMethod', s) for s in unit_symbols}
    if gates['tests']:
        gates['resolved'] = not (unit_keys & after_keys)
    if gates['resolved']:
        gates['no_new_debt'] = not (after_keys - before_keys)
    failed = next((g for g in GATES if gates[g] is False), None)
    return dict(success=failed is None and all(gates[g] for g in GATES), stage=failed, gates=gates, tests_applicable=bool(required),
                success_without_new_debt=all(gates[g] for g in GATES[:4]), new_debt=sorted(after_keys - before_keys),
                remaining=sorted(unit_keys & after_keys))


def truncated(text):
    return '\n'.join(text.rstrip().split('\n')[:-1])


STUBS = dict(identity=lambda current, parent, path: rr.noop_stub_response(current, path),
             truncate=lambda current, parent, path: rr.developer_stub_response(current, truncated(current), path),
             revert=lambda current, parent, path: rr.developer_stub_response(current, parent, path))


def stub_provider(kind):
    def provide(messages, current_text, parent_text, path, record=None):
        return STUBS[kind](current_text, parent_text, path), dict(input_tokens=0, output_tokens=0, provider=f'stub-{kind}')
    return provide


def prepare_workspace(clone, commit):
    fa.git(clone, 'checkout', '-f', '-q', commit)
    fa.git(clone, 'clean', '-ffdxq')
    sln = clone / SOLUTION
    (clone / ROOT_SOLUTION).write_text(root_solution_text(sln.read_text(encoding='utf-8-sig'), 'Ibis.Calculeren'), encoding='utf-8')
    (clone / 'NuGet.Config').write_text(op.nuget_config_disabling(op.clone_missing_sources(clone)), encoding='utf-8')


def build(clone):
    code, log, seconds = fa.run(['dotnet', 'build', str(clone / ROOT_SOLUTION), '--nologo', '-v', 'q', '-p:TreatWarningsAsErrors=false', '-p:NuGetAudit=false'],
                                clone, timeout=1500)
    errors = sorted({line.strip().replace(str(clone) + chr(92), '') for line in log.splitlines() if ': error ' in line})
    return code == 0, errors


def scan(clone, output):
    subprocess.run(['dotnet', str(CLI_DLL), 'analyse', '--target', str(clone / SOLUTION), '--dry-run', '--format', 'json', '--severity', 'Warning',
                    '--output', str(output)], capture_output=True, cwd=REPO)
    if not output.exists():
        raise SystemExit(f'Detector produced no output: {output}')
    return json.loads(output.read_text(encoding='utf-8-sig'))['findings']


def run_oracle(clone, projects, results_dir, no_restore):
    outcomes, statuses = {}, {}
    for project in projects:
        r = fa.run_tests(clone, clone / project, results_dir, None, no_restore=no_restore)
        statuses[project] = r['status']
        outcomes[Path(project).stem] = r['outcomes']
    return qualified(outcomes), statuses


def commit_message(clone, commit):
    out = subprocess.run(['git', '-C', str(clone), 'log', '-1', '--format=%B', commit], capture_output=True, text=True, encoding='utf-8', errors='replace', check=True).stdout
    return out.strip()


def git_text(clone, commit, path):
    raw = subprocess.run(['git', '-C', str(clone), 'show', f'{commit}:{path}'], capture_output=True)
    return core.decode_source(raw.stdout) if raw.returncode == 0 else ''


def prepare(a):
    rows = {(r['commit'], r['symbol']): r for r in json.loads(a.oracle_rows.read_text(encoding='utf-8'))}
    frame = json.loads(a.frame.read_text(encoding='utf-8'))['candidates']
    audit = {}
    for line in (a.introductions / 'introductions.jsonl').read_text(encoding='utf-8').splitlines():
        record = json.loads(line)
        audit[record['commit']] = record
    a.out.mkdir(parents=True, exist_ok=True)
    fa.EXCLUDED.update(op.EXCLUDED)
    units = []
    built = [c for c in frame if rows[c['commit'], c['symbol']]['solution_built']]
    for index, candidate in enumerate(built):
        uid, commit, path = unit_id(index), candidate['commit'], candidate['file']
        folder = a.out / uid
        if (folder / 'unit.json').exists():
            units.append(json.loads((folder / 'unit.json').read_text(encoding='utf-8')))
            continue
        folder.mkdir(exist_ok=True)
        symbols = sorted({f['symbol'] for f in audit[commit]['long_method'] if f['kind'] == 'genuine' and f['file'] == path})
        prepare_workspace(a.clone, commit)
        ok, errors = build(a.clone)
        before = scan(a.clone, folder / 'baseline-scan.json') if ok else []
        reproduced, missing = unit_findings(before, symbols, path)
        projects = [str(p.relative_to(a.clone)) for p in fa.test_projects_for(a.clone, path, [])] if ok else []
        outcomes, statuses = run_oracle(a.clone, projects, folder, no_restore=True) if ok else ({}, {})
        required = required_tests(outcomes)
        (folder / 'post.cs').write_bytes(git_text(a.clone, commit, path).encode('utf-8'))
        (folder / 'parent.cs').write_bytes(git_text(a.clone, audit[commit]['parent'], path).encode('utf-8'))
        (folder / 'required-tests.json').write_text(json.dumps(required, indent=1, sort_keys=True), encoding='utf-8')
        unit = dict(unit_id=uid, commit=commit, parent=audit[commit]['parent'], file=path, stratum=candidate['stratum'], layer=layer(path),
                    symbols=symbols, reproduced=[f['symbolName'] for f in reproduced], missing=missing,
                    eligible=ok and bool(reproduced), built=ok, message=commit_message(a.clone, commit), test_projects=projects,
                    test_statuses=statuses, required_count=len(required), tests_applicable=bool(required), date=candidate['date'])
        (folder / 'unit.json').write_text(json.dumps(unit, indent=1), encoding='utf-8')
        units.append(unit)
        print(json.dumps(dict(unit=uid, eligible=unit['eligible'], required=len(required), reproduced=len(reproduced), missing=len(missing))), flush=True)
    (a.out / 'manifest.json').write_text(json.dumps(dict(seed=SEED, units=[u['unit_id'] for u in units]), indent=1), encoding='utf-8')
    funnel = dict(units=len(units), eligible=sum(u['eligible'] for u in units), with_oracle=sum(u['eligible'] and u['tests_applicable'] for u in units),
                  by_layer=dict(collections.Counter(u['layer'] for u in units if u['eligible'])))
    (a.out / 'funnel.json').write_text(json.dumps(funnel, indent=1), encoding='utf-8')
    print(json.dumps(funnel, indent=1))


def load_unit(manifest, uid):
    folder = manifest / uid
    unit = json.loads((folder / 'unit.json').read_text(encoding='utf-8'))
    unit['post'] = core.decode_source((folder / 'post.cs').read_bytes())
    unit['parent_text'] = core.decode_source((folder / 'parent.cs').read_bytes())
    unit['before'] = json.loads((folder / 'baseline-scan.json').read_text(encoding='utf-8-sig'))['findings']
    unit['required'] = json.loads((folder / 'required-tests.json').read_text(encoding='utf-8'))
    return unit


def run_unit(unit, clone, provider, out):
    path, post, spent, calls, result = unit['file'], unit['post'], 0, [], None
    findings, _ = unit_findings(unit['before'], unit['symbols'], path)
    prepare_workspace(clone, unit['commit'])
    messages = v04.quality_prompt(unit['message'], post, path, {}, findings)
    started = time.monotonic()
    for attempt in (1, 2):
        reserve = core.reservation(messages)
        if not core.may_call(spent, reserve, rr.MAX_OUTPUT, ALLOCATION):
            result = dict(stage='allocation', success=False)
            break
        (out / f'call{attempt}-request.json').write_text(json.dumps(dict(messages=messages), indent=1), encoding='utf-8')
        text, usage = provider(messages, post, unit['parent_text'], path, record=out / f'call{attempt}')
        (out / f'call{attempt}-response.txt').write_text(text, encoding='utf-8')
        spent += (usage.get('input_tokens') or 0) + (usage.get('output_tokens') or 0)
        calls.append(dict(attempt=attempt, reserve=reserve, **usage))
        try:
            candidate = b.apply_edits(post, path, text)
        except (ValueError, json.JSONDecodeError) as error:
            if attempt == 1:
                messages = messages + [dict(role='assistant', content=text), dict(role='user', content=f'Invalid edit JSON: {error}. Return corrected JSON edits for the same numbered source.')]
                continue
            result = dict(stage='invalid_patch', success=False, error=str(error))
            break
        (clone / path).write_bytes(candidate.encode('utf-8'))
        (out / 'candidate.cs').write_bytes(candidate.encode('utf-8'))
        ok, errors = build(clone)
        if not ok and attempt == 1:
            messages = messages + [dict(role='assistant', content=text), dict(role='user', content=rr.compiler_feedback(errors))]
            continue
        api = b.missing_api(post, candidate) if ok else []
        outcomes, statuses, after = None, {}, None
        if ok and not api:
            outcomes, statuses = run_oracle(clone, unit['test_projects'], out, no_restore=True)
            if all(outcomes.get(name) == 'Passed' for name in unit['required']):
                after = scan(clone, out / 'scan.json')
        result = dict(verdict(ok, api, unit['required'], outcomes, unit['reproduced'], unit['before'], after, path),
                      api_missing=api, build_errors=errors[:3], test_statuses=statuses, attempts=attempt)
        break
    result['calls'] = calls
    result['tokens'] = spent
    result['seconds'] = round(time.monotonic() - started, 1)
    return result


def freeze_inputs(manifest):
    uids = json.loads((manifest / 'manifest.json').read_text(encoding='utf-8'))['units']
    files = [manifest / 'manifest.json', HERE / 'PROTOCOL-v0.5.md']
    for uid in uids:
        files += [manifest / uid / n for n in ('unit.json', 'post.cs', 'parent.cs', 'baseline-scan.json', 'required-tests.json')]
    return files


def run(a):
    from replay_freeze import changed_files
    manifest_ids = json.loads((a.manifest / 'manifest.json').read_text(encoding='utf-8'))['units']
    units = [u for u in manifest_ids if not a.units or u in a.units]
    ledger_path = ROOT / 'budget-ledger.json'
    prefix = f'reaccrual-v05-{a.out.name}'
    if a.out.exists() and not a.resume:
        raise SystemExit('Output exists: use a new run directory, or --resume to continue it')
    skip, moved = rr.prepare_resume(a.out, units) if a.out.exists() else (set(), [])
    experiment = None
    if a.provider == 'live':
        if not rr.SETTINGS['live_execution_enabled']:
            raise SystemExit('Live execution is not enabled')
        if not a.freeze or not a.freeze.exists():
            raise SystemExit('Live execution requires the v0.5 freeze record (--freeze)')
        frozen = json.loads(a.freeze.read_text(encoding='utf-8'))
        drift = changed_files(frozen['inputs']) + changed_files(frozen['code'])
        if drift:
            raise SystemExit(f'Frozen inputs or code changed: {drift[:5]}')
        ledger.recover_interrupted(ledger_path, f'interrupted {prefix} run, resumed', prefix=prefix)
        previous = sum(1 for e in json.loads(ledger_path.read_text(encoding='utf-8'))['entries'] if e['experiment'].startswith(prefix))
        experiment = f'{prefix}-{previous + 1}'
        ledger.open_entry(ledger_path, experiment, a.out)
        provider = rr.live_provider(rr.SETTINGS, ledger_path, experiment)
    else:
        provider = stub_provider(a.provider)
    if moved:
        print(json.dumps(dict(moved_partial_units=moved)), flush=True)
    a.out.mkdir(parents=True, exist_ok=True)
    summary_path = a.out / 'summary.json'
    summary = [r for r in (json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else []) if r['unit'] in skip]
    for uid in units:
        if uid in skip:
            continue
        unit = load_unit(a.manifest, uid)
        folder = a.out / uid
        folder.mkdir(parents=True)
        if not unit['eligible']:
            result = dict(stage='ineligible', success=False, calls=[], tokens=0, seconds=0)
        else:
            result = run_unit(unit, a.clone, provider, folder)
        (folder / 'result.json').write_text(json.dumps(result, indent=1), encoding='utf-8')
        (folder / 'complete.json').write_text('{}', encoding='utf-8')
        summary.append(dict(unit=uid, stratum=unit['stratum'], layer=unit['layer'], success=result['success'], stage=result['stage'],
                            tests_applicable=result.get('tests_applicable'), calls=len(result['calls']), tokens=result['tokens'], seconds=result['seconds']))
        summary_path.write_text(json.dumps(summary, indent=1), encoding='utf-8')
        print(json.dumps(summary[-1]), flush=True)
    if experiment:
        ledger.close_entry(ledger_path, experiment)
    counts = collections.Counter((r['stage'] if not r['success'] else 'success') for r in summary)
    print(json.dumps(dict(units=len(summary), outcomes=dict(counts)), indent=1))


def write_freeze(a):
    from replay_freeze import CODE, hash_files
    if a.out.exists():
        raise SystemExit('Freeze record exists; a freeze is never overwritten')
    record = dict(schema_version='reaccrual-v0.5-freeze/0.1', seed=SEED, allocation=ALLOCATION, settings=rr.SETTINGS,
                  inputs=hash_files(freeze_inputs(a.manifest)), code=hash_files(CODE))
    a.out.write_text(json.dumps(record, indent=1), encoding='utf-8')
    print(f'Frozen: {len(record["inputs"])} inputs, {len(record["code"])} code files')


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('prepare')
    s.add_argument('--frame', type=Path, required=True)
    s.add_argument('--oracle-rows', type=Path, required=True)
    s.add_argument('--introductions', type=Path, required=True)
    s.add_argument('--clone', type=Path, required=True)
    s.add_argument('--out', type=Path, required=True)
    s = sub.add_parser('freeze')
    s.add_argument('--manifest', type=Path, required=True)
    s.add_argument('--out', type=Path, required=True)
    s = sub.add_parser('run')
    s.add_argument('--manifest', type=Path, required=True)
    s.add_argument('--clone', type=Path, required=True)
    s.add_argument('--out', type=Path, required=True)
    s.add_argument('--provider', choices=[*STUBS, 'live'], required=True)
    s.add_argument('--freeze', type=Path)
    s.add_argument('--units', nargs='*')
    s.add_argument('--resume', action='store_true')
    a = p.parse_args()
    {'prepare': prepare, 'freeze': write_freeze, 'run': run}[a.command](a)


if __name__ == '__main__':
    main()
