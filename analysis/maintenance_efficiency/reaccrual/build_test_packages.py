"""Build one oracle-test work package per unchecked step of the eligible replay windows (ORACLE_TEST_SPEC.md).

Usage: python build_test_packages.py <work-dir> <repo> <output-dir> [--exclude-project NAME ...] [--max-tokens N]
<work-dir> holds eligible-targets.json, f2p-results.jsonl and phase1-candidates.json from summarise_audit.py --include-unchecked.
Packages contain proprietary source; <output-dir> must be outside the public repository.
"""
import json
import subprocess
import sys
from pathlib import Path


def show(repo, commit, path):
    p = subprocess.run(['git', '-C', str(repo), 'show', f'{commit}:{path}'], capture_output=True)
    return p.stdout if p.returncode == 0 else None


def test_project(record, target, excluded):
    candidates = [p for p in record['target_projects'][target]
                  if Path(p).stem not in excluded and record['post'][p]['status'] == 'ran']
    production = Path(target).parts[1] if len(Path(target).parts) > 1 else ''
    matching = [p for p in candidates if Path(p).parent.name.lower() == f'{production}.tests'.lower()]
    return (matching or candidates or [None])[0]


def main():
    work, repo, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    excluded = {sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == '--exclude-project'}
    max_tokens = int(sys.argv[sys.argv.index('--max-tokens') + 1]) if '--max-tokens' in sys.argv else None
    targets = [t for t in json.loads((work / 'eligible-targets.json').read_text(encoding='utf-8'))
               if max_tokens is None or t['approx_tokens_t0'] <= max_tokens]
    commits = json.loads((work / 'phase1-candidates.json').read_text(encoding='utf-8'))['commits']
    records = {}
    for line in (work / 'f2p-results.jsonl').read_text(encoding='utf-8').splitlines():
        if line.strip():
            r = json.loads(line)
            records[r['commit']] = r
    index = []
    for t_index, target in enumerate(sorted(targets, key=lambda t: t['path']), 1):
        for k, (commit, kind) in enumerate(target['steps'], 1):
            if kind != 'unchecked':
                continue
            step_id = f'T{t_index:02d}S{k}'
            record = records[commit]
            path = target['path']
            folder = out / step_id
            (folder / 'callers').mkdir(parents=True, exist_ok=True)
            (folder / 'existing-tests').mkdir(exist_ok=True)
            pre, post = show(repo, f'{commit}^', path), show(repo, commit, path)
            (folder / 'target.pre.cs').write_bytes(pre)
            (folder / 'target.post.cs').write_bytes(post)
            diff = subprocess.run(['git', '-C', str(repo), 'diff', f'{commit}^', commit, '--', path], capture_output=True).stdout
            (folder / 'target.diff').write_bytes(diff)
            callers, tests = [], []
            for changed in commits[commit]['files']:
                if not changed.endswith('.cs') or changed == path:
                    continue
                content = show(repo, commit, changed)
                if content is None:
                    continue
                is_test = 'test' in changed.lower()
                destination = folder / ('existing-tests' if is_test else 'callers') / changed.replace('/', '__')
                destination.write_bytes(content)
                (tests if is_test else callers).append(changed)
            subject = subprocess.run(['git', '-C', str(repo), 'log', '-1', '--format=%s', commit],
                                     capture_output=True, text=True, encoding='utf-8').stdout.strip()
            step = dict(step_id=step_id, commit=commit, date=commits[commit]['date'], subject=subject,
                        target_file=path, target_type=target['type'], step_in_window=k, window_length=target['k'],
                        test_project=test_project(record, path, excluded),
                        changed_members=record.get('stub', {}).get(path, {}).get('stubbed', []),
                        unstubbable_members=record.get('stub', {}).get(path, {}).get('unstubbable', []),
                        changed_callers=callers, changed_tests=tests,
                        deliverable=f'Step_{step_id}.cs', test_class=f'Reaccrual.Oracle.Step_{step_id}')
            (folder / 'step.json').write_text(json.dumps(step, indent=1), encoding='utf-8')
            index.append(step)
    (out / 'index.json').write_text(json.dumps(index, indent=1), encoding='utf-8')
    print(f'{len(index)} work packages written to {out}')
    for s in index:
        print(s['step_id'], s['target_type'], Path(s['target_file']).name, 'members', len(s['changed_members']), 'test project', s['test_project'])


if __name__ == '__main__':
    main()
