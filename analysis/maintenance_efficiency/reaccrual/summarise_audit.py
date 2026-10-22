"""Second audit stage: eligible replay windows, t0 detection, bands, SESOI and context sizes. No model calls.

Usage: python summarise_audit.py <work-dir> <t0-clone> <pipeline-repo> <decision-burden-dll> [--solution REL] [--complete-only] [--include-unchecked] [--exclude-project NAME ...]
<work-dir> holds phase1-candidates.json and f2p-results.jsonl; outputs go there too.
"""
import hashlib
import json
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

SEED = 'reaccrual-v0.2'
MAX_K = 4
WMC_BOUND, CC_BOUND = 47, 10


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def git(clone, *args):
    return subprocess.run(['git', '-C', str(clone), *args], capture_output=True, check=True).stdout


QUALIFYING = {'test', 'stub'}
BYTES_PER_TOKEN = 3.5
TOKEN_BOUND_FOR_FILE = 22000
EXCLUDED = set()


def flips(record, runs):
    """Tests passing after the commit that do not pass in the given runs."""
    found = 0
    for project, post in record['post'].items():
        if Path(project).stem in EXCLUDED:
            continue
        run = runs.get(project)
        if post['status'] == 'ran' and isinstance(run, dict) and run.get('status') == 'ran':
            found += sum(1 for t, o in post['outcomes'].items() if o == 'Passed' and run['outcomes'].get(t) != 'Passed')
    return found


def f2p_kind(record, target):
    """'test': tests fail on the pre-commit file; 'stub': tests fail with the commit's changed members stubbed;
    'unchecked': the pre-commit file does not build and stubbing exposes no failing test; None: nothing changes."""
    pre = record['pre'].get(target, {})
    if flips(record, pre):
        return 'test'
    if any(isinstance(v, dict) and v.get('status') == 'build_failed' and Path(k).stem not in EXCLUDED for k, v in pre.items()):
        return 'stub' if flips(record, record.get('stub', {}).get(target, {})) else 'unchecked'
    return None


def windows(candidates, results, qualifying=QUALIFYING):
    chosen = []
    for c in candidates:
        best = None
        for run in c['runs']:
            current = []
            for h in run + [None]:
                kind = f2p_kind(results[h], c['path']) if h in results else None
                if h is not None and kind in qualifying:
                    current.append((h, kind))
                    continue
                if len(current) >= 2 and (best is None or len(current) > len(best)):
                    best = current
                current = []
        if best:
            chosen.append(dict(path=c['path'], steps=best[:MAX_K]))
    return chosen


def detect(t0, t0_clone, pipeline, solution, out_dir):
    out = out_dir / f'{t0}.json'
    if not out.exists():
        git(t0_clone, 'checkout', '-f', '-q', t0)
        subprocess.run(['dotnet', 'restore', str(t0_clone / solution), '-p:NuGetAudit=false'], capture_output=True)
        subprocess.run(['dotnet', 'run', '--project', str(pipeline / 'src/HybridLens.CLI'), '--', 'analyse',
                        '--target', str(t0_clone / solution), '--dry-run', '--format', 'json',
                        '--severity', 'Warning', '--output', str(out)], capture_output=True)
    return json.loads(out.read_text(encoding='utf-8-sig'))['findings'] if out.exists() else None


def burden(clone, dll, versions):
    with tempfile.TemporaryDirectory() as tmp:
        for key, (commit, path) in versions.items():
            try:
                Path(tmp, key + '.cs').write_bytes(git(clone, 'show', f'{commit}:{path}'))
            except subprocess.CalledProcessError:
                pass
        return json.loads(subprocess.run(['dotnet', dll, tmp], capture_output=True, text=True, check=True).stdout)


def band(finding):
    m = finding['metrics']
    if finding['type'] == 'godClass':
        return 'borderline' if m['WMC'] <= WMC_BOUND * 1.1 else 'clear_cut'
    return 'borderline' if m['CyclomaticComplexity'] == CC_BOUND + 1 else 'clear_cut'


