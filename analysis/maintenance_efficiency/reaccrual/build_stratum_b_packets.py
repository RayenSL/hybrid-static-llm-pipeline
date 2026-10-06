"""Build R2's stratum-B authoring packets (STRATUM_B_TASK_SPEC.md). Repaired sources are deliberately excluded.

Usage: python build_stratum_b_packets.py <output-dir>
"""
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = HERE.parents[2]
VALIDATION = ['GC-02', 'GC-03', 'GC-04', 'GC-05', 'GC-07', 'GC-08', 'GC-09', 'GC-10', 'GC-11', 'GC-12', 'GC-13',
              'LM-01', 'LM-03', 'LM-06', 'LM-07', 'LM-08', 'LM-09', 'LM-10', 'LM-11', 'LM-12', 'LM-13']
STEP_FILES = ['requirement.md', 'family.txt', 'tests.cs', 'reference.cs', 'mutant1.cs', 'mutant2.cs', 'superseded.txt']


def oracle_material(project, stem):
    drivers = REPO / 'layer3' / 'characterization'
    named = drivers / f'Drivers.{project}.cs'
    found = [named] if named.exists() else [p for p in drivers.glob('Drivers.*.cs') if stem in p.read_text(encoding='utf-8', errors='replace')]
    golden = sorted((REPO / 'layer3' / 'golden').glob(f'{stem}.*'))
    return [str(p.relative_to(REPO)) for p in found + golden]


def main():
    out = Path(sys.argv[1])
    if out.exists():
        raise SystemExit('Output exists: packets are built once')
    pairs = {p['target_id']: p for p in json.loads((ROOT / 'generated' / 'campaign.json').read_text(encoding='utf-8'))['pairs']}
    for target in VALIDATION:
        pair = pairs[target]
        original = (ROOT / pair['baseline_path']).resolve()
        project = original.parent.name
        folder = out / target
        (folder / 'supporting').mkdir(parents=True)
        shutil.copyfile(original, folder / 'original.cs')
        for sibling in sorted(original.parent.glob('*.cs')):
            if sibling != original:
                shutil.copyfile(sibling, folder / 'supporting' / sibling.name)
        (folder / 'oracle-drivers.txt').write_text('\n'.join(oracle_material(project, original.stem)) + '\n', encoding='utf-8')
        for k in range(1, 5):
            step = folder / 'steps' / f'S{k}'
            step.mkdir(parents=True)
            for name in STEP_FILES:
                (step / name).touch()
        (folder / 'target.json').write_text(json.dumps(dict(target_id=target, file=pair['relative_file'], project=project,
                                                            baseline_sha256=pair['baseline_sha256']), indent=1), encoding='utf-8')
    print(f'{len(VALIDATION)} packets written to {out}')


if __name__ == '__main__':
    main()
