"""Execute stratum-A replay branches (protocol v0.3, Sections 4.3 and 6.1).

Usage: python replay_run.py --manifest DIR --clone CLONE --oracle-dir DIR --out DIR --provider developer|noop|live
                            [--targets T01 T03 ...] [--branches O1 O2 O3 R1] [--repairs DIR] [--max-steps N]
developer and noop are no-cost instrument checks: replaying the developers' own change must complete every step,
and a no-op edit must fail every step. live is refused unless the frozen settings enable it.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'natural_validation'))
sys.path.insert(0, str(HERE.parent))
import patches
import replay_core as core
import replay_ledger as ledger
import replay_rate as rate
from feasibility_audit import git, run_tests
from replay_prepare import qualified

REPO = HERE.parents[2]
STUBBER = REPO / 'src/HybridLens.ChangeStub/bin/Debug/net10.0/HybridLens.ChangeStub.dll'
MAX_OUTPUT = 4096
ALLOCATION = 160_000
SYSTEM = ('Implement the requested change in the supplied C# source file. Preserve public, protected and internal APIs '
          'and all other behaviour. No test, project or dependency changes. Lines of the editable file are numbered from 1; '
          'only that file may change. Return only JSON {"edits":[{"file":"relative/path.cs","start_line":1,"end_line":2,'
          '"text":"replacement source"}]}. Coordinates are inclusive and refer to the supplied numbered source, not to '
          'earlier edits. For an insertion use end_line=start_line-1. No overlapping edits. Give complete replacement code, '
          'not placeholders. Do not add external I/O, process execution or runtime-loading capabilities.')


def number_lines(text):
    return '\n'.join(f'{i}| {line}' for i, line in enumerate(text.splitlines(), 1))


def render_prompt(step, current_text, path, diff_text):
    parts = [f'Change request:\n{step["message"]}',
             'The same change already modified these other files (read-only diff):\n' + (diff_text.strip() or '(none)'),
             f'Editable file: {json.dumps(path)}\n' + number_lines(current_text)]
    return [dict(role='system', content=SYSTEM), dict(role='user', content='\n\n'.join(parts))]


def developer_stub_response(current_text, developer_text, path):
    end = len(current_text.splitlines())
    return json.dumps(dict(edits=[dict(file=path, start_line=1, end_line=end, text=developer_text)]))


def noop_stub_response(current_text, path):
    first = current_text.splitlines()[0]
    return json.dumps(dict(edits=[dict(file=path, start_line=1, end_line=1, text=first)]))


class Workspace:
    def __init__(self, clone, oracle_dir, results_dir):
        self.clone, self.oracle_dir, self.results_dir = clone, oracle_dir, results_dir

    def checkout(self, commit, path, content):
        git(self.clone, 'checkout', '-f', '-q', commit)
        (self.clone / path).write_bytes(content.encode('utf-8'))

    def evaluate(self, step, path, developer_text):
        outcomes, errors, build_ok = {}, [], True
        for project in step['test_projects']:
            for stale in ('bin', 'obj'):
                shutil.rmtree((self.clone / project).parent / stale, ignore_errors=True)
            r = run_tests(self.clone, self.clone / project, self.results_dir, None,
                          extra=['--filter', 'FullyQualifiedName!~Reaccrual.Oracle'])
            if r['status'] == 'build_failed':
                build_ok = False
                errors.append(r['log_tail'])
                break
            outcomes[project] = r['outcomes']
        installed = []
        if build_ok:
            for oracle in step['oracle_classes']:
                sid = oracle['step_id']
                target = (self.clone / oracle['test_project']).parent / 'ReaccrualOracle' / f'Step_{sid}.cs'
                target.parent.mkdir(exist_ok=True)
                shutil.copyfile(self.oracle_dir / sid / 'submission' / f'Step_{sid}.cs', target)
                installed.append(target)
                r = run_tests(self.clone, self.clone / oracle['test_project'], self.results_dir, None, no_restore=True,
                              extra=['--filter', f'FullyQualifiedName~Reaccrual.Oracle.Step_{sid}'])
                outcomes[f'oracle/{sid}'] = r['outcomes']
                if r['status'] == 'build_failed':
                    errors.append(r['log_tail'])
                target.unlink()
        with tempfile.TemporaryDirectory() as tmp:
            reference, candidate = Path(tmp, 'reference.cs'), Path(tmp, 'candidate.cs')
            reference.write_text(developer_text, encoding='utf-8')
            shutil.copyfile(self.clone / path, candidate)
            api = json.loads(subprocess.run(['dotnet', str(STUBBER), '--missing-api', str(reference), str(candidate)],
                                            capture_output=True, text=True, check=True).stdout)['missing']
        return dict(build_ok=build_ok, api_missing=api, outcomes=qualified(outcomes), errors=errors)


def compiler_feedback(errors):
    return 'The edit does not compile. Compiler errors:\n' + '\n'.join(errors)[:8000] + '\nReturn corrected JSON edits for the same numbered source.'


def run_step(workspace, step, path, previous_text, developer_text, diff_text, provider, spent, step_dir):
    messages = render_prompt(step, previous_text, path, diff_text)
    calls, result = [], None
    for attempt in (1, 2):
        reserve = core.reservation(messages)
        if not core.may_call(spent, reserve, MAX_OUTPUT, ALLOCATION):
            result = dict(completed=False, stage='allocation')
            break
        (step_dir / f'call{attempt}-request.json').write_text(json.dumps(dict(messages=messages), indent=1), encoding='utf-8')
        text, usage = provider(messages, previous_text, developer_text, path, record=step_dir / f'call{attempt}')
        (step_dir / f'call{attempt}-response.txt').write_text(text, encoding='utf-8')
        spent += (usage.get('input_tokens') or 0) + (usage.get('output_tokens') or 0)
        calls.append(dict(attempt=attempt, reserve=reserve, **usage))
        workspace.checkout(step['commit'], path, previous_text)
        try:
            patches.apply(workspace.clone, patches.parse(text), [path])
        except (ValueError, json.JSONDecodeError) as error:
            if attempt == 1:
                messages = messages + [dict(role='assistant', content=text),
                                       dict(role='user', content=f'Invalid edit JSON: {error}. Return corrected JSON edits for the same numbered source.')]
                continue
            result = dict(completed=False, stage='invalid_patch', error=str(error))
            break
        evaluation = workspace.evaluate(step, path, developer_text)
        if not evaluation['build_ok'] and attempt == 1:
            messages = messages + [dict(role='assistant', content=text), dict(role='user', content=compiler_feedback(evaluation['errors']))]
            continue
        reference = qualified(step['reference_outcomes'])
        completed, stage = core.step_verdict(evaluation['build_ok'], evaluation['api_missing'], reference,
                                             step['fail_to_pass'], evaluation['outcomes'], spent <= ALLOCATION)
        result = dict(completed=completed, stage=stage, api_missing=evaluation['api_missing'], errors=evaluation['errors'][:3],
                      outcomes=evaluation['outcomes'], state=core.decode_source((workspace.clone / path).read_bytes()))
        break
    result['calls'] = calls
    return result, spent


def stub_provider(kind):
    def provide(messages, current_text, developer_text, path, record=None):
        text = developer_stub_response(current_text, developer_text, path) if kind == 'developer' else noop_stub_response(current_text, path)
        return text, dict(input_tokens=0, output_tokens=0, provider=f'stub-{kind}')
    return provide


def live_provider(settings, ledger_path, experiment):
    """Azure chat completions via the pilot's provider call, with ledger reservation before and reconciliation after."""
    import run_pilot
    from accounting import validate_call
    local = json.loads((REPO / 'src/HybridLens.CLI/appsettings.local.json').read_text(encoding='utf-8-sig'))['Llm']
    model = {**{k: v for k, v in local.items() if k != 'Models'}, **local['Models'][settings['model_key']]}
    if not model.get('ApiKey'):
        raise SystemExit('Existing API key unavailable')

    history = []

    def provide(messages, current_text, developer_text, path, record=None):
        reserve = core.reservation(messages) + MAX_OUTPUT

        def send():
            pause = rate.wait_needed(history, time.monotonic(), reserve, settings['rate_limit_tokens_per_minute'])
            if pause:
                time.sleep(pause)
            ledger.reserve(ledger_path, experiment, reserve)
            history.append((time.monotonic(), reserve))
            Path(f'{record}-intent.json').write_text(json.dumps(dict(status='sending', reserved_total_tokens=reserve)), encoding='utf-8')
            return run_pilot.provider_call(messages, MAX_OUTPUT, model)
        raw, elapsed, _ = rate.with_rate_limit_retry(send, release=lambda: ledger.reconcile(ledger_path, experiment, reserved=reserve, used=0),
                                                     sleep=time.sleep, attempts=3)
        Path(f'{record}-raw-response.json').write_text(json.dumps(raw, indent=1), encoding='utf-8')
        usage = raw.get('usage') or {}
        call = dict(call_id=Path(str(record)).name, model=settings['model_key'], outcome='completed', elapsed_seconds=elapsed,
                    input_tokens=usage.get('prompt_tokens'), output_tokens=usage.get('completion_tokens'),
                    cached_input_tokens=(usage.get('prompt_tokens_details') or {}).get('cached_tokens'),
                    reasoning_output_tokens=(usage.get('completion_tokens_details') or {}).get('reasoning_tokens'),
                    returned_model=raw.get('model'), finish_reason=raw['choices'][0].get('finish_reason'))
        input_tokens, output_tokens, _, _ = validate_call(call)
        if input_tokens is None or output_tokens is None:
            raise RuntimeError('Provider omitted usage: campaign halted for reconciliation')
        ledger.reconcile(ledger_path, experiment, reserved=reserve, used=input_tokens + output_tokens)
        return raw['choices'][0]['message'].get('content') or '', call
    return provide


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--clone', type=Path, required=True)
    p.add_argument('--oracle-dir', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--provider', choices=['developer', 'noop', 'live'], required=True)
    p.add_argument('--targets', nargs='*')
    p.add_argument('--branches', nargs='*', default=['O1'])
    p.add_argument('--max-steps', type=int)
    p.add_argument('--freeze', type=Path)
    a = p.parse_args()
    if a.out.exists():
        raise SystemExit('Output exists: use a new run directory')
    manifest = json.loads((a.manifest / 'manifest.json').read_text(encoding='utf-8'))
    ledger_path = HERE.parent / 'budget-ledger.json'
    experiment = None
    if a.provider == 'live':
        settings = json.loads((HERE / 'replay_settings.json').read_text(encoding='utf-8'))
        if not settings['live_execution_enabled']:
            raise SystemExit('Live execution is not enabled: freeze, ceiling authorisation and review gates are pending.')
        from replay_freeze import changed_files
        if not a.freeze or not a.freeze.exists():
            raise SystemExit('Live execution requires the freeze record (--freeze)')
        frozen = json.loads(a.freeze.read_text(encoding='utf-8'))
        drift = changed_files(frozen['inputs']) + changed_files(frozen['code'])
        if drift or Path(frozen['manifest']).resolve() != a.manifest.resolve():
            raise SystemExit(f'Frozen inputs or code changed: {drift[:5]}')
        experiment = f'reaccrual-replay-{a.out.name}'
        ledger.open_entry(ledger_path, experiment, a.out)
        provider = live_provider(settings, ledger_path, experiment)
    else:
        provider = stub_provider(a.provider)
    workspace = Workspace(a.clone, a.oracle_dir, a.out / '_trx')
    (a.out / '_trx').mkdir(parents=True)
    selected = [t for t in manifest['targets'] if not a.targets or t['target_id'] in a.targets]
    summary = []
    for target in selected:
        path = target['path']
        branches = core.branch_order(manifest['seed'], target['target_id'], [(b[0], int(b[1:])) for b in a.branches])
        states = {b: core.decode_source(git(a.clone, 'show', f"{target['t0']}:{path}")) for b in branches}
        spent = {b: 0 for b in branches}
        active = set(branches)
        for step in target['steps'][:a.max_steps]:
            developer_text = core.decode_source(git(a.clone, 'show', f"{step['commit']}:{path}"))
            diff_text = (a.manifest / 'diffs' / step['diff']).read_text(encoding='utf-8', errors='replace')
            for b in branches:
                if b not in active:
                    continue
                step_dir = a.out / target['target_id'] / f'{b[0]}{b[1]}' / f"S{step['step']}"
                step_dir.mkdir(parents=True)
                started = time.monotonic()
                result, spent[b] = run_step(workspace, step, path, states[b], developer_text, diff_text, provider, spent[b], step_dir)
                result['seconds'] = round(time.monotonic() - started, 1)
                state = result.pop('state', None)
                if result['completed']:
                    states[b] = state
                    (step_dir / 'state.cs').write_text(state, encoding='utf-8')
                else:
                    active.discard(b)
                (step_dir / 'result.json').write_text(json.dumps(result, indent=1), encoding='utf-8')
                summary.append(dict(target=target['target_id'], branch=f'{b[0]}{b[1]}', step=step['step'],
                                    completed=result['completed'], stage=result.get('stage'), seconds=result['seconds']))
                print(json.dumps(summary[-1]), flush=True)
    (a.out / 'summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    if experiment:
        ledger.close_entry(ledger_path, experiment)


if __name__ == '__main__':
    main()
