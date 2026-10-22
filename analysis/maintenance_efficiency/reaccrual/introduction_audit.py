"""Debt-introduction audit of a git history (protocol v0.5, Section 7). Makes no model calls and builds nothing.

Usage: python introduction_audit.py --clone CLONE --out DIR [--limit N]
For every non-merge commit, the changed production C# files are measured before and after with the syntax-only detector facts
(DesignQuality --history-metrics): Long Method findings exactly as the thesis detector reports them, and class WMC as the necessary
syntactic part of the God Class rule. Findings are keyed by symbol, as the repair verifier keys them.
Output is private (per-commit records name real symbols); only the aggregate summary is meant to leave the output folder.
"""
import argparse
import collections
import json
import re
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DLL = REPO / 'src/HybridLens.DesignQuality/bin/Debug/net10.0/HybridLens.DesignQuality.dll'
LM_BOUND = 10
GC_WMC = 47
CHUNK = 150
GENERATED = re.compile(r'(\.Designer|\.g|\.g\.i|\.generated)\.cs$', re.IGNORECASE)


def is_production(path):
    if not path or not path.endswith('.cs') or GENERATED.search(path):
        return False
    return not any('test' in segment.lower() for segment in path.split('/'))


def parse_name_status(raw):
    tokens = [t.decode('utf-8', errors='replace') for t in raw.split(b'\x00') if t]
    entries, i = [], 0
    while i < len(tokens):
        status = tokens[i]
        if status[0] in 'RC':
            entries.append((status[0], tokens[i + 1], tokens[i + 2]))
            i += 3
        else:
            path = tokens[i + 1]
            entries.append((status[0], None if status[0] == 'A' else path, None if status[0] == 'D' else path))
            i += 2
    return entries


def band(complexity):
    if complexity <= 11:
        return '11'
    if complexity <= 14:
        return '12-14'
    return '15-19' if complexity <= 19 else '20+'


def by_symbol(methods):
    best = {}
    for m in methods:
        if m['symbol'] not in best or m['complexity'] > best[m['symbol']]['complexity']:
            best[m['symbol']] = m
    return best


def gone_long_methods(before, after):
    """Methods that were Long Methods before and are not after (renamed, moved, shortened or deleted)."""
    bm, am = by_symbol(before), by_symbol(after)
    return [m for s, m in bm.items() if m['complexity'] > LM_BOUND and not (s in am and am[s]['complexity'] > LM_BOUND)]


def long_method_introductions(before, after, gone_elsewhere):
    b, a = by_symbol(before), by_symbol(after)
    before_long = {s for s, m in b.items() if m['complexity'] > LM_BOUND}
    after_long = {s for s, m in a.items() if m['complexity'] > LM_BOUND}
    gone = gone_long_methods(before, after) + list(gone_elsewhere)
    moved = {m['symbol'] for m in gone_elsewhere}
    found = []
    for symbol in sorted(after_long - before_long):
        m = a[symbol]
        renamed = any(d['complexity'] == m['complexity'] and abs(d['lines'] - m['lines']) <= 2 for d in gone)
        kind = 'relocation' if symbol in moved else ('rename' if renamed else 'genuine')
        found.append(dict(symbol=symbol, complexity=m['complexity'], lines=m['lines'], line=m['line'],
                          subtype='crossing' if symbol in b else 'new_method', kind=kind))
    return found


def god_class_candidates(before, after, gone_elsewhere):
    b, a = {c['symbol']: c for c in before}, {c['symbol']: c for c in after}
    found = []
    for symbol, c in sorted(a.items()):
        if c['wmc'] >= GC_WMC and not (symbol in b and b[symbol]['wmc'] >= GC_WMC):
            found.append(dict(symbol=symbol, wmc=c['wmc'], line=c['line'], subtype='crossing' if symbol in b else 'new_class',
                              kind='relocation' if symbol in gone_elsewhere else 'genuine'))
    return found


