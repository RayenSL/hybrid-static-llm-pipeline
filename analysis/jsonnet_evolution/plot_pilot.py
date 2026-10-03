#!/usr/bin/env python3
"""Generate the versioned pilot figure using only Python's standard library."""
from __future__ import annotations
import csv
import datetime as dt
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / 'pilot_results'
OUT = HERE / 'figures'
W, H = 1200, 800
LEFT, RIGHT = 105, 1145
TOP_Y0, TOP_Y1 = 150, 500
SIZE_Y0, SIZE_Y1 = 590, 715
START = dt.date(2007, 1, 1)
END = dt.date(2027, 1, 1)


def esc(value): return html.escape(str(value), quote=True)
def x_pos(date): return LEFT + (date - START).days / (END - START).days * (RIGHT - LEFT)
def y_top(value): return TOP_Y1 - value / 14.0 * (TOP_Y1 - TOP_Y0)
def y_size(value): return SIZE_Y1 - value / 75000.0 * (SIZE_Y1 - SIZE_Y0)
def path(points, y): return 'M ' + ' L '.join(f'{x_pos(p["date"]):.1f},{y(p["value"]):.1f}' for p in points)

protocol = json.loads((HERE / 'protocol.json').read_text())
manifest = json.loads((RESULTS / 'snapshot-manifest.json').read_text())
timestamps = {x['commit']: x['committer_unix'] for x in manifest['history']}
summary = {x['label']: x for x in csv.DictReader((RESULTS / 'pilot-summary.csv').open())}
rows = []
for sample in protocol['pilot_commits']:
    row = summary[sample['label']]
    rows.append({
        'label': sample['label'], 'commit': sample['commit'],
        'date': dt.datetime.fromtimestamp(timestamps[sample['commit']], dt.timezone.utc).date(),
        'framework': row['framework'], 'god': float(row['god_class_rate']) * 100,
        'long': float(row['long_method_rate']) * 100,
        'obsolete': float(row['obsolete_affected_files_rate']) * 100,
        'ploc': int(row['physical_lines'])
    })
rows.sort(key=lambda x: x['date'])
OUT.mkdir(exist_ok=True)
with (OUT / 'pilot_figure_data.csv').open('w', newline='', encoding='utf-8') as stream:
    writer = csv.DictWriter(stream, fieldnames=['label','commit','date','framework','god','long','obsolete','ploc'])
    writer.writeheader()
    for row in rows: writer.writerow({**row, 'date': row['date'].isoformat()})

