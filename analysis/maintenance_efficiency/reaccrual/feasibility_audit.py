"""Fail-to-pass replay audit for the re-accrual protocol (Section 10). Makes no model calls.

Usage: python feasibility_audit.py <clone> <phase1-candidates.json> <results.jsonl> [--only commits.json] [--nuget-config path] [--max-commits N] [--stubber HybridLens.ChangeStub.dll] [--backfill-stubs] [--exclude-project NAME ...]
The clone must be a disposable local clone; it is force-checked-out per commit.
--only restricts testing to listed commits; candidate runs are split at unlisted commits.
With --stubber, a pair whose pre-commit file does not build is rerun with only the commit's changed members stubbed;
--backfill-stubs adds those runs to records written before stubbing existed.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

TEST_TIMEOUT = 900


def run(args, cwd, timeout=None):
    started = time.time()
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
        return p.returncode, p.stdout + p.stderr, round(time.time() - started, 1)
    except subprocess.TimeoutExpired:
        return None, 'timeout', round(time.time() - started, 1)


def git(clone, *args):
    return subprocess.run(['git', '-C', str(clone), *args], capture_output=True, check=True).stdout


def owning_project(clone, test_file):
    folder = (clone / test_file).parent
    while folder != clone and folder.exists():
        projects = sorted(folder.glob('*.csproj'))
        if projects:
            return projects[0]
        folder = folder.parent
    return None


EXCLUDED = set()


def test_projects_for(clone, target, changed_tests):
    """Test projects that transitively reference the target's project, plus owners of changed test files."""
    projects = sorted(clone.rglob('*.csproj'))
    references = {}
    for project in projects:
        text = project.read_text(encoding='utf-8-sig', errors='replace')
        references[project] = {(project.parent / ref.replace(chr(92), '/')).resolve()
                               for ref in re.findall(r'<ProjectReference\s+Include="([^"]+)"', text)}
    owner = owning_project(clone, target)
    selected = {owning_project(clone, t) for t in changed_tests} - {None}
    if owner is not None:
        reaching, frontier = set(), {owner.resolve()}
        while frontier:
            frontier = {p.resolve() for p, refs in references.items() if refs & frontier} - reaching
            reaching |= frontier
        selected |= {p for p in projects if p.resolve() in reaching and 'test' in p.name.lower()}
    return sorted(p for p in selected if p.stem not in EXCLUDED)