def ordinary(records, max_files):
    """Commits an individual developer plausibly made: at least one and at most max_files production files."""
    return [r for r in records if 1 <= len(r['production_files']) <= max_files]


class Blobs:
    def __init__(self, clone):
        self.process = subprocess.Popen(['git', '-C', str(clone), 'cat-file', '--batch'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def get(self, revision, path):
        self.process.stdin.write(f'{revision}:{path}\n'.encode('utf-8'))
        self.process.stdin.flush()
        header = self.process.stdout.readline().split()
        if len(header) < 3 or header[1] != b'blob':
            return None
        size = int(header[2])
        data = self.process.stdout.read(size)
        self.process.stdout.read(1)
        return data

    def close(self):
        self.process.stdin.close()
        self.process.wait()


def measure(files):
    """files: name -> bytes. Returns name -> facts from DesignQuality --history-metrics."""
    with tempfile.TemporaryDirectory() as tmp:
        for name, data in files.items():
            Path(tmp, f'{name}.cs').write_bytes(data)
        out = subprocess.run(['dotnet', str(DLL), '--history-metrics', tmp], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def commits(clone, limit=None):
    raw = subprocess.run(['git', '-C', str(clone), 'log', '--no-merges', '--reverse', '--date=short',
                          '--format=%H%x1f%P%x1f%ad%x1f%s'], capture_output=True, text=True, encoding='utf-8', errors='replace', check=True).stdout
    rows = [line.split('\x1f') for line in raw.splitlines() if line]
    rows = [(h, p.split(), d, s) for h, p, d, s in rows if len(p.split()) == 1]
    return rows[:limit] if limit else rows


def commit_record(commit, parent, date, subject, changes, facts_before, facts_after):
    """changes: [(status, old, new)] for production files; facts_*: path -> facts or None."""
    empty = dict(methods=[], classes=[])
    pairs = []
    for status, old, new in changes:
        before = facts_before.get(old) or empty
        after = facts_after.get(new) or empty
        pairs.append((old, new, before, after))
    gone_methods = {(old, new): gone_long_methods(b['methods'], a['methods']) for old, new, b, a in pairs}
    gone_classes = {(old, new): {c['symbol'] for c in b['classes'] if c['wmc'] >= GC_WMC} - {c['symbol'] for c in a['classes'] if c['wmc'] >= GC_WMC}
                    for old, new, b, a in pairs}
    lm, gc = [], []
    for old, new, before, after in pairs:
        if new is None or facts_after.get(new) is None:
            continue
        elsewhere = [m for key, ms in gone_methods.items() if key != (old, new) for m in ms]
        elsewhere_classes = set().union(*(s for key, s in gone_classes.items() if key != (old, new)))
        for f in long_method_introductions(before['methods'], after['methods'], elsewhere):
            lm.append(dict(f, file=new))
        for f in god_class_candidates(before['classes'], after['classes'], elsewhere_classes):
            gc.append(dict(f, file=new))
    return dict(commit=commit, parent=parent, date=date, subject=subject, production_files=[n for _, _, n in changes if n],
                long_method=lm, god_class_candidates=gc)


def scan(clone, out, limit=None):
    out.mkdir(parents=True, exist_ok=True)
    blobs = Blobs(clone)
    rows = commits(clone, limit)
    test_touch = {}
    records = []
    path = out / 'introductions.jsonl'
    with path.open('w', encoding='utf-8') as sink:
        for start in range(0, len(rows), CHUNK):
            batch = rows[start:start + CHUNK]
            files, plan = {}, []
            for commit, (parent,), date, subject in batch:
                raw = subprocess.run(['git', '-C', str(clone), 'diff-tree', '-r', '-M', '-z', '--no-commit-id', '--name-status', parent, commit],
                                     capture_output=True, check=True).stdout
                entries = parse_name_status(raw)
                test_touch[commit] = any(p and p.endswith('.cs') and any('test' in s.lower() for s in p.split('/')) for _, o, n in entries for p in (o, n))
                changes = [(s, o, n) for s, o, n in entries if is_production(n) or (s == 'D' and is_production(o))]
                for status, old, new in changes:
                    for side, revision, p in (('b', parent, old), ('a', commit, new)):
                        if p is None or (revision, p) in files:
                            continue
                        data = blobs.get(revision, p)
                        if data is not None:
                            files[(revision, p)] = data
                plan.append((commit, parent, date, subject, changes))
            names = {key: f'f{n}' for n, key in enumerate(files)}
            facts = measure({names[key]: data for key, data in files.items()}) if files else {}
            for commit, parent, date, subject, changes in plan:
                fb = {o: facts.get(names.get((parent, o))) for _, o, _ in changes if o}
                fa = {n: facts.get(names.get((commit, n))) for _, _, n in changes if n}
                record = commit_record(commit, parent, date, subject, changes, fb, fa)
                record['touches_tests'] = test_touch[commit]
                records.append(record)
                sink.write(json.dumps(record) + '\n')
            print(f'{min(start + CHUNK, len(rows))}/{len(rows)} commits', flush=True)
    blobs.close()
    return records


def summarise(records, head_long=None):
    genuine = [dict(f, commit=r['commit'], date=r['date'], touches_tests=r['touches_tests'], production_files=len(r['production_files']))
               for r in records for f in r['long_method'] if f['kind'] == 'genuine']
    gc_genuine = [dict(f, commit=r['commit'], date=r['date']) for r in records for f in r['god_class_candidates'] if f['kind'] == 'genuine']
    summary = dict(commits_scanned=len(records), commits_with_production_changes=sum(bool(r['production_files']) for r in records),
                   long_method=dict(
                       raw=sum(len(r['long_method']) for r in records),
                       by_kind=dict(collections.Counter(f['kind'] for r in records for f in r['long_method'])),
                       genuine=len(genuine), genuine_commits=len({f['commit'] for f in genuine}),
                       by_subtype=dict(collections.Counter(f['subtype'] for f in genuine)),
                       by_band=dict(collections.Counter(band(f['complexity']) for f in genuine)),
                       by_year=dict(sorted(collections.Counter(f['date'][:4] for f in genuine).items())),
                       with_tests_in_commit=sum(f['touches_tests'] for f in genuine),
                       single_file_commits=sum(f['production_files'] == 1 for f in genuine)),
                   god_class_candidates=dict(
                       raw=sum(len(r['god_class_candidates']) for r in records),
                       genuine=len(gc_genuine), genuine_commits=len({f['commit'] for f in gc_genuine}),
                       by_subtype=dict(collections.Counter(f['subtype'] for f in gc_genuine)),
                       by_year=dict(sorted(collections.Counter(f['date'][:4] for f in gc_genuine).items()))))
    if head_long is not None:
        summary['long_method']['still_long_at_head'] = sum(f['symbol'] in head_long for f in genuine)
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--clone', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--limit', type=int)
    p.add_argument('--head-findings', type=Path)
    p.add_argument('--from-records', action='store_true', help='re-summarise an existing introductions.jsonl without scanning')
    a = p.parse_args()
    if a.from_records:
        records = [json.loads(line) for line in (a.out / 'introductions.jsonl').read_text(encoding='utf-8').splitlines()]
    else:
        if not a.clone:
            raise SystemExit('--clone is required unless --from-records is given')
        records = scan(a.clone, a.out, a.limit)
    head_long = None
    if a.head_findings:
        findings = json.loads(a.head_findings.read_text(encoding='utf-8-sig'))
        findings = findings['findings'] if isinstance(findings, dict) else findings
        head_long = {f['symbolName'] for f in findings if f['type'] == 'longMethod'}
    summary = dict(all_commits=summarise(records, head_long),
                   **{f'ordinary_le_{n}': summarise(ordinary(records, n), head_long) for n in (3, 10, 30)})
    (a.out / 'summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
