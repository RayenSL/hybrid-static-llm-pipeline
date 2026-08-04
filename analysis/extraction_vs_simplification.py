#!/usr/bin/env python3
"""Classify every confirmatory repair as an extraction or a branch simplification.

Motivation (thesis §4.5.2, gaming guard). A repair is scored metric-resolved when the triggering
detector condition no longer fires. Because the detector measures cyclomatic complexity and WMC,
a repair could in principle cross the threshold by deleting unreachable or redundant branches
rather than by performing the intended Extract Method or Extract Class. The thesis currently
hedges about this. This script settles it from the frozen artefacts.

Input : experiments/<campaign>/campaign/viewable-codebases/*/{ASSIGNMENT.json,REPAIR.diff}
        experiments/<campaign>/results/attempts.json          (outcomes, joined on source ref)
Output: results/extraction-analysis/{repair_shape.csv,REPAIR_SHAPE_REPORT.md}

No model calls. No writes outside the output directory.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
from pathlib import Path

# A declaration line: one to six type/modifier tokens, then a name, then an open paren.
# Excludes control flow, calls (dotted receivers have no space before the paren) and
# statements terminated with a semicolon.
DECL = re.compile(r'^(?:[\w<>,\[\]\?\.]+\s+){1,6}([A-Za-z_]\w*)\s*\(')
CONTROL = re.compile(r'^(?:if|else|for|foreach|while|switch|case|return|throw|using|lock|'
                     r'try|catch|finally|yield|await|do)\b')
TYPE_DECL = re.compile(r'\b(?:class|record|struct|interface)\s+([A-Z]\w*)')
BRANCH = re.compile(r'^(?:if|else\s+if|else|switch|case)\b')


def parse_diff(text: str) -> dict:
    added, removed = [], []
    for raw in text.splitlines():
        if raw.startswith(('+++', '---', '@@', 'diff ', 'index ')):
            continue
        if raw.startswith('+'):
            added.append(raw[1:])
        elif raw.startswith('-'):
            removed.append(raw[1:])

    def decls(lines):
        names, types = [], []
        for l in lines:
            s = l.strip()
            t = TYPE_DECL.search(s)
            if t:
                types.append(t.group(1))
            if not s or s.endswith(';') or CONTROL.match(s):
                continue
            m = DECL.match(s)
            if m:
                names.append(m.group(1))
        return names, types

    added_methods, added_types = decls(added)
    removed_methods, removed_types = decls(removed)
    # A signature that merely moved or was reindented appears on both sides.
    net_methods = [m for m in added_methods if m not in removed_methods]
    net_types = [t for t in added_types if t not in removed_types]

    return {
        'added_lines': len(added),
        'removed_lines': len(removed),
        'net_lines': len(added) - len(removed),
        'new_methods': net_methods,
        'new_types': net_types,
        'branches_removed': sum(1 for l in removed if BRANCH.match(l.strip())),
        'branches_added': sum(1 for l in added if BRANCH.match(l.strip())),
    }


def classify(d: dict) -> str:
    """Primary shape. Extraction wins over simplification when both are present."""
    if d['new_types']:
        return 'extract_type'
    if d['new_methods']:
        return 'extract_method'
    if d['branches_removed'] > d['branches_added']:
        return 'simplify_only'
    if d['added_lines'] or d['removed_lines']:
        return 'other_edit'
    return 'no_change'


def load_strata(corpus: Path) -> dict:
    """symbol -> (instance_id, stratum). Long Method records key on Type.Method."""
    out = {}
    for f in sorted((corpus / 'ground-truth' / 'records').glob('*.json')):
        d = json.loads(f.read_text(encoding='utf-8'))
        sym = d['location']['symbol']
        key = '.'.join(sym.split('.')[-2:]) if d['anti_pattern'] == 'LongMethod' else sym
        out[key] = (d['instance_id'], d['stratum'])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--campaign', default='experiments/confirmatory-gpt56-sol-20260728')
    ap.add_argument('--repo-root', default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument('--corpus', default=r'Z:\GitHub\hybrid-pipeline-corpus',
                    help='corpus repo, for the severity stratum join')
    args = ap.parse_args()

    root = Path(args.repo_root)
    camp = root / args.campaign
    archive = camp / 'campaign' / 'viewable-codebases'
    outdir = camp / 'results' / 'extraction-analysis'
    outdir.mkdir(parents=True, exist_ok=True)

    outcomes = {}
    for a in json.loads((camp / 'results' / 'attempts.json').read_text(encoding='utf-8')):
        outcomes[a['materialized_source_ref']] = a

    strata = load_strata(Path(args.corpus))

    rows = []
    for d in sorted(archive.iterdir()):
        aj, dj = d / 'ASSIGNMENT.json', d / 'REPAIR.diff'
        if not aj.exists():
            continue
        asg = json.loads(aj.read_text(encoding='utf-8'))
        shape = parse_diff(dj.read_text(encoding='utf-8', errors='replace')) if dj.exists() else {
            'added_lines': 0, 'removed_lines': 0, 'net_lines': 0, 'new_methods': [],
            'new_types': [], 'branches_removed': 0, 'branches_added': 0}
        out = outcomes.get(asg.get('materialized_source_ref'), {})
        iid, stratum = strata.get(asg['symbol_name'], ('?', '?'))
        rows.append({
            'assignment_id': asg['assignment_id'],
            'instance_id': iid,
            'stratum': stratum,
            'symbol_name': asg['symbol_name'],
            'anti_pattern': asg['anti_pattern_type'],
            'grounding': asg['grounding_enabled'],
            'control': asg['control_structure'],
            'visible_test': asg['visible_tests_enabled'],
            'shape': classify(shape),
            'new_methods': ';'.join(shape['new_methods']),
            'new_types': ';'.join(shape['new_types']),
            'n_new_methods': len(shape['new_methods']),
            'n_new_types': len(shape['new_types']),
            'branches_removed': shape['branches_removed'],
            'branches_added': shape['branches_added'],
            'net_lines': shape['net_lines'],
            'metric_resolved': out.get('metric_resolved'),
            'strict_success': out.get('strict_success'),
            'private_test_passed': out.get('private_test_passed'),
        })

    with (outdir / 'repair_shape.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # ── report ────────────────────────────────────────────────────────────
    L = []
    L.append('# Repair shape: extraction against branch simplification\n')
    L.append(f'Classified {len(rows)} archived repairs from their frozen unified diffs. '
             'No model calls; outcomes joined from `attempts.json`.\n')

    order = ['extract_type', 'extract_method', 'simplify_only', 'other_edit', 'no_change']
    tot = collections.Counter(r['shape'] for r in rows)
    L.append('## Overall\n')
    L.append('| Shape | n | share |\n|---|---:|---:|')
    for s in order:
        if tot[s]:
            L.append(f'| {s} | {tot[s]} | {100*tot[s]/len(rows):.1f}% |')
    L.append('')

    res = [r for r in rows if r['metric_resolved']]
    unres = [r for r in rows if r['metric_resolved'] is False]
    nonext = [r for r in res if r['shape'] in ('simplify_only', 'other_edit', 'no_change')]
    L.append('## The gaming question\n')
    L.append(f'- metric-resolved repairs: **{len(res)}**')
    L.append(f'- of those, repairs that introduced no new method or type: '
             f'**{len(nonext)}** ({100*len(nonext)/len(res):.1f}%)')
    L.append(f'- of those, classified `simplify_only`: '
             f'**{sum(1 for r in nonext if r["shape"] == "simplify_only")}**')
    L.append(f'- metric-unresolved repairs: {len(unres)}\n')
    if nonext:
        L.append('Metric-resolved without extraction, by target:\n')
        L.append('| Target | Pattern | Arm | Shape | branches −/+ | net lines |\n|---|---|---|---|---|---:|')
        for r in sorted(nonext, key=lambda x: x['symbol_name']):
            arm = f"{'G' if r['grounding'] else 'U'}/{r['control'][:4]}/{'ON' if r['visible_test'] else 'OFF'}"
            L.append(f"| `{r['symbol_name']}` | {r['anti_pattern']} | {arm} | {r['shape']} | "
                     f"{r['branches_removed']}/{r['branches_added']} | {r['net_lines']:+} |")
        L.append('')

    L.append('## Where the non-repairs fall\n')
    L.append('Every unresolved attempt is a non-repair: the model returned the pristine source '
             'unchanged and reported an empty findings array. None is a failed edit.\n')
    L.append('| Stratum | attempts | non-repairs | rate |\n|---|---:|---:|---:|')
    for st in ('clear_cut', 'borderline'):
        sub = [r for r in rows if r['stratum'] == st]
        nc2 = [r for r in sub if r['shape'] == 'no_change']
        if sub:
            L.append(f'| {st} | {len(sub)} | {len(nc2)} | {100*len(nc2)/len(sub):.1f}% |')
    L.append('')
    L.append('| Grounding | Control | attempts | non-repairs |\n|---|---|---:|---:|')
    for g in (False, True):
        for c in ('single_shot', 'iterative'):
            sub = [r for r in rows if r['grounding'] == g and r['control'] == c]
            nc2 = [r for r in sub if r['shape'] == 'no_change']
            L.append(f"| {'grounded' if g else 'ungrounded'} | {c} | {len(sub)} | {len(nc2)} |")
    L.append('')

    L.append('## By arm\n')
    L.append('| Grounding | Control | Test | ' + ' | '.join(order) + ' | extraction rate |\n'
             '|---|---|---|' + '---:|' * (len(order) + 1))
    for g in (False, True):
        for c in ('single_shot', 'iterative'):
            for v in (False, True):
                sub = [r for r in rows if r['grounding'] == g and r['control'] == c
                       and r['visible_test'] == v]
                if not sub:
                    continue
                cnt = collections.Counter(r['shape'] for r in sub)
                ext = sum(cnt[s] for s in ('extract_type', 'extract_method'))
                L.append(f"| {'grounded' if g else 'ungrounded'} | {c} | {'ON' if v else 'OFF'} | "
                         + ' | '.join(str(cnt[s]) for s in order)
                         + f' | {100*ext/len(sub):.1f}% |')
    L.append('')

    L.append('## By anti-pattern\n')
    L.append('| Pattern | n | ' + ' | '.join(order) + ' | mean new methods | mean new types |\n'
             '|---|---:|' + '---:|' * (len(order) + 2))
    for p in sorted({r['anti_pattern'] for r in rows}):
        sub = [r for r in rows if r['anti_pattern'] == p]
        cnt = collections.Counter(r['shape'] for r in sub)
        L.append(f'| {p} | {len(sub)} | ' + ' | '.join(str(cnt[s]) for s in order)
                 + f" | {sum(r['n_new_methods'] for r in sub)/len(sub):.2f}"
                 + f" | {sum(r['n_new_types'] for r in sub)/len(sub):.2f} |")
    L.append('')

    L.append('## Per target\n')
    L.append('| Target | Pattern | n | extraction | simplify_only | other | mean branches removed |\n'
             '|---|---|---:|---:|---:|---:|---:|')
    for sym in sorted({r['symbol_name'] for r in rows}):
        sub = [r for r in rows if r['symbol_name'] == sym]
        cnt = collections.Counter(r['shape'] for r in sub)
        ext = cnt['extract_type'] + cnt['extract_method']
        L.append(f"| `{sym}` | {sub[0]['anti_pattern']} | {len(sub)} | {ext} | "
                 f"{cnt['simplify_only']} | {cnt['other_edit'] + cnt['no_change']} | "
                 f"{sum(r['branches_removed'] for r in sub)/len(sub):.1f} |")

    (outdir / 'REPAIR_SHAPE_REPORT.md').write_text('\n'.join(L) + '\n', encoding='utf-8',
                                                   newline='\n')
    print(f'wrote {outdir.relative_to(root)}/repair_shape.csv and REPAIR_SHAPE_REPORT.md')
    print(f'\n{len(rows)} repairs | ' + ', '.join(f'{s}={tot[s]}' for s in order if tot[s]))
    print(f'metric-resolved without any extraction: {len(nonext)} / {len(res)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
