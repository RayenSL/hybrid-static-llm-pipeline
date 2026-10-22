"""Sampling frame for the shadow-loop study (protocol v0.5, Section 5). Makes no model calls.

Usage: python shadow_frame.py --introductions DIR --clone CLONE --out DIR [--seed S] [--max-files N]
Reads introductions.jsonl from the introduction audit, applies the cheap eligibility filters (no build needed), and writes
frame.json: the hash-ordered candidate list per stratum that the oracle pilot and the run draw from in order.
"""
import argparse
import collections
import hashlib
import json
import subprocess
from pathlib import Path

from introduction_audit import band, ordinary

SEED = 'reaccrual-v0.5'
BYTES_PER_TOKEN = 3.5
CONTEXT_TOKENS = 32_000


def rank(seed, commit, symbol):
    return hashlib.sha256(f'{seed}|{commit}|{symbol}'.encode()).hexdigest()


def stratum(finding):
    return f"{finding['subtype']}|{band(finding['complexity'])}"


def candidates(records, limit_tokens=CONTEXT_TOKENS, sizes=None):
    """One genuine Long Method introduction per commit: the most complex, then the smallest symbol; within the file-size bound."""
    chosen = []
    for record in records:
        genuine = [f for f in record['long_method'] if f['kind'] == 'genuine']
        if limit_tokens is not None:
            genuine = [f for f in genuine if sizes and (record['commit'], f['file']) in sizes
                       and sizes[record['commit'], f['file']] / BYTES_PER_TOKEN <= limit_tokens]
        if genuine:
            best = sorted(genuine, key=lambda f: (-f['complexity'], f['symbol']))[0]
            chosen.append(dict(best, commit=record['commit'], date=record['date'], stratum=stratum(best)))
    return chosen


def ordered(rows, seed):
    """Hash order within each stratum; strata are listed alphabetically."""
    by_stratum = collections.defaultdict(list)
    for row in rows:
        by_stratum[row['stratum']].append(row)
    return [r for s in sorted(by_stratum) for r in sorted(by_stratum[s], key=lambda r: rank(seed, r['commit'], r['symbol']))]


def file_sizes(clone, records):
    wanted = {(r['commit'], f['file']) for r in records for f in r['long_method'] if f['kind'] == 'genuine'}
    process = subprocess.Popen(['git', '-C', str(clone), 'cat-file', '--batch-check'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    sizes = {}
    for commit, path in sorted(wanted):
        process.stdin.write(f'{commit}:{path}\n'.encode('utf-8'))
        process.stdin.flush()
        header = process.stdout.readline().split()
        if len(header) == 3 and header[1] == b'blob':
            sizes[commit, path] = int(header[2])
    process.stdin.close()
    process.wait()
    return sizes


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--introductions', type=Path, required=True)
    p.add_argument('--clone', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--seed', default=SEED)
    p.add_argument('--max-files', type=int, default=10)
    a = p.parse_args()
    everything = [json.loads(line) for line in (a.introductions / 'introductions.jsonl').read_text(encoding='utf-8').splitlines()]
    records = ordinary(everything, a.max_files)
    sizes = file_sizes(a.clone, records)
    unbounded = candidates(records, None)
    bounded = candidates(records, CONTEXT_TOKENS, sizes)
    rows = ordered(bounded, a.seed)
    funnel = dict(commits_scanned=len(everything), ordinary_commits=len(records), max_files=a.max_files, commits_with_genuine_introduction=len(unbounded), within_context_bound=len(bounded),
                  by_stratum=dict(collections.Counter(r['stratum'] for r in bounded)),
                  by_year=dict(sorted(collections.Counter(r['date'][:4] for r in bounded).items())),
                  oversize=len(unbounded) - len(bounded))
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / 'frame.json').write_text(json.dumps(dict(seed=a.seed, funnel=funnel, candidates=rows), indent=1), encoding='utf-8')
    print(json.dumps(funnel, indent=1))


if __name__ == '__main__':
    main()
