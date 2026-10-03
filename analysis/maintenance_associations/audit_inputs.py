"""Audit eligibility and retained inputs without extracting maintenance outcomes."""
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
EVOLUTION = ROOT / 'analysis/multilanguage_evolution'
CUTOFF = dt.datetime.fromisoformat('2026-09-14T00:00:00+00:00')
IDS = {'Odoo': 'odoo__odoo', 'Jenkins': 'jenkinsci__jenkins', 'Apache Tomcat': 'apache__tomcat'}

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def main():
    coverage = EVOLUTION / 'results/three-rule-annual-coverage.csv'
    with coverage.open(newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    histories = {name: json.loads((EVOLUTION / f'selection/histories/{rid}.json').read_text()) for name, rid in IDS.items()}
    output = []
    for row in rows:
        baseline = dt.datetime.fromisoformat(row['actual_commit_date'])
        if baseline.tzinfo is None:
            raise ValueError('Baseline timestamp must be timezone-aware')
        start = dt.datetime.fromisoformat(histories[row['repository']]['earliest_source']['committer_date'])
        reasons = []
        if row['status'] != 'complete':
            reasons.append('incomplete_detector_observation')
        if baseline + dt.timedelta(days=365) > CUTOFF:
            reasons.append('insufficient_follow_up_before_cutoff')
        if baseline - dt.timedelta(days=365) < start:
            reasons.append('insufficient_preserved_baseline_history')
        output.append({
            'repository': row['repository'], 'rule': row['rule'], 'snapshot': row['snapshot'],
            'commit': row['commit'], 'baseline_utc': baseline.astimezone(dt.timezone.utc).isoformat(),
            'follow_up_end_utc': (baseline + dt.timedelta(days=365)).astimezone(dt.timezone.utc).isoformat(),
            'temporally_eligible': not reasons, 'exclusion_reasons': ';'.join(reasons),
            'scientifically_admitted': False,
        })
    paths = [HERE / 'PROTOCOL.md', Path(__file__), coverage, EVOLUTION / 'results/three-rule-evidence.tar.gz', EVOLUTION / 'results/three-rule-replay-evidence.json']
    inventory = {str(p.relative_to(ROOT)): {'exists': p.is_file(), 'sha256': sha(p) if p.is_file() else None} for p in paths}
    report = {
        'protocol_version': '0.1', 'cutoff_utc': CUTOFF.isoformat(),
        'meaning': 'Temporal eligibility is not data completeness or scientific admission.',
        'input_inventory': inventory,
        'temporary_git_cache_present': Path('/tmp/multilanguage-evolution-git').is_dir(),
        'persistent_git_cache_present': {rid: (ROOT / 'tmp/maintenance-associations/git' / rid / 'HEAD').is_file() for rid in IDS.values()},
        'source_archive_count': len(list((ROOT / 'tmp/multilanguage-evolution/annual-sources').glob('*.tar'))),
        'counts': {},
        'outcomes_extracted': False, 'associations_estimated': False,
        'outstanding': ['verify retained Git histories', 'validate detector decisions', 'audit issue/PR coverage', 'validate corrective-change labels', 'extract canonical changes and lineage'],
    }
    for name in IDS:
        report['counts'][name] = {}
        for rule in sorted({r['rule'] for r in output}):
            group = [r for r in output if r['repository'] == name and r['rule'] == rule]
            report['counts'][name][rule] = {'scheduled': len(group), 'temporally_eligible': sum(r['temporally_eligible'] for r in group)}
    result_dir = HERE / 'results'
    result_dir.mkdir(exist_ok=True)
    with (result_dir / 'baseline-eligibility.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)
    (result_dir / 'input-audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['counts', 'temporary_git_cache_present', 'source_archive_count', 'outcomes_extracted', 'associations_estimated']}, indent=2))

if __name__ == '__main__':
    main()
