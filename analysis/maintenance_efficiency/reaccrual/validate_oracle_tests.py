"""Automatic admission checks for oracle test classes (ORACLE_TEST_SPEC.md). Makes no model calls.

Usage: python validate_oracle_tests.py <clone> <packages-dir> <stubber.dll> [--step ID ...] [--retention eligible-targets.json]
Each package folder holds step.json and, once written, submission/Step_<ID>.cs. Results go to <package>/validation.json.
The clone must be a disposable local clone that no other process is using.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from feasibility_audit import git, run_tests

FORBIDDEN = [r'DateTime(Offset)?\.(Utc)?Now', r'\bnew Random\b', r'\bRandom\.Shared\b', r'\bFile\.', r'\bDirectory\.',
             r'Thread\.Sleep', r'Task\.Delay', r'\bProcess\.', r'Environment\.', r'\bRegistry\b', r'HttpClient',
             r'SqlConnection', r'ShowDialog', r'MessageBox', r'\[Ignore', r'BindingFlags\.NonPublic',
             r'\.GetField\(', r'\.GetMethod\(', r'\.GetProperty\(']


def static_guard(text, step_id):
    problems = [f'forbidden construct: {p}' for p in FORBIDDEN if re.search(p, text)]
    if not re.search(r'namespace\s+Reaccrual\.Oracle\b', text):
        problems.append('namespace must be Reaccrual.Oracle')
    classes = re.findall(r'\bclass\s+(\w+)', text)
    if classes != [f'Step_{step_id}']:
        problems.append(f'expected exactly one class Step_{step_id}, found {classes}')
    if '[TestMethod' not in text:
        problems.append('no [TestMethod]')
    return problems


def run_class(clone, project, results_dir, step_id, no_restore):
    return run_tests(clone, project, results_dir, None, no_restore=no_restore,
                     extra=['--filter', f'FullyQualifiedName~Reaccrual.Oracle.Step_{step_id}'])


def install(clone, project, submission):
    destination = project.parent / 'ReaccrualOracle' / submission.name
    destination.parent.mkdir(exist_ok=True)
    shutil.copyfile(submission, destination)
    return destination


def validate(clone, package, stubber, results_dir):
    step = json.loads((package / 'step.json').read_text(encoding='utf-8'))
    step_id = step['step_id']
    submission = package / 'submission' / f'Step_{step_id}.cs'
    result = dict(step_id=step_id, admitted=False, problems=[])
    if not submission.exists():
        result['problems'].append('no submission')
        return result
    result['problems'] += static_guard(submission.read_text(encoding='utf-8-sig'), step_id)
    if result['problems']:
        return result
    project = clone / step['test_project']
    commit, target = step['commit'], step['target_file']
    git(clone, 'checkout', '-f', '-q', commit)
    for stale in ('bin', 'obj'):
        shutil.rmtree(project.parent / stale, ignore_errors=True)
    installed = install(clone, project, submission)
    try:
        runs = [run_class(clone, project, results_dir, step_id, no_restore=n > 0) for n in range(2)]
        result['post_runs'] = [dict(status=r['status'], outcomes=r['outcomes'], errors=r['log_tail']) for r in runs]
        if any(r['status'] != 'ran' or any(o != 'Passed' for o in r['outcomes'].values()) for r in runs):
            result['problems'].append('not all tests pass twice on the post-commit state')
            return result
        with tempfile.TemporaryDirectory() as tmp:
            pre, post = Path(tmp, 'pre.cs'), Path(tmp, 'post.cs')
            pre.write_bytes(git(clone, 'show', f'{commit}^:{target}'))
            post.write_bytes(git(clone, 'show', f'{commit}:{target}'))
            stub = json.loads(subprocess.run(['dotnet', stubber, str(pre), str(post), str(clone / target)],
                                             capture_output=True, text=True, check=True).stdout)
        stubbed = run_class(clone, project, results_dir, step_id, no_restore=True)
        result['stub_run'] = dict(stubbed=stub['stubbed'], status=stubbed['status'], outcomes=stubbed['outcomes'],
                                  errors=stubbed['log_tail'])
        failing = [t for t, o in stubbed['outcomes'].items() if o != 'Passed']
        if stubbed['status'] != 'ran' or not failing:
            result['problems'].append('no test fails with the changed members stubbed')
            return result
        result['stub_failing_tests'] = failing
        result['admitted'] = True
        return result
    finally:
        git(clone, 'checkout', '-q', commit, '--', target)
        installed.unlink(missing_ok=True)


def retention(clone, package, later_commits, results_dir):
    """Run an admitted class at each later step's post-commit state; passing classes are retained there."""
    step = json.loads((package / 'step.json').read_text(encoding='utf-8'))
    step_id = step['step_id']
    project = clone / step['test_project']
    submission = package / 'submission' / f'Step_{step_id}.cs'
    results = []
    for commit in later_commits:
        git(clone, 'checkout', '-f', '-q', commit)
        for stale in ('bin', 'obj'):
            shutil.rmtree(project.parent / stale, ignore_errors=True)
        installed = install(clone, project, submission)
        try:
            run = run_class(clone, project, results_dir, step_id, no_restore=False)
        finally:
            installed.unlink(missing_ok=True)
        passed = run['status'] == 'ran' and all(o == 'Passed' for o in run['outcomes'].values())
        results.append(dict(commit=commit, retained=passed, status=run['status'], outcomes=run['outcomes'], errors=run['log_tail']))
    return results


def main():
    clone, packages, stubber = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    only = {sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == '--step'}
    results_dir = packages / '_trx'
    results_dir.mkdir(exist_ok=True)
    if '--retention' in sys.argv:
        windows = {t['path']: [h for h, _ in t['steps']]
                   for t in json.loads(Path(sys.argv[sys.argv.index('--retention') + 1]).read_text(encoding='utf-8'))}
        for package in sorted(p for p in packages.iterdir() if (p / 'validation.json').exists()):
            if only and package.name not in only:
                continue
            validation = json.loads((package / 'validation.json').read_text(encoding='utf-8'))
            if not validation['admitted']:
                continue
            step = json.loads((package / 'step.json').read_text(encoding='utf-8'))
            later = windows[step['target_file']][step['step_in_window']:]
            validation['retention'] = retention(clone, package, later, results_dir)
            (package / 'validation.json').write_text(json.dumps(validation, indent=1), encoding='utf-8')
            print(step['step_id'], [('retained' if r['retained'] else 'retired') + ' ' + r['commit'][:8] for r in validation['retention']], flush=True)
        return
    for package in sorted(p for p in packages.iterdir() if (p / 'step.json').exists()):
        if only and package.name not in only:
            continue
        result = validate(clone, package, stubber, results_dir)
        (package / 'validation.json').write_text(json.dumps(result, indent=1), encoding='utf-8')
        print(result['step_id'], 'ADMITTED' if result['admitted'] else 'REJECTED', '; '.join(result['problems']), flush=True)


if __name__ == '__main__':
    main()
