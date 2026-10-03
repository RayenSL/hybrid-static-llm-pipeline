#!/usr/bin/env python3
"""Generate the protocol-1.1.0 annual figure using Python's standard library."""
from __future__ import annotations
import csv, datetime as dt, html, json
from pathlib import Path
HERE=Path(__file__).resolve().parent; RESULTS=HERE/'annual_results'; OUT=HERE/'figures'
W,H=1600,900; L,R=110,1545; T0,T1=165,505; S0,S1=645,790
START=dt.date(2007,1,1); END=dt.date(2027,1,1)
def esc(x): return html.escape(str(x),quote=True)
def xp(d): return L+(d-START).days/(END-START).days*(R-L)
def yt(v): return T1-v/20*(T1-T0)
def ys(v): return S1-v/75000*(S1-S0)
def line(rows,key,y): return 'M '+' L '.join(f'{xp(r["date"]):.1f},{y(r[key]):.1f}' for r in rows)
protocol=json.loads((HERE/'protocol-annual-1.1.0.json').read_text()); manifest=json.loads((RESULTS/'snapshot-manifest.json').read_text())
times={x['commit']:x['committer_unix'] for x in manifest['history']}; summary={x['label']:x for x in csv.DictReader((RESULTS/'pilot-summary.csv').open())}
rows=[]
for sample in protocol['snapshots']:
 r=summary[sample['label']]; rows.append({'label':sample['label'],'year':int(sample['label'][-4:]) if '-' in sample['label'] else int(sample['label']), 'commit':sample['commit'], 'date':dt.datetime.fromtimestamp(times[sample['commit']],dt.timezone.utc).date(), 'framework':r['framework'], 'god':100*float(r['god_class_rate']), 'long':100*float(r['long_method_rate']), 'obsolete':100*float(r['obsolete_affected_files_rate']), 'ploc':int(r['physical_lines'])})
