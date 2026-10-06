"""Execute the protocol v0.4 arms O-N, R-N, R-D and R-L on the frozen stratum-B tasks (PROTOCOL-v0.4.md).

Usage: python v04_run.py --packets DIR --out DIR --provider reference|noop|live [--targets GC-02 ...] [--freeze F] [--resume]
       python v04_run.py --packets DIR --write-freeze F
With the reference provider, the R-L quality call returns its input unchanged, which exercises the loop at no cost.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

import messages_provider
import stratum_b_run as b
from stratum_b_run import rr, core, ledger, ROOT, HERE
from stratum_b_analyze import scan

REPO = HERE.parents[2]
SEED = 'reaccrual-v0.4'
TYPES = ('godClass', 'longMethod')
GUIDANCE = ('Keep the design clean while you implement the change: keep methods short and focused on one task, keep each class '
            'cohesive, and put new behaviour in the class that owns that responsibility instead of growing an existing large method '
            'or class. Prefer extending the existing structure over adding branches to a long method.')
QUALITY_INSTRUCTION = ('The static analyser reports the following design findings introduced by your change. Restructure the editable '
                       'file to remove them. Preserve all behaviour, the public API and the requirement just implemented; edit only the '
                       'given file.')
ARMS = {'O-N': dict(start='original', guidance=False, loop=False),
        'R-N': dict(start='repair', guidance=False, loop=False),
        'R-D': dict(start='repair', guidance=True, loop=False),
        'R-L': dict(start='repair', guidance=False, loop=True)}


def system_for(arm):
    return f'{b.SYSTEM}\n\n{GUIDANCE}' if ARMS[arm]['guidance'] else b.SYSTEM


def arm_order(target_id):
    return sorted(ARMS, key=lambda arm: hashlib.sha256(f'{SEED}|{target_id}|{arm}'.encode()).hexdigest())


def in_file(finding, path):
    return finding['type'] in TYPES and finding['filePath'].replace('\\', '/') == path


def new_findings(before, after, path):
    known = {(f['type'], f['symbolName']) for f in before if in_file(f, path)}
    return [f for f in after if in_file(f, path) and (f['type'], f['symbolName']) not in known]


def describe(finding):
    kind = 'GodClass' if finding['type'] == 'godClass' else 'LongMethod'
    metrics = ', '.join(f'{k}={v}' for k, v in (finding.get('metrics') or {}).items())
    return f"{kind} {finding['symbolName']} at line {finding.get('line')}: {metrics}"


def quality_prompt(requirement, candidate, path, context, findings):
    parts = [f'Change request just implemented:\n{requirement}',
             'Static-analysis findings:\n' + '\n'.join(f'- {describe(f)}' for f in findings),
             QUALITY_INSTRUCTION]
    if context:
        parts.append('Read-only context files:\n' + '\n\n'.join(f'// {name}\n{text}' for name, text in sorted(context.items())))
    parts.append(f'Editable file: {json.dumps(path)}\n' + rr.number_lines(candidate))
    return [dict(role='system', content=b.SYSTEM), dict(role='user', content='\n\n'.join(parts))]


def choose(candidate, restructured, outcome):
    if restructured is not None and outcome and outcome['completed']:
        return restructured, True
    return candidate, False


def quality_step(packet, k, bodies, superseded, helpers, baseline, path, previous_text, candidate, context, provider, spent, step_dir, findings):
    requirement = (packet / 'steps' / f'S{k}' / 'requirement.md').read_text(encoding='utf-8').strip()
    messages = quality_prompt(requirement, candidate, path, context, findings)
    record = dict(triggered=True, findings=[f"{f['type']}:{f['symbolName']}" for f in findings])
    reserve = core.reservation(messages)
    if not core.may_call(spent, reserve, rr.MAX_OUTPUT, rr.ALLOCATION):
        return dict(record, accepted=False, stage='allocation'), candidate, spent
    (step_dir / 'quality-request.json').write_text(json.dumps(dict(messages=messages), indent=1), encoding='utf-8')
    text, usage = provider(messages, candidate, candidate, path, record=step_dir / 'quality')
    (step_dir / 'quality-response.txt').write_text(text, encoding='utf-8')
    spent += (usage.get('input_tokens') or 0) + (usage.get('output_tokens') or 0)
    try:
        restructured = b.apply_edits(candidate, path, text)
    except (ValueError, json.JSONDecodeError) as error:
        return dict(record, accepted=False, stage='invalid_patch', error=str(error), call=usage), candidate, spent
    outcome = b.gates(baseline, previous_text, restructured, bodies, k, superseded, helpers, spent <= rr.ALLOCATION)
    final, accepted = choose(candidate, restructured, outcome)
    return dict(record, accepted=accepted, stage=outcome['stage'], call=usage), final, spent


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--packets', type=Path, required=True)
    p.add_argument('--out', type=Path)
    p.add_argument('--provider', choices=['reference', 'noop', 'live'])
    p.add_argument('--targets', nargs='*')
    p.add_argument('--freeze', type=Path)
    p.add_argument('--write-freeze', type=Path)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--model-key', help='local CLI model entry (an Azure deployment); default is the model of replay_settings.json')
    p.add_argument('--temperature', type=float, help='sampling temperature recorded in the freeze and applied to every call; default is the model entry')
    p.add_argument('--api', choices=['chat', 'messages'], default='chat',
                   help='chat: Azure chat completions (default); messages: the Anthropic-compatible route on the entry\'s own Azure host')
    p.add_argument('--protocol', type=Path, default=HERE / 'PROTOCOL-v0.4.md')
    a = p.parse_args()
    from replay_freeze import hash_files, changed_files, CODE
    pairs = {x['target_id']: x for x in json.loads((ROOT / 'generated' / 'campaign.json').read_text(encoding='utf-8'))['pairs']}
    folders = b.selected_targets(a.packets, a.targets)
    protocol = a.protocol
    model_label = a.model_key or rr.SETTINGS['model_key']
    if a.write_freeze:
        if a.write_freeze.exists():
            raise SystemExit('Freeze record exists; a freeze is never overwritten')
        record = dict(schema_version='reaccrual-v0.4-freeze/0.1', targets=[f.name for f in folders], arms=list(ARMS), seed=SEED, model_key=model_label, temperature=a.temperature, api=a.api,
                      settings=rr.SETTINGS, inputs=hash_files(b.packet_inputs(a.packets, folders, pairs) + [protocol]), code=hash_files(CODE))
        a.write_freeze.write_text(json.dumps(record, indent=1), encoding='utf-8')
        print(f'Frozen: {len(folders)} targets, {len(record["inputs"])} inputs, {len(record["code"])} code files')
        return
    if not (a.out and a.provider):
        raise SystemExit('--out and --provider are required for a run')
    if a.out.exists() and not a.resume:
        raise SystemExit('Output exists: use a new run directory, or --resume to continue it')
    ledger_path = ROOT / 'budget-ledger.json'
    prefix = f'reaccrual-v04-{a.out.name}'
    skip, moved = rr.prepare_resume(a.out, [f.name for f in folders]) if a.out.exists() else (set(), [])
    experiment = None
    if a.provider == 'live':
        if not rr.SETTINGS['live_execution_enabled']:
            raise SystemExit('Live execution is not enabled')
        if not a.freeze or not a.freeze.exists():
            raise SystemExit('Live execution requires the v0.4 freeze record (--freeze)')
        frozen = json.loads(a.freeze.read_text(encoding='utf-8'))
        drift = changed_files(frozen['inputs']) + changed_files(frozen['code'])
        frozen_run = (frozen.get('model_key', rr.SETTINGS['model_key']), frozen.get('temperature'), frozen.get('api', 'chat'))
        if drift or frozen['targets'] != [f.name for f in folders] or frozen_run != (model_label, a.temperature, a.api):
            raise SystemExit(f'Frozen inputs, code, targets or model changed: {drift[:5]}')
        ledger.recover_interrupted(ledger_path, f'interrupted {prefix} run, resumed', prefix=prefix)
        previous = sum(1 for e in json.loads(ledger_path.read_text(encoding='utf-8'))['entries'] if e['experiment'].startswith(prefix))
        experiment = f'{prefix}-{previous + 1}'
        ledger.open_entry(ledger_path, experiment, a.out)
        overrides = dict(Temperature=a.temperature) if a.temperature is not None else None
        if a.api == 'messages':
            local = json.loads((REPO / 'src/HybridLens.CLI/appsettings.local.json').read_text(encoding='utf-8-sig'))['Llm']
            provider = messages_provider.live_provider(rr.model_config(local, model_label, overrides), ledger_path, experiment, rr.MAX_OUTPUT,
                                                       rr.SETTINGS['rate_limit_tokens_per_minute'])
        else:
            provider = rr.live_provider(dict(rr.SETTINGS, model_key=model_label), ledger_path, experiment, overrides)
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
        repaired = core.decode_source((ROOT / pair['repaired_path']).resolve().read_bytes())
        supporting = {f.name: core.decode_source(f.read_bytes()) for f in sorted((packet / 'supporting').glob('*.cs'))}
        context = {name: supporting[name] for name in b.closure_files(original, supporting)}
        helpers = (packet / 'helpers.cs').read_text(encoding='utf-8') if (packet / 'helpers.cs').exists() else ''
        bodies = {k: (packet / 'steps' / f'S{k}' / 'tests.cs').read_text(encoding='utf-8') for k in range(1, 5)}
        arms = arm_order(tid)
        states = {arm: original if ARMS[arm]['start'] == 'original' else repaired for arm in arms}
        spent, active, superseded = {arm: 0 for arm in arms}, set(arms), set()
        (a.out / tid).mkdir(parents=True, exist_ok=True)
        findings = {arm: scan(path, states[arm], a.out / tid / f'{arm}-S0-scan.json') for arm in arms if ARMS[arm]['loop']}
        for k in range(1, 5):
            superseded |= {line.strip() for line in (packet / 'steps' / f'S{k}' / 'superseded.txt').read_text(encoding='utf-8').splitlines() if line.strip()}
            reference_text = core.decode_source((packet / 'steps' / f'S{k}' / 'reference.cs').read_bytes())
            for arm in arms:
                if arm not in active:
                    continue
                step_dir = a.out / tid / arm / f'S{k}'
                step_dir.mkdir(parents=True)
                started = time.monotonic()
                result, spent[arm] = b.run_step(packet, k, bodies, superseded, helpers, baseline, path, states[arm], reference_text,
                                                context, provider, spent[arm], step_dir, system_for(arm))
                state = result.pop('state', None)
                if result['completed'] and ARMS[arm]['loop']:
                    after = scan(path, state, step_dir / 'scan.json')
                    introduced = new_findings(findings[arm], after, path)
                    if introduced:
                        result['quality'], state, spent[arm] = quality_step(packet, k, bodies, superseded, helpers, baseline, path, states[arm],
                                                                            state, context, provider, spent[arm], step_dir, introduced)
                        if result['quality']['accepted']:
                            after = scan(path, state, step_dir / 'scan-after-quality.json')
                    else:
                        result['quality'] = dict(triggered=False)
                    findings[arm] = after
                result['seconds'] = round(time.monotonic() - started, 1)
                if result['completed']:
                    states[arm] = state
                    (step_dir / 'state.cs').write_bytes(state.encode('utf-8'))
                else:
                    active.discard(arm)
                (step_dir / 'result.json').write_text(json.dumps(result, indent=1), encoding='utf-8')
                quality = result.get('quality') or {}
                summary.append(dict(target=tid, branch=arm, step=k, completed=result['completed'], stage=result.get('stage'),
                                    seconds=result['seconds'], quality_triggered=quality.get('triggered'), quality_accepted=quality.get('accepted')))
                summary_path.write_text(json.dumps(summary, indent=1), encoding='utf-8')
                print(json.dumps(summary[-1]), flush=True)
        (a.out / tid / 'complete.json').write_text(json.dumps(dict(arms=arms, context_files=sorted(context))), encoding='utf-8')
    summary_path.write_text(json.dumps(summary, indent=1), encoding='utf-8')
    if experiment:
        ledger.close_entry(ledger_path, experiment)


if __name__ == '__main__':
    main()