def run_tests(clone, project, results_dir, nuget_config, no_restore=False, extra=()):
    trx = results_dir / 'r.trx'
    if trx.exists():
        trx.unlink()
    restore = ['--no-restore'] if no_restore else ([f'-p:RestoreConfigFile={nuget_config}'] if nuget_config else [])
    code, log, seconds = run(['dotnet', 'test', str(project), '--nologo', '-v', 'q', '-p:NuGetAudit=false', *restore,
                              '--logger', 'trx;LogFileName=r.trx', '--results-directory', str(results_dir), *extra],
                             cwd=clone, timeout=TEST_TIMEOUT)
    outcomes, total = {}, None
    if trx.exists():
        ns = {'t': 'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
        root = ET.parse(trx).getroot()
        for result in root.iterfind('.//t:UnitTestResult', ns):
            name, outcome = result.get('testName'), result.get('outcome')
            if outcomes.get(name, 'Passed') == 'Passed':
                outcomes[name] = outcome
        counters = root.find('.//t:Counters', ns)
        total = int(counters.get('total')) if counters is not None else None
    errors = sorted({line.strip() for line in log.splitlines() if ': error ' in line})
    status = 'timeout' if code is None else ('ran' if outcomes else ('no_tests' if total == 0 else 'no_results'))
    if status != 'ran' and any(': error NU' in e for e in errors):
        status = 'restore_failed'
    elif status != 'ran' and any(': error CS' in e for e in errors):
        status = 'build_failed'
    tail = '' if status == 'ran' else ('\n'.join(errors[:30]) if errors else log[-4000:])
    return dict(status=status, exit=code, seconds=seconds, outcomes=outcomes, error_count=len(errors), log_tail=tail)


def needs_stub(record, target):
    return any(isinstance(v, dict) and v.get('status') == 'build_failed' and Path(k).stem not in EXCLUDED
               for k, v in record['pre'].get(target, {}).items())


def stub_run(clone, h, target, target_projects, record, results_dir, nuget_config, stubber, fresh):
    """Run the target's tests with only the members changed by commit h stubbed to throw."""
    rel = lambda p: str(Path(p).relative_to(clone))
    with tempfile.TemporaryDirectory() as tmp:
        pre, post = Path(tmp, 'pre.cs'), Path(tmp, 'post.cs')
        pre.write_bytes(git(clone, 'show', f'{h}^:{target}'))
        post.write_bytes(git(clone, 'show', f'{h}:{target}'))
        out = subprocess.run(['dotnet', stubber, str(pre), str(post), str(clone / target)], capture_output=True, text=True, check=True)
    entry = json.loads(out.stdout)
    if not entry['stubbed']:
        entry['status'] = 'nothing_to_stub'
    else:
        for project in target_projects:
            if Path(project).stem in EXCLUDED or record['post'][rel(project)]['status'] != 'ran':
                continue
            if fresh:
                for stale in ('bin', 'obj'):
                    shutil.rmtree(Path(project).parent / stale, ignore_errors=True)
            entry[rel(project)] = run_tests(clone, project, results_dir, nuget_config, no_restore=not fresh)
    git(clone, 'checkout', '-q', h, '--', target)
    return entry


def save(out_path, records):
    tmp = out_path.with_suffix('.tmp')
    tmp.write_text(''.join(json.dumps(r) + '\n' for r in records.values()), encoding='utf-8')
    tmp.replace(out_path)


def main():
    clone, candidates_path, out_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    data = json.loads(candidates_path.read_text(encoding='utf-8'))
    only = set(json.loads(Path(sys.argv[sys.argv.index('--only') + 1]).read_text())) if '--only' in sys.argv else None
    nuget_config = sys.argv[sys.argv.index('--nuget-config') + 1] if '--nuget-config' in sys.argv else None
    stubber = sys.argv[sys.argv.index('--stubber') + 1] if '--stubber' in sys.argv else None
    backfill = '--backfill-stubs' in sys.argv
    EXCLUDED.update(sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == '--exclude-project')
    files_by_commit = {}
    for c in data['candidates']:
        for window in c['runs']:
            pieces, current = [], []
            for h in window + [None]:
                if h is not None and (only is None or h in only):
                    current.append(h)
                else:
                    pieces.append(current)
                    current = []
            for piece in pieces:
                if len(piece) >= 2:
                    for h in piece:
                        files_by_commit.setdefault(h, set()).add(c['path'])
    records = {}
    if out_path.exists():
        for line in out_path.read_text(encoding='utf-8').splitlines():
            if line.strip():
                r = json.loads(line)
                records[r['commit']] = r
    commits = sorted(files_by_commit, key=lambda h: data['commits'][h]['date'])
    results_dir = out_path.parent / 'trx'
    results_dir.mkdir(exist_ok=True)
    max_commits = int(sys.argv[sys.argv.index('--max-commits') + 1]) if '--max-commits' in sys.argv else None
    rel = lambda p: str(Path(p).relative_to(clone))
    processed = 0
    for i, h in enumerate(commits, 1):
        record = records.get(h)
        if record is not None:
            pending = [t for t in record['pre'] if stubber and backfill and needs_stub(record, t) and t not in record.get('stub', {})]
            if not pending:
                continue
            git(clone, 'checkout', '-f', '-q', h)
            for n, target in enumerate(pending):
                record.setdefault('stub', {})[target] = stub_run(clone, h, target, [clone / p for p in record['target_projects'][target]],
                                                                 record, results_dir, nuget_config, stubber, fresh=n == 0)
            save(out_path, records)
            print(f'{i}/{len(commits)} {h[:10]} backfilled stubs={len(pending)}', flush=True)
        else:
            git(clone, 'checkout', '-f', '-q', h)
            changed = data['commits'][h]['files']
            tests = sorted({p for p in changed if 'test' in p.lower() and p.endswith('.cs') and (clone / p).exists()})
            per_target = {t: test_projects_for(clone, t, tests) for t in sorted(files_by_commit[h])}
            projects = sorted({p for ps in per_target.values() for p in ps})
            record = dict(commit=h, date=data['commits'][h]['date'], test_projects=[rel(p) for p in projects],
                          target_projects={t: [rel(p) for p in ps] for t, ps in per_target.items()}, post={}, pre={}, stub={})
            for project in projects:
                for stale in ('bin', 'obj'):
                    shutil.rmtree(project.parent / stale, ignore_errors=True)
                record['post'][rel(project)] = run_tests(clone, project, results_dir, nuget_config)
            for target, target_projects in per_target.items():
                entry = record['pre'][target] = {}
                try:
                    parent_version = git(clone, 'show', f'{h}^:{target}')
                except subprocess.CalledProcessError:
                    entry['status'] = 'absent_in_parent'
                    continue
                (clone / target).write_bytes(parent_version)
                for project in target_projects:
                    if record['post'][rel(project)]['status'] == 'ran':
                        entry[rel(project)] = run_tests(clone, project, results_dir, nuget_config, no_restore=True)
                git(clone, 'checkout', '-q', h, '--', target)
                if stubber and needs_stub(record, target):
                    record['stub'][target] = stub_run(clone, h, target, target_projects, record, results_dir, nuget_config, stubber, fresh=False)
            records[h] = record
            save(out_path, records)
            print(f'{i}/{len(commits)} {h[:10]} projects={len(projects)} stubs={len(record["stub"])}', flush=True)
        processed += 1
        if max_commits and processed >= max_commits:
            break


if __name__ == '__main__':
    main()