def main():
    work, t0_clone, pipeline, dll = (Path(a) for a in sys.argv[1:5])
    solution = sys.argv[sys.argv.index('--solution') + 1] if '--solution' in sys.argv else 'Ibis.Calculeren/IbisCalculeren.sln'
    data = json.loads((work / 'phase1-candidates.json').read_text(encoding='utf-8'))
    results = {}
    for line in (work / 'f2p-results.jsonl').read_text(encoding='utf-8').splitlines():
        if line.strip():
            r = json.loads(line)
            results[r['commit']] = r
    complete_only = '--complete-only' in sys.argv
    EXCLUDED.update(sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == '--exclude-project')
    tested = [c for c in data['candidates']
              if (all if complete_only else any)(h in results for run in c['runs'] for h in run)]
    found = windows(tested, results, QUALIFYING | {'unchecked'} if '--include-unchecked' in sys.argv else QUALIFYING)
    detections = work / 't0-findings'
    detections.mkdir(exist_ok=True)
    targets, excluded = [], []
    for w in found:
        first = w['steps'][0][0]
        t0 = git(t0_clone, 'rev-parse', f'{first}^').decode().strip()
        findings = detect(t0, t0_clone, pipeline, solution, detections)
        if findings is None:
            excluded.append(dict(path=w['path'], reason='detector_failed_at_t0'))
            continue
        local = [f for f in findings if f['type'] in ('godClass', 'longMethod')
                 and 'Ibis.Calculeren/' + f['filePath'].replace(chr(92), '/') == w['path']]
        if not local:
            excluded.append(dict(path=w['path'], reason='not_flagged_at_t0'))
            continue
        preferred = [f for f in local if f['type'] == 'godClass'] or local
        pick = min(preferred, key=lambda f: sha(f"{SEED}|{w['path']}|{f['symbolName']}|{f['line']}"))
        last = w['steps'][-1][0]
        m = burden(t0_clone, str(dll), {'t0': (t0, w['path']), 'last': (last, w['path'])})
        if 't0' not in m or 'last' not in m:
            excluded.append(dict(path=w['path'], reason='file_unreadable'))
            continue
        k = len(w['steps'])
        targets.append(dict(path=w['path'], symbol=pick['symbolName'], type=pick['type'], band=band(pick),
                            metrics=pick.get('metrics'), t0=t0, k=k, steps=w['steps'],
                            f2p_kinds=[kind for _, kind in w['steps']],
                            bytes_t0=m['t0']['bytes'], decision_burden_t0=m['t0']['decision_burden'],
                            decision_burden_last=m['last']['decision_burden'],
                            developer_accrual_per_change=(m['last']['decision_burden'] - m['t0']['decision_burden']) / k))
    for t in targets:
        t['context'] = 'excluded' if t['bytes_t0'] > 28000 else ('tight' if t['bytes_t0'] > 16000 else 'fits')
        t['approx_tokens_t0'] = round(t['bytes_t0'] / BYTES_PER_TOKEN)
    eligible = [t for t in targets if t['context'] != 'excluded']
    token_eligible = [t for t in targets if t['approx_tokens_t0'] <= TOKEN_BOUND_FOR_FILE]
    summary = dict(
        candidate_files=len(data['candidates']), tested_files=len(tested), windows_with_k_ge_2=len(found),
        exclusions=excluded, targets=len(targets), eligible_after_context=len(eligible),
        by_type={ty: sum(t['type'] == ty for t in eligible) for ty in ('godClass', 'longMethod')},
        by_band={b: sum(t['band'] == b for t in eligible) for b in ('clear_cut', 'borderline')},
        k_distribution={k: sum(t['k'] == k for t in eligible) for k in (2, 3, 4)},
        step_kinds={k: sum(kind == k for t in eligible for kind in t['f2p_kinds']) for k in sorted(QUALIFYING)},
        windows_if_unchecked_steps_counted=len(windows(tested, results, QUALIFYING | {'unchecked'})),
        context=dict(fits=sum(t['context'] == 'fits' for t in targets), tight=sum(t['context'] == 'tight' for t in targets),
                     excluded=sum(t['context'] == 'excluded' for t in targets)),
        sesoi={ty: (statistics.median([t['developer_accrual_per_change'] for t in eligible if t['type'] == ty]) / 2
                    if any(t['type'] == ty for t in eligible) else None) for ty in ('godClass', 'longMethod')},
        developer_accrual_per_change={ty: [round(t['developer_accrual_per_change'], 2) for t in eligible if t['type'] == ty]
                                      for ty in ('godClass', 'longMethod')},
    )
    summary['go'] = len(eligible) >= 12 and summary['by_type']['godClass'] >= 4 and summary['by_type']['longMethod'] >= 4
    token_types = {ty: sum(t['type'] == ty for t in token_eligible) for ty in ('godClass', 'longMethod')}
    summary['token_based_context_estimate'] = dict(
        assumption=f'{BYTES_PER_TOKEN} bytes per token; file share of the prompt <= {TOKEN_BOUND_FOR_FILE} tokens (unverified for the deployment)',
        eligible=len(token_eligible), by_type=token_types,
        go=len(token_eligible) >= 12 and token_types['godClass'] >= 4 and token_types['longMethod'] >= 4)
    summary['file_size_bytes'] = sorted(t['bytes_t0'] for t in targets)
    (work / 'eligible-targets.json').write_text(json.dumps(targets, indent=1), encoding='utf-8')
    (work / 'audit-summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
