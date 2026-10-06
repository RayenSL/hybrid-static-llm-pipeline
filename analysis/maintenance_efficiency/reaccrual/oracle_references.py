"""Does the oracle's test code mention the unit file's types? (protocol v0.5, Section 8.4). Makes no model calls and builds nothing.

Usage: python oracle_references.py --rows pilot.json --clone CLONE --out FILE
A unit's oracle is any test project that references the file's project. That is a regression check on dependents, and it need not
execute the unit file. As an objective proxy for "the tests exercise this file", the check looks for a type declared in the unit file
as a whole word in the oracle test sources at the post-commit state. A mention is necessary for a direct test, not sufficient.
"""
import argparse
import collections
import json
import re
import subprocess
from pathlib import Path

DECLARATION = re.compile(r'^\s*(?:(?:public|internal|private|protected|sealed|static|abstract|partial|readonly|unsafe)\s+)*'
                         r'(?:class|struct|interface|enum|record(?:\s+(?:class|struct))?)\s+([A-Za-z_]\w*)', re.MULTILINE)
EXCLUDED_SEGMENTS = ('UI.Tests', 'IntegratieTests', 'E2E')


def declared_types(source):
    return DECLARATION.findall(source)


def is_oracle_path(path):
    segments = path.split('/')
    if not path.endswith('.cs') or not any('test' in s.lower() for s in segments):
        return False
    return not any(any(x.lower() in s.lower() for x in EXCLUDED_SEGMENTS) for s in segments)


def classify(matching_paths):
    return 'direct' if matching_paths else 'dependent_only'


def check(clone, commit, path):
    source = subprocess.run(['git', '-C', str(clone), 'show', f'{commit}:{path}'], capture_output=True, text=True,
                            encoding='utf-8', errors='replace', check=True).stdout
    types = declared_types(source)
    if not types:
        return types, []
    args = ['git', '-C', str(clone), 'grep', '-l', '-w', '-F', '-I']
    for t in types:
        args += ['-e', t]
    out = subprocess.run(args + [commit, '--', '*.cs'], capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
    return types, [line.split(':', 1)[1] for line in out.splitlines() if ':' in line and is_oracle_path(line.split(':', 1)[1])]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--rows', type=Path, required=True)
    p.add_argument('--clone', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    rows = json.loads(a.rows.read_text(encoding='utf-8'))
    results = []
    for row in rows:
        types, paths = check(a.clone, row['commit'], row['file'])
        results.append(dict(commit=row['commit'], symbol=row['symbol'], file=row['file'], stratum=row['stratum'], types=types,
                            matching_test_files=len(paths), kind=classify(paths)))
    a.out.write_text(json.dumps(results, indent=1), encoding='utf-8')
    print(json.dumps(dict(units=len(results), kinds=dict(collections.Counter(r['kind'] for r in results))), indent=1))


if __name__ == '__main__':
    main()
