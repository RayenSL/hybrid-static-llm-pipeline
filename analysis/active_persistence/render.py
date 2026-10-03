"""Render the descriptive active-file redetection figure from summary.csv."""
from __future__ import annotations
import argparse
import csv
from pathlib import Path
from reportlab.lib.colors import HexColor, Color
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / 'analysis/active_persistence/results/v1.0'
RULES = [('LongMethod', 'Long Method', '#355C7D'),
         ('GodClass', 'God Class', '#2A8C82'),
         ('ObsoleteApiUsage', 'Obsolete API Usage', '#BD683A')]
REPOS = [('odoo__odoo', 'Odoo'), ('jenkinsci__jenkins', 'Jenkins'),
         ('apache__tomcat', 'Apache Tomcat')]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', type=Path, default=DEFAULT)
    args = parser.parse_args()
    results = args.results.resolve()
    with (results / 'summary.csv').open(newline='', encoding='utf8') as f:
        data = {(r['repository'], r['rule']): r for r in csv.DictReader(f)}
    destination = results / 'active-file-redetection.pdf'
    if destination.exists():
        raise SystemExit(f'Refusing to overwrite {destination}')
    width, height = 720, 380
    c = canvas.Canvas(str(destination), pagesize=(width, height), pageCompression=0, invariant=1)
    c.setTitle('Anti-pattern redetection in changing production files')
    c.setAuthor('Reproducible annual detector study')
    c.setFillColor(HexColor('#152837'))
    c.setFont('Helvetica-Bold', 15)
    c.drawString(28, 347, 'Findings redetected after the source file changed')
    c.setFont('Helvetica', 9)
    c.setFillColor(HexColor('#44505A'))
    c.drawString(28, 330, 'Consecutive complete annual scans, 2007-2025')
    x0, x1 = 238, 610
    for v in [0, .25, .5, .75, 1]:
        x = x0 + (x1 - x0) * v
        c.setStrokeColor(HexColor('#DBE0E4'))
        c.line(x, 66, x, 307)
        c.setFillColor(HexColor('#44505A'))
        c.setFont('Helvetica', 8)
        c.drawCentredString(x, 54, f'{int(v*100)}%')
    y = 293
    for repo, repo_label in REPOS:
        c.setFillColor(HexColor('#152837'))
        c.setFont('Helvetica-Bold', 9)
        c.drawString(28, y + 8, repo_label)
        for rule, label, colour in RULES:
            row = data[(repo, rule)]
            n = int(row['changed_file_findings'])
            share = float(row['changed_file_redetection_share']) if row['changed_file_redetection_share'] else 0
            c.setFont('Helvetica', 8.5)
            c.setFillColor(HexColor('#354653'))
            c.drawString(88, y, label)
            c.setFillColor(HexColor(colour))
            c.rect(x0, y - 2, (x1 - x0) * share, 8, fill=1, stroke=0)
            c.setFillColor(HexColor('#152837'))
            c.setFont('Helvetica', 8)
            c.drawString(615, y, f'{share:.1%}  (n={n:,})')
            y -= 22
        y -= 15
    c.setFillColor(HexColor('#44505A'))
    c.setFont('Helvetica', 7.5)
    c.drawString(28, 25, 'Redetection means the same path and symbol were flagged at the next scan. File changes may affect other code.')
    c.drawString(28, 14, 'API findings lack a full annual reference inventory; their absence cannot be interpreted as confirmed repair.')
    c.showPage()
    c.save()
    print(destination)

if __name__ == '__main__':
    main()