series = [
    ('god', 'God Class / class declarations', '#0072B2', '', 'circle'),
    ('long', 'Long Method / method declarations', '#D55E00', '10 5', 'square'),
    ('obsolete', 'Files with obsolete API use / production files', '#009E73', '3 4', 'triangle')
]
parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">
<title id="title">Anti-pattern prevalence and production code size in Json.NET pilot snapshots</title>
<desc id="desc">Three normalized anti-pattern prevalence lines and a lower physical-lines-of-code line across five dated snapshots from 2007 through 2026.</desc>
<rect width="100%" height="100%" fill="white"/>
<style>
text {{ font-family: "DejaVu Sans", Arial, sans-serif; fill: #202124; }}
.axis {{ stroke: #343a40; stroke-width: 1.2; }}
.grid {{ stroke: #d9dee3; stroke-width: 1; }}
.note {{ fill: #59636e; }}
</style>
<text x="{LEFT}" y="43" font-size="25" font-weight="700">Anti-pattern prevalence and production code size in Json.NET</text>
<text x="{LEFT}" y="72" font-size="15" class="note">Five compatibility-pilot snapshots · points positioned by exact Git committer date</text>
<text x="{LEFT}" y="125" font-size="17" font-weight="700">Normalized anti-pattern prevalence</text>
<text transform="translate(31 385) rotate(-90)" font-size="14">Flagged units (%)</text>''']
# Top horizontal grid and labels.
for value in range(0, 15, 2):
    y = y_top(value)
    parts.append(f'<line class="grid" x1="{LEFT}" y1="{y:.1f}" x2="{RIGHT}" y2="{y:.1f}"/>')
    parts.append(f'<text x="{LEFT-14}" y="{y+5:.1f}" font-size="13" text-anchor="end">{value}</text>')
parts += [f'<line class="axis" x1="{LEFT}" y1="{TOP_Y0}" x2="{LEFT}" y2="{TOP_Y1}"/>',
          f'<line class="axis" x1="{LEFT}" y1="{TOP_Y1}" x2="{RIGHT}" y2="{TOP_Y1}"/>']
# Legend.
legend_x = LEFT
for key, label, color, dash, marker in series:
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ''
    parts.append(f'<line x1="{legend_x}" y1="100" x2="{legend_x+32}" y2="100" stroke="{color}" stroke-width="3"{dash_attr}/>')
    parts.append(f'<text x="{legend_x+40}" y="105" font-size="13">{esc(label)}</text>')
    legend_x += {'god': 275, 'long': 320, 'obsolete': 0}[key]
# Lines and accessible marker shapes.
for key, label, color, dash, marker in series:
    points = [{'date': r['date'], 'value': r[key]} for r in rows]
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ''
    parts.append(f'<path d="{path(points, y_top)}" fill="none" stroke="{color}" stroke-width="3" stroke-linejoin="round"{dash_attr}/>')
    for r in rows:
        x, y = x_pos(r['date']), y_top(r[key])
        if marker == 'circle': parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="white" stroke="{color}" stroke-width="3"/>')
        elif marker == 'square': parts.append(f'<rect x="{x-5:.1f}" y="{y-5:.1f}" width="10" height="10" fill="white" stroke="{color}" stroke-width="3"/>')
        else: parts.append(f'<path d="M{x:.1f},{y-6:.1f} L{x-6:.1f},{y+5:.1f} L{x+6:.1f},{y+5:.1f} Z" fill="white" stroke="{color}" stroke-width="3"/>')
# Size panel.
parts.append(f'<text x="{LEFT}" y="560" font-size="17" font-weight="700">Production code size</text>')
parts.append(f'<text transform="translate(31 700) rotate(-90)" font-size="14">Physical lines</text>')
for value in (0, 25000, 50000, 75000):
    y = y_size(value)
    parts.append(f'<line class="grid" x1="{LEFT}" y1="{y:.1f}" x2="{RIGHT}" y2="{y:.1f}"/>')
    parts.append(f'<text x="{LEFT-14}" y="{y+5:.1f}" font-size="13" text-anchor="end">{value//1000}k</text>')
parts += [f'<line class="axis" x1="{LEFT}" y1="{SIZE_Y0}" x2="{LEFT}" y2="{SIZE_Y1}"/>',
          f'<line class="axis" x1="{LEFT}" y1="{SIZE_Y1}" x2="{RIGHT}" y2="{SIZE_Y1}"/>']
size_points = [{'date': r['date'], 'value': r['ploc']} for r in rows]
parts.append(f'<path d="{path(size_points, y_size)}" fill="none" stroke="#6C4AB6" stroke-width="3"/>')
for r in rows:
    x, y = x_pos(r['date']), y_size(r['ploc'])
    parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="white" stroke="#6C4AB6" stroke-width="3"/>')
    parts.append(f'<text x="{x:.1f}" y="{y-11:.1f}" font-size="12" text-anchor="middle" fill="#553597">{r["ploc"]/1000:.1f}k</text>')
# Shared dated snapshot labels and vertical guides.
for r in rows:
    x = x_pos(r['date'])
    parts.append(f'<line x1="{x:.1f}" y1="{TOP_Y1}" x2="{x:.1f}" y2="{SIZE_Y1}" stroke="#edf0f2"/>')
    parts.append(f'<line class="axis" x1="{x:.1f}" y1="{SIZE_Y1}" x2="{x:.1f}" y2="{SIZE_Y1+6}"/>')
    parts.append(f'<text x="{x:.1f}" y="742" font-size="13" text-anchor="middle">{r["date"].isoformat()}</text>')
    parts.append(f'<text x="{x:.1f}" y="761" font-size="12" text-anchor="middle" class="note">{esc(r["framework"])}</text>')
parts.append('<text x="1145" y="786" font-size="11" text-anchor="end" class="note">PLOC includes blank and comment lines; production scope follows protocol 1.0.0.</text>')
parts.append('</svg>')
(OUT / 'jsonnet_pilot_timeline.svg').write_text('\n'.join(parts) + '\n', encoding='utf-8')
print(OUT / 'jsonnet_pilot_timeline.svg')
