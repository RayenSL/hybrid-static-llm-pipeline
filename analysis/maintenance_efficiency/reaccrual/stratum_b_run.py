"""Execute stratum-B corpus branches O1 and R1 (protocol v0.3, Sections 5 and 6.1; amendment 0.3.4).

Usage: python stratum_b_run.py --packets DIR --out DIR --provider reference|noop|live [--targets GC-02 ...] [--freeze F] [--resume]
       python stratum_b_run.py --packets DIR --write-freeze F
reference and noop are no-cost instrument checks: writing the step reference must complete every step, and a no-op edit
must fail every step. Only targets that passed admission and R2 review (accept or edit) are run.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import replay_run as rr
from replay_run import patches, core, ledger
from admit_stratum_b import CHECK, HEADER, FOOTER, PROBE

REPO = HERE.parents[2]
SYSTEM = rr.SYSTEM
DECLARATION = re.compile(r'\b(?:class|interface|enum|struct|record)\s+([A-Za-z_]\w*)')
IDENTIFIER = re.compile(r'[A-Za-z_]\w*')
SEED = 'reaccrual-v0.3-stratum-b'


def closure_files(original_text, supporting):
    used = set(IDENTIFIER.findall(original_text))
    return sorted(name for name, text in supporting.items() if used & set(DECLARATION.findall(text)))


def render_prompt(requirement, current_text, path, context, system=SYSTEM):
    parts = [f'Change request:\n{requirement}']
    if context:
        parts.append('Read-only context files:\n' + '\n\n'.join(f'// {name}\n{text}' for name, text in sorted(context.items())))
    parts.append(f'Editable file: {json.dumps(path)}\n' + rr.number_lines(current_text))
    return [dict(role='system', content=system), dict(role='user', content='\n\n'.join(parts))]


def cases(body):
    return {name: flag == 'true' for name, flag in CHECK.findall(body)}


def required_cases(bodies, k, superseded):
    fail_to_pass = sorted(name for name, acceptance in cases(bodies[k]).items() if acceptance)
    required = {name for j in range(1, k + 1) for name in cases(bodies[j])} - superseded
    return fail_to_pass, required


def test_file(bodies, k, helpers):
    return HEADER + ''.join(bodies[j] for j in range(1, k + 1)) + FOOTER + helpers


def verdict(build_ok, api_missing, outcomes, fail_to_pass, required, within_allocation):
    if not build_ok:
        return False, 'build'
    if api_missing:
        return False, 'api'
    # Hidden tests that do not compile against the candidate mean the requested API is missing; their errors are never shown.
    if outcomes is None:
        return False, 'fail_to_pass'
    return core.step_verdict(True, [], {c: 'Passed' for c in required}, fail_to_pass, outcomes, within_allocation)


# Bytes, not write_text: Windows newline translation would turn CRLF into CR CR LF and shift every patch coordinate.
def apply_edits(previous_text, path, response):
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / path).parent.mkdir(parents=True)
        (Path(tmp) / path).write_bytes(previous_text.encode('utf-8'))
        patches.apply(Path(tmp), patches.parse(response), [path])
        return core.decode_source((Path(tmp) / path).read_bytes())


def probe(baseline, candidate_text, tests_text):
    with tempfile.TemporaryDirectory() as tmp:
        candidate, tests, out = Path(tmp, 'candidate.cs'), Path(tmp, 'tests.cs'), Path(tmp, 'out.json')
        candidate.write_bytes(candidate_text.encode('utf-8'))
        tests.write_bytes(tests_text.encode('utf-8'))
        subprocess.run(['dotnet', str(PROBE), '--probe', str(baseline), str(candidate), str(tests), str(out)], capture_output=True, timeout=300)
        raw = json.loads(out.read_text(encoding='utf-8-sig')) if out.exists() else dict(build_passed=False, errors=['probe produced no output'])
    if not raw.get('build_passed'):
        return False, raw.get('errors', []), None
    return True, [], {c['id']: 'Passed' if c['passed'] else 'Failed' for c in raw['cases']}


def missing_api(previous_text, candidate_text):
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, 'a.cs').write_bytes(previous_text.encode('utf-8'))
        Path(tmp, 'b.cs').write_bytes(candidate_text.encode('utf-8'))
        return json.loads(subprocess.run(['dotnet', str(rr.STUBBER), '--missing-api', str(Path(tmp, 'a.cs')), str(Path(tmp, 'b.cs'))],
                                         capture_output=True, text=True, check=True).stdout)['missing']


def gates(baseline, previous_text, candidate, bodies, k, superseded, helpers, within_allocation, built=None):
    build_ok, errors = built if built else probe(baseline, candidate, HEADER + FOOTER)[:2]
    fail_to_pass, required = required_cases(bodies, k, superseded)
    api = missing_api(previous_text, candidate) if build_ok else []
    outcomes = probe(baseline, candidate, test_file(bodies, k, helpers))[2] if build_ok and not api else None
    completed, stage = verdict(build_ok, api, outcomes, fail_to_pass, required, within_allocation)
    return dict(completed=completed, stage=stage, api_missing=api, errors=errors[:5], outcomes=outcomes)


def run_step(packet, k, bodies, superseded, helpers, baseline, path, previous_text, reference_text, context, provider, spent, step_dir,
             system=SYSTEM):
    requirement = (packet / 'steps' / f'S{k}' / 'requirement.md').read_text(encoding='utf-8').strip()
    messages = render_prompt(requirement, previous_text, path, context, system)
    calls, result = [], None
    for attempt in (1, 2):
        reserve = core.reservation(messages)
        if not core.may_call(spent, reserve, rr.MAX_OUTPUT, rr.ALLOCATION):
            result = dict(completed=False, stage='allocation')
            break
        (step_dir / f'call{attempt}-request.json').write_text(json.dumps(dict(messages=messages), indent=1), encoding='utf-8')
        text, usage = provider(messages, previous_text, reference_text, path, record=step_dir / f'call{attempt}')
        (step_dir / f'call{attempt}-response.txt').write_text(text, encoding='utf-8')
        spent += (usage.get('input_tokens') or 0) + (usage.get('output_tokens') or 0)
        calls.append(dict(attempt=attempt, reserve=reserve, **usage))
        try:
            candidate = apply_edits(previous_text, path, text)
        except (ValueError, json.JSONDecodeError) as error:
            if attempt == 1:
                messages = messages + [dict(role='assistant', content=text),
                                       dict(role='user', content=f'Invalid edit JSON: {error}. Return corrected JSON edits for the same numbered source.')]
                continue
            result = dict(completed=False, stage='invalid_patch', error=str(error))
            break
        build_ok, errors, _ = probe(baseline, candidate, HEADER + FOOTER)
        if not build_ok and attempt == 1:
            messages = messages + [dict(role='assistant', content=text), dict(role='user', content=rr.compiler_feedback(errors))]
            continue
        result = dict(gates(baseline, previous_text, candidate, bodies, k, superseded, helpers, spent <= rr.ALLOCATION, (build_ok, errors)),
                      state=candidate)
        break
    result['calls'] = calls
    return result, spent


def selected_targets(packets, only, unreviewed=False):
    decisions_path = packets / 'review-decisions.json'
    decisions = json.loads(decisions_path.read_text(encoding='utf-8')) if decisions_path.exists() else {}
    chosen = []
    for folder in sorted(p for p in packets.iterdir() if (p / 'admission.json').exists()):
        admitted = json.loads((folder / 'admission.json').read_text(encoding='utf-8')).get('admitted')
        reviewed = decisions.get(folder.name, {}).get('decision') in ('accept', 'edit')
        if admitted and (reviewed or unreviewed) and (not only or folder.name in only):
            chosen.append(folder)
    return chosen


def packet_inputs(packets, folders, pairs):
    files = [packets / 'review-decisions.json']
    for folder in folders:
        files += sorted(f for f in folder.rglob('*') if f.is_file() and f.name not in ('author-check.json',))
        pair = pairs[folder.name]
        files += [(ROOT / pair['baseline_path']).resolve(), (ROOT / pair['repaired_path']).resolve()]
    return files


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--packets', type=Path, required=True)
    p.add_argument('--out', type=Path)
    p.add_argument('--provider', choices=['reference', 'noop', 'live'])
    p.add_argument('--targets', nargs='*')
    p.add_argument('--freeze', type=Path)
    p.add_argument('--write-freeze', type=Path)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--unreviewed', action='store_true', help='stub instrument checks only: also run admitted targets R2 has not reviewed')
    a = p.parse_args()
    if a.unreviewed and (a.provider == 'live' or a.write_freeze):
        raise SystemExit('--unreviewed is for stub instrument checks only')
    from replay_freeze import hash_files, changed_files, CODE
    pairs = {x['target_id']: x for x in json.loads((ROOT / 'generated' / 'campaign.json').read_text(encoding='utf-8'))['pairs']}
    folders = selected_targets(a.packets, a.targets, a.unreviewed)
    if a.write_freeze:
        if a.write_freeze.exists():
            raise SystemExit('Freeze record exists; a freeze is never overwritten')
        record = dict(schema_version='reaccrual-stratum-b-freeze/0.1', targets=[f.name for f in folders], seed=SEED,
                      settings=rr.SETTINGS, inputs=hash_files(packet_inputs(a.packets, folders, pairs)), code=hash_files(CODE))
        a.write_freeze.write_text(json.dumps(record, indent=1), encoding='utf-8')
        print(f'Frozen: {len(folders)} targets, {len(record["inputs"])} inputs, {len(record["code"])} code files')
        return
    if not (a.out and a.provider):
        raise SystemExit('--out and --provider are required for a run')
    if a.out.exists() and not a.resume:
        raise SystemExit('Output exists: use a new run directory, or --resume to continue it')
    ledger_path = ROOT / 'budget-ledger.json'
    prefix = f'reaccrual-stratum-b-{a.out.name}'
    skip, moved = rr.prepare_resume(a.out, [f.name for f in folders]) if a.out.exists() else (set(), [])
    experiment = None
    if a.provider == 'live':
        if not rr.SETTINGS['live_execution_enabled']:
            raise SystemExit('Live execution is not enabled')
        if not a.freeze or not a.freeze.exists():
            raise SystemExit('Live execution requires the stratum-B freeze record (--freeze)')
        frozen = json.loads(a.freeze.read_text(encoding='utf-8'))
        drift = changed_files(frozen['inputs']) + changed_files(frozen['code'])
        if drift or frozen['targets'] != [f.name for f in folders]:
            raise SystemExit(f'Frozen inputs, code or targets changed: {drift[:5]}')
        ledger.recover_interrupted(ledger_path, f'interrupted {prefix} run, resumed', prefix=prefix)
        previous = sum(1 for e in json.loads(ledger_path.read_text(encoding='utf-8'))['entries'] if e['experiment'].startswith(prefix))
        experiment = f'{prefix}-{previous + 1}'
        ledger.open_entry(ledger_path, experiment, a.out)
        provider = rr.live_provider(rr.SETTINGS, ledger_path, experiment)
    else:
        provider = rr.stub_provider('developer' if a.provider == 'reference' else 'noop')
    if moved:
        print(json.dumps(dict(moved_partial_targets=moved)), flush=True)
    a.out.mkdir(parents=True, exist_ok=True)
    summary_path = a.out / 'summary.json'
    summary = [r for r in (json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else []) if r['target'] in skip]
    for packet in folders:
        tid = packet.name
        if tid in skip:
            continue
        pair = pairs[tid]
        baseline = (ROOT / pair['baseline_path']).resolve()
        path = pair['relative_file']
        original = core.decode_source((packet / 'original.cs').read_bytes())
        states = {'O1': original, 'R1': core.decode_source((ROOT / pair['repaired_path']).resolve().read_bytes())}
        supporting = {f.name: core.decode_source(f.read_bytes()) for f in sorted((packet / 'supporting').glob('*.cs'))}
        context = {name: supporting[name] for name in closure_files(original, supporting)}
        helpers = (packet / 'helpers.cs').read_text(encoding='utf-8') if (packet / 'helpers.cs').exists() else ''
        bodies = {k: (packet / 'steps' / f'S{k}' / 'tests.cs').read_text(encoding='utf-8') for k in range(1, 5)}
        branches = [f'{b}{n}' for b, n in core.branch_order(SEED, tid, [('O', 1), ('R', 1)])]
        spent, active, superseded = {b: 0 for b in branches}, set(branches), set()
        for k in range(1, 5):
            superseded |= {line.strip() for line in (packet / 'steps' / f'S{k}' / 'superseded.txt').read_text(encoding='utf-8').splitlines() if line.strip()}
            reference_text = core.decode_source((packet / 'steps' / f'S{k}' / 'reference.cs').read_bytes())
            for b in branches:
                if b not in active:
                    continue
                step_dir = a.out / tid / b / f'S{k}'
                step_dir.mkdir(parents=True)
                started = time.monotonic()
                result, spent[b] = run_step(packet, k, bodies, superseded, helpers, baseline, path, states[b], reference_text,
                                            context, provider, spent[b], step_dir)
                result['seconds'] = round(time.monotonic() - started, 1)
                state = result.pop('state', None)
                if result['completed']:
                    states[b] = state
                    (step_dir / 'state.cs').write_bytes(state.encode('utf-8'))
                else:
                    active.discard(b)
                (step_dir / 'result.json').write_text(json.dumps(result, indent=1), encoding='utf-8')
                summary.append(dict(target=tid, branch=b, step=k, completed=result['completed'], stage=result.get('stage'), seconds=result['seconds']))
                summary_path.write_text(json.dumps(summary, indent=1), encoding='utf-8')
                print(json.dumps(summary[-1]), flush=True)
        (a.out / tid / 'complete.json').write_text(json.dumps(dict(branches=branches, context_files=sorted(context))), encoding='utf-8')
    summary_path.write_text(json.dumps(summary, indent=1), encoding='utf-8')
    if experiment:
        ledger.close_entry(ledger_path, experiment)


if __name__ == '__main__':
    main()