rows.sort(key=lambda r:r['date']); OUT.mkdir(exist_ok=True)
with (OUT/'annual_figure_data.csv').open('w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=['label','year','commit','date','framework','god','long','obsolete','ploc']);w.writeheader()
 for r in rows:w.writerow({**r,'date':r['date'].isoformat()})
series=[('god','God Class / class declarations','#0072B2','', 'circle'),('long','Long Method / method declarations','#D55E00','10 5','square'),('obsolete','Files with obsolete API use / production files','#009E73','3 4','triangle')]
p=[f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">
<title id="title">Annual anti-pattern prevalence and production code size in Json.NET</title><desc id="desc">Twenty independently reproduced observations from 2007 through 2026, showing three normalized anti-pattern measures, target-framework periods, and physical lines of production code.</desc><rect width="100%" height="100%" fill="white"/><style>text{{font-family:"DejaVu Sans",Arial,sans-serif;fill:#202124}}.axis{{stroke:#343a40;stroke-width:1.2}}.grid{{stroke:#d9dee3;stroke-width:1}}.vgrid{{stroke:#eef1f3;stroke-width:1}}.note{{fill:#59636e}}</style>
<text x="{L}" y="42" font-size="27" font-weight="700">Annual anti-pattern prevalence and production code size in Json.NET</text>
<text x="{L}" y="72" font-size="15" class="note">Creation (2007), year-end observations (2008–2025), and frozen partial-year endpoint (2026)</text>
<text x="{L}" y="137" font-size="18" font-weight="700">Normalized anti-pattern prevalence</text><text transform="translate(32 410) rotate(-90)" font-size="14">Flagged units (%)</text>''']
# Legend
lx=L
for key,label,color,dash,shape in series:
 da=f' stroke-dasharray="{dash}"' if dash else ''
 p += [f'<line x1="{lx}" y1="103" x2="{lx+34}" y2="103" stroke="{color}" stroke-width="3"{da}/>',f'<text x="{lx+43}" y="108" font-size="14">{esc(label)}</text>']; lx += {'god':315,'long':365,'obsolete':0}[key]
# Shared yearly vertical grid
for r in rows:p.append(f'<line class="vgrid" x1="{xp(r["date"]):.1f}" y1="{T0}" x2="{xp(r["date"]):.1f}" y2="{S1}"/>')
for v in range(0,21,5):
 y=yt(v);p += [f'<line class="grid" x1="{L}" y1="{y:.1f}" x2="{R}" y2="{y:.1f}"/>',f'<text x="{L-13}" y="{y+5:.1f}" text-anchor="end" font-size="13">{v}</text>']
p += [f'<line class="axis" x1="{L}" y1="{T0}" x2="{L}" y2="{T1}"/>',f'<line class="axis" x1="{L}" y1="{T1}" x2="{R}" y2="{T1}"/>']
for key,label,color,dash,shape in series:
 da=f' stroke-dasharray="{dash}"' if dash else '';p.append(f'<path d="{line(rows,key,yt)}" fill="none" stroke="{color}" stroke-width="3" stroke-linejoin="round"{da}/>')
 for r in rows:
  x,y=xp(r['date']),yt(r[key])
  if shape=='circle':p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="white" stroke="{color}" stroke-width="2.5"/>')
  elif shape=='square':p.append(f'<rect x="{x-4:.1f}" y="{y-4:.1f}" width="8" height="8" fill="white" stroke="{color}" stroke-width="2.5"/>')
  else:p.append(f'<path d="M{x:.1f},{y-5:.1f} L{x-5:.1f},{y+4:.1f} L{x+5:.1f},{y+4:.1f} Z" fill="white" stroke="{color}" stroke-width="2.5"/>')
# Framework strip: boundaries halfway between adjacent dated observations.
p.append(f'<text x="{L}" y="536" font-size="13" font-weight="700">Selected target framework</text>')
groups=[]
for r in rows:
 if not groups or groups[-1][0]!=r['framework']:groups.append([r['framework'],r,r])
 else:groups[-1][2]=r
palette=['#dbeafe','#e0f2fe','#dcfce7','#fef3c7','#ffedd5','#f3e8ff','#fce7f3']
for i,(framework,first,last) in enumerate(groups):
 start=L if first is rows[0] else (xp(rows[rows.index(first)-1]['date'])+xp(first['date']))/2
 end=R if last is rows[-1] else (xp(last['date'])+xp(rows[rows.index(last)+1]['date']))/2
 p += [f'<rect x="{start:.1f}" y="545" width="{end-start:.1f}" height="30" fill="{palette[i%len(palette)]}" stroke="white"/>',f'<text x="{(start+end)/2:.1f}" y="565" text-anchor="middle" font-size="12">{esc(framework)}</text>']
# Size panel
p += [f'<text x="{L}" y="619" font-size="18" font-weight="700">Production code size</text>',f'<text transform="translate(32 775) rotate(-90)" font-size="14">Physical lines</text>']
for v in (0,25000,50000,75000):
 y=ys(v);p += [f'<line class="grid" x1="{L}" y1="{y:.1f}" x2="{R}" y2="{y:.1f}"/>',f'<text x="{L-13}" y="{y+5:.1f}" text-anchor="end" font-size="13">{v//1000}k</text>']
p += [f'<line class="axis" x1="{L}" y1="{S0}" x2="{L}" y2="{S1}"/>',f'<line class="axis" x1="{L}" y1="{S1}" x2="{R}" y2="{S1}"/>',f'<path d="{line(rows,"ploc",ys)}" fill="none" stroke="#6C4AB6" stroke-width="3"/>']
for r in rows:
 x,y=xp(r['date']),ys(r['ploc']);p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="white" stroke="#6C4AB6" stroke-width="2.5"/>')
 p += [f'<line class="axis" x1="{x:.1f}" y1="{S1}" x2="{x:.1f}" y2="{S1+5}"/>',f'<text x="{x:.1f}" y="816" text-anchor="middle" font-size="11">{r["year"]}</text>']
p += [f'<text x="{L}" y="850" font-size="12" class="note">Points use actual Git committer dates; year labels identify the sampling interval.</text>',f'<text x="{R}" y="850" text-anchor="end" font-size="12" class="note">PLOC includes blank and comment lines; production scope follows protocol 1.1.0.</text>','</svg>']
(OUT/'jsonnet_annual_timeline.svg').write_text('\n'.join(p)+'\n',encoding='utf-8');print(OUT/'jsonnet_annual_timeline.svg')
