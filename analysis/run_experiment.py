"""Single thesis entry point. Planning uses only the Python standard library.

Default: regenerate the final thesis outputs from retained evidence, without model
calls. Use --study to execute a campaign, or --list to see all supported studies.
Environment: OUT, CORPUS, CLI, MODEL, RUNS, BUDGET, SEED, BUILD_TIMEOUT,
MAX_INPUT_TOKENS, DOTNET, INDUSTRIAL_TARGET, ADMITTED, HARNESS, GOLDEN.
Maintenance commands accept their native arguments after -- (including --help).
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REA = 'analysis/maintenance_efficiency/reaccrual/'
DATA = 'analysis/thesis/data/'
STUDIES = {
    'thesis': ('tables', 'figures', 'appendix-b'),
    'factorial': ('baseline', 'tests', 'manifest', 'campaign', 'oracle', 'quality', 'analyse'),
    'context-corpus': ('baseline', 'manifest', 'campaign', 'oracle', 'quality', 'analyse'),
    'context-industrial': ('baseline', 'manifest', 'campaign', 'oracle', 'quality', 'analyse'),
    'replay': ('prepare', 'freeze', 'campaign', 'analyse', 'recurrence', 'sensitivity'),
    'durability': ('prepare', 'freeze', 'campaign', 'analyse', 'introductions'),
    'interventions': ('freeze', 'campaign', 'analyse'),
    'replication': ('freeze', 'campaign', 'analyse'),
    'introduction': ('prepare', 'freeze', 'campaign', 'analyse'),
    'appendix-b': ('scan', 'models', 'categories', 'figures'),
    'maintenance-export': ('analyse',),
}
# Native maintenance interfaces preserve their own freezes, gates and resume rules.
NATIVE = {
    'replay': {'prepare': 'replay_prepare.py', 'freeze': 'replay_freeze.py',
               'campaign': 'replay_run.py', 'analyse': 'replay_analyze.py',
               'recurrence': 'recurrence.py', 'sensitivity': 'sensitivity.py'},
    'durability': {'prepare': 'build_stratum_b_packets.py', 'freeze': 'stratum_b_run.py',
                   'campaign': 'stratum_b_run.py', 'analyse': 'stratum_b_analyze.py',
                   'introductions': 'introduced_findings.py'},
    'interventions': {'freeze': 'v04_run.py', 'campaign': 'v04_run.py', 'analyse': 'v04_analyze.py'},
    'replication': {'freeze': 'v04_run.py', 'campaign': 'v04_run.py', 'analyse': 'v04_analyze.py'},
    'introduction': {'prepare': 'v05_run.py', 'freeze': 'v05_run.py',
                     'campaign': 'v05_run.py', 'analyse': 'v05_analyze.py'},
}


@dataclass
class Step:
    stage: str
    command: list[str]
    inputs: tuple[str, ...] = ()
    directories: tuple[str, ...] = ()
    action: str = ''


def py(script, *args):
    return [sys.executable, script, *map(str, args)]


def thesis_steps(out):
    return [
        Step('tables', py('analysis/thesis/tables.py', '--out', f'{out}/tables')),
        Step('figures', py('analysis/thesis/architecture.py', '--out', f'{out}/figures')),
        Step('figures', py('analysis/thesis/maintenance_figures.py', '--out', f'{out}/figures')),
        Step('appendix-b', py('analysis/multilanguage_evolution/plot_three_rule_trajectories.py',
             '--csv', DATA+'evolution/three-rule-annual-coverage.csv', '--out', f'{out}/appendix-b/annual')),
        Step('appendix-b', py('analysis/god_class_change_count_thesis/render.py',
             '--source', DATA+'god-class/models.csv', '--output', f'{out}/appendix-b/change-count')),
        Step('appendix-b', py('analysis/god_class_change_categories/combined_fix/render.py',
             '--input', DATA+'categories/comparison-file-counts.csv',
             '--seal', DATA+'categories/SHA256SUMS.json', '--output', f'{out}/appendix-b/categories')),
    ]


def repair_steps(study, out, env):
    factorial = study == 'factorial'
    industrial = study == 'context-industrial'
    cli = env.get('CLI', 'src/HybridLens.CLI')
    target = env.get('INDUSTRIAL_TARGET', '<INDUSTRIAL_TARGET>') if industrial else env.get(
        'CORPUS', str(ROOT.parent/'hybrid-pipeline-corpus/corpus/Corpus.sln'))
    model = env.get('MODEL', 'gpt-5.6-sol')
    dotnet = env.get('DOTNET', 'dotnet')
    def net(command, *args):
        return [dotnet, 'run', '--project', cli, '--', command, *map(str, args)]
    baseline = f'{out}/baseline.jsonl'
    tests = f'{out}/generated-tests'
    manifest = f'{out}/factorial-manifest.json' if factorial else f'{out}/ladder-manifest.json'
    campaign = f'{out}/campaign'
    results = f'{out}/results'
    private = f'{out}/private-results'
    quality = f'{out}/quality-results'
    # Resolve revision only during execution; --dry-run is free of Git and SDK checks.
    revision = env.get('CODE_REVISION', '<git-revision>')
    common = ['--from', baseline, '--target', target, '--model', model,
              '--code-revision', revision, '--runs', env.get('RUNS', '3'),
              '--build-timeout', env.get('BUILD_TIMEOUT', '180'),
              '--seed', env.get('SEED', '503999552'), '--out', manifest]
    steps = [Step('baseline', net('analyse', '--target', target, '--dry-run',
                  '--severity', 'Warning', '--format', 'json', '--output', baseline),
                  (target,), (out,))]
    if factorial:
        steps.append(Step('tests', net('generate-characterization-test', '--from', baseline,
                     '--target', target, '--source', '<each target source>', '--model', model,
                     '--out', tests), (target, baseline), (tests,), 'tests'))
        steps.append(Step('manifest', net('factorial-manifest', *common, '--visible-tests', tests,
                     '--budget', env.get('BUDGET', '6'), '--max-input-tokens', env.get('MAX_INPUT_TOKENS', '120000')),
                     (target, baseline, tests)))
    else:
        admitted = ['--admitted', env.get('ADMITTED', '<ADMITTED>')] if industrial else []
        steps.append(Step('manifest', net('context-ladder-manifest', *common, *admitted),
                     (target, baseline, *([admitted[-1]] if admitted else []))))
    command = 'factorial-campaign' if factorial else 'context-ladder-campaign'
    steps.append(Step('campaign', net(command, '--manifest', manifest, '--out', campaign),
                 (manifest,), (campaign,)))
    oracle_name = 'layer3-campaign.jsonl' if factorial else 'layer3.jsonl'
    build = ['--build-arg', '--no-restore', '--build-arg', '-p:NuGetAudit=false']
    for name in ('bin', '.git', '.vs', '.idea'):
        build += ['--working-copy-skip', name]
    if industrial:
        harness, golden = env.get('HARNESS', '<HARNESS>'), env.get('GOLDEN', '<GOLDEN>')
        steps.append(Step('oracle', net('external-oracle', '--artifacts', campaign+'/final-sources',
                     '--target', target, '--harness', harness, '--golden', golden,
                     '--harness-prop', '-p:ProductRoot={WORKING_ROOT}', *build,
                     '--out', private+'/external-oracle.jsonl'),
                     (target, harness, golden, manifest), (private,), 'sealed'))
    else:
        steps.append(Step('oracle', net('private-layer3', '--artifacts', campaign+'/final-sources',
                     '--target', target, '--oracle-manifest', 'layer3/PRIVATE_ORACLE_MANIFEST.md',
                     '--out', f'{private}/{oracle_name}'), (target, manifest), (private,), 'sealed'))
    quality_file = private+'/external-quality.jsonl' if industrial else quality+('/layer2-quality.jsonl' if factorial else '/layer2.jsonl')
    steps.append(Step('quality', net('external-quality', '--artifacts', campaign+'/final-sources',
                 '--target', target, * (build if industrial else []), '--out', quality_file),
                 (target, manifest), (str(Path(quality_file).parent),), 'sealed'))
    if factorial:
        steps.extend([
            Step('analyse', net('factorial-summary', '--runs-dir', campaign+'/traces',
                 '--private-dir', private, '--out', results+'/factorial-summary'),
                 (campaign+'/traces', private), (results,)),
            Step('analyse', py('analysis/factorial_test_feedback_analysis.py',
                 '--attempts', results+'/factorial-summary/attempts.json', '--out', results+'/statistical-analysis')),
            Step('analyse', py('analysis/factorial_glmm.py', '--data', results+'/statistical-analysis/model_ready_attempts.csv',
                 '--out', results+'/glmm-analysis')),
            Step('analyse', py('analysis/thesis/tables.py', '--factorial', out,
                 '--section', 'factorial', '--out', results+'/tables')),
        ])
    else:
        script = 'context_ladder_industrial_analysis.py' if industrial else 'context_ladder_analysis.py'
        steps.append(Step('analyse', py('analysis/'+script, '--experiment', out, '--out', results+'/analysis'),
                     (manifest, quality_file)))
    return steps


def ensure_sealed(manifest, campaign):
    assignments = json.loads(Path(manifest).read_text(encoding='utf-8-sig'))['assignments']
    ledger = Path(campaign)/'execution-ledger.jsonl'
    rows = [json.loads(line) for line in ledger.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    expected = {row['assignment_id'] for row in assignments}
    complete = {row['assignment_id'] for row in rows if row.get('completed') is True}
    if not expected or expected != complete:
        raise ValueError('Private evaluation requires every frozen assignment to be complete.')


def generate_tests(command):
    baseline = Path(command[command.index('--from')+1])
    target = Path(command[command.index('--target')+1])
    findings = json.loads(baseline.read_text(encoding='utf-8-sig'))['findings']
    sources = sorted({f['filePath'] for f in findings if f['type'] in ('longMethod', 'godClass')})
    if not sources:
        raise ValueError(f'No Long Method or God Class targets in {baseline}')
    index = command.index('--source')+1
    for source in sources:
        call = command.copy()
        call[index] = str(target.parent/source)
        # Rejected test admission remains in the intention-to-treat denominator.
        result = subprocess.run(call, cwd=ROOT, check=False)
        if result.returncode:
            print(f'Characterisation test unavailable for {source}; retained in the denominator.', file=sys.stderr)


def execute(step, dry_run):
    print(f'[{step.stage}] {shlex.join(step.command)}', flush=True)
    if dry_run:
        return
    for value in step.inputs:
        if not Path(value).exists():
            raise ValueError(f'Required input is missing: {value}')
    command = step.command.copy()
    if '<git-revision>' in command:
        command[command.index('<git-revision>')] = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if step.action == 'sealed':
        artifacts = Path(command[command.index('--artifacts')+1])
        ensure_sealed(step.inputs[-1], artifacts.parent)
    for directory in step.directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
    if step.action == 'tests':
        generate_tests(command)
    else:
        subprocess.run(command, cwd=ROOT, check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--study', choices=STUDIES, default='thesis')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--stage')
    group.add_argument('--from', dest='from_stage')
    parser.add_argument('--out', default=os.environ.get('OUT'))
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('arguments', nargs=argparse.REMAINDER, help='Native study options after --')
    args = parser.parse_args(argv)
    os.chdir(ROOT)
    if args.list:
        for name, stages in STUDIES.items():
            print(f'{name:20} {", ".join(stages)}')
        return 0
    stages = STUDIES[args.study]
    for selected in (args.stage, args.from_stage):
        if selected and selected not in stages:
            parser.error(f'{args.study} stages: {", ".join(stages)}')
    extra = args.arguments[1:] if args.arguments[:1] == ['--'] else args.arguments
    out = args.out or 'output/'+args.study+'-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    if args.study in NATIVE or args.study in ('maintenance-export', 'appendix-b'):
        if args.from_stage:
            parser.error('This study uses native arguments per stage; choose --stage instead of --from.')
        stage = args.stage or ('analyse' if args.study == 'maintenance-export' else 'figures' if args.study == 'appendix-b' else 'campaign')
        if args.study in NATIVE:
            prefix = []
            if args.study == 'introduction' and stage != 'analyse':
                prefix = [{'campaign': 'run'}.get(stage, stage)]
            if stage == 'freeze' and args.study in ('durability', 'interventions', 'replication') and '--write-freeze' not in extra and '--help' not in extra:
                parser.error('The freeze stage requires -- --packets DIR --write-freeze FILE.')
            if args.study == 'replication' and stage in ('freeze', 'campaign'):
                if '--model-key' not in extra:
                    prefix += ['--model-key', 'claude-opus-5-5']
                if '--temperature' not in extra:
                    prefix += ['--temperature', '1']
                prefix += ['--api', 'messages', '--protocol', REA+'PROTOCOL-v0.6.md']
            command = py(REA+NATIVE[args.study][stage], *prefix, *extra)
        elif args.study == 'maintenance-export':
            command = py('analysis/thesis/export_maintenance.py', *extra)
        elif stage != 'figures':
            script = {'scan': 'multilanguage_evolution/run_three_rules.py',
                      'models': 'maintenance_associations/run_final_automated_analysis.py',
                      'categories': 'god_class_change_categories/run_v1_1.py'}[stage]
            command = py('analysis/'+script, *extra)
        else:
            if extra:
                parser.error('Appendix figure inputs are retained in analysis/thesis/data; use --out for generated outputs.')
            for step in thesis_steps(out):
                if step.stage == 'appendix-b':
                    execute(step, args.dry_run)
            return 0
        if args.out:
            parser.error('For native studies, pass their output flag after --; use -- --help for its name.')
        execute(Step(stage, command), args.dry_run)
        return 0
    if extra:
        parser.error('Only maintenance and Appendix B analysis stages accept arguments after --.')
    if os.environ.get('MAX_TARGETS', '0') != '0':
        parser.error('MAX_TARGETS was not a campaign limit. Use a deliberately filtered baseline and start at --stage manifest.')
    steps = thesis_steps(out) if args.study == 'thesis' else repair_steps(args.study, out, os.environ)
    selected = {args.stage} if args.stage else set(stages[stages.index(args.from_stage):] if args.from_stage else stages)
    for step in steps:
        if step.stage in selected:
            execute(step, args.dry_run)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, FileNotFoundError) as error:
        print(f'error: {error}', file=sys.stderr)
        raise SystemExit(1)
    except subprocess.CalledProcessError as error:
        print(f'error: command failed with exit code {error.returncode}', file=sys.stderr)
        raise SystemExit(error.returncode)
