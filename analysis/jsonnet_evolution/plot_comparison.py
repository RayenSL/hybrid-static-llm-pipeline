#!/usr/bin/env python3
"""Create the auditable three-system comparison dataset and SVG figure."""
import csv, html, json
from pathlib import Path

HERE=Path(__file__).resolve().parent; OUT=HERE/'figures'
SYSTEMS=[('Json.NET','annual_results','#0072B2'),('OpenRA','openra_annual_results','#D55E00'),('nopCommerce','nopcommerce_annual_results','#009E73')]
FIELDS=['repository','label','year','commit','status','reproduced','god_class_rate','long_method_rate','obsolete_affected_files_rate','physical_lines','GodClass','LongMethod','ObsoleteApiUsage','obsolete_affected_files']

def load(name,dirname,color):
 root=HERE/dirname; comp=json.loads((root/'comparison.json').read_text()); eq={x['label']:x['equal'] and x['all_complete'] for x in comp['snapshots']}
 rows=[]
 for r in csv.DictReader((root/'pilot-summary.csv').open()):
  year=int(r['label'][-4:]); ok=r['status']=='complete' and eq.get(r['label'],False)
  rows.append({'repository':name,'label':r['label'],'year':year,'commit':r['commit'],'status':r['status'],'reproduced':str(ok),'god_class_rate':r['god_class_rate'] if ok else '', 'long_method_rate':r['long_method_rate'] if ok else '', 'obsolete_affected_files_rate':r['obsolete_affected_files_rate'] if ok else '', 'physical_lines':r['physical_lines'] if ok else '', **{k:r[k] if ok else '' for k in ['GodClass','LongMethod','ObsoleteApiUsage','obsolete_affected_files']},'_ok':ok,'_color':color})
 return rows

rows=[r for args in SYSTEMS for r in load(*args)]; OUT.mkdir(exist_ok=True)
with (OUT/'comparative_figure_data.csv').open('w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows([{k:r[k] for k in FIELDS} for r in rows])

W,H=1600,1030; L,R=115,1540; years=range(2007,2027); panels=[('god_class_rate','God Class prevalence','Flagged classes (%)'),('long_method_rate','Long Method prevalence','Flagged methods (%)'),('obsolete_affected_files_rate','Obsolete API prevalence','Affected files (%)'),('physical_lines','Production code size','Physical lines')]
top=150; ph=176; gap=55
def esc(s):return html.escape(str(s))
def xp(y):return L+(y-2007)/(2026-2007)*(R-L)
valid=[r for r in rows if r['_ok']]
maxima={k:max(float(r[k])*(100 if k!='physical_lines' else 1) for r in valid) for k,_,_ in panels}
maxima['physical_lines']=maxima['physical_lines']*1.08; maxima.update({k:max(v*1.12,1) for k,v in maxima.items()})
p=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><rect width="100%" height="100%" fill="white"/><style>text{{font-family:DejaVu Sans,Arial,sans-serif;fill:#202124}}.grid{{stroke:#e5e7eb}}.axis{{stroke:#374151}}.note{{fill:#5b6470}}</style>',f'<text x="{L}" y="42" font-size="27" font-weight="700">Annual anti-pattern trajectories in three C# systems</text>',f'<text x="{L}" y="72" font-size="15" class="note">Primary production component; only complete, byte-for-byte reproduced observations are connected</text>']
lx=L
for name,_,color in SYSTEMS:p += [f'<line x1="{lx}" y1="108" x2="{lx+38}" y2="108" stroke="{color}" stroke-width="3"/><circle cx="{lx+19}" cy="108" r="4" fill="white" stroke="{color}" stroke-width="2"/><text x="{lx+48}" y="113" font-size="14">{esc(name)}</text>'];lx+=185
for pi,(key,title,ylabel) in enumerate(panels):
 y0=top+pi*(ph+gap); y1=y0+ph; mx=maxima[key]
 p += [f'<text x="{L}" y="{y0-17}" font-size="17" font-weight="700">{title}</text>',f'<text transform="translate(31 {y1}) rotate(-90)" font-size="13">{ylabel}</text>']
 for frac in (0,.5,1):
  y=y1-frac*ph; val=mx*frac; label=f'{val/1000:.0f}k' if key=='physical_lines' and val>=1000 else f'{val:.1f}'
  p += [f'<line class="grid" x1="{L}" y1="{y:.1f}" x2="{R}" y2="{y:.1f}"/>',f'<text x="{L-12}" y="{y+5:.1f}" text-anchor="end" font-size="12">{label}</text>']
 p += [f'<line class="axis" x1="{L}" y1="{y0}" x2="{L}" y2="{y1}"/>',f'<line class="axis" x1="{L}" y1="{y1}" x2="{R}" y2="{y1}"/>']
 for name,_,color in SYSTEMS:
  rr=sorted([r for r in rows if r['repository']==name],key=lambda x:x['year']); seg=[]
  def draw(seg):
   if not seg:return
   pts=' '.join(f'{xp(q["year"]):.1f},{y1-(float(q[key])*(100 if key!="physical_lines" else 1))/mx*ph:.1f}' for q in seg)
   p.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.7" stroke-linejoin="round"/>')
   for q in seg:
    y=y1-(float(q[key])*(100 if key!='physical_lines' else 1))/mx*ph;p.append(f'<circle cx="{xp(q["year"]):.1f}" cy="{y:.1f}" r="3.7" fill="white" stroke="{color}" stroke-width="2"/>')
  prev=None
  for q in rr:
   if not q['_ok'] or (prev is not None and q['year']!=prev+1):draw(seg);seg=[];prev=None
   if q['_ok']:seg.append(q);prev=q['year']
  draw(seg)
 if pi==3:
  for y in years:
   if y%2==1:p.append(f'<text x="{xp(y):.1f}" y="{y1+24}" text-anchor="middle" font-size="11">{y}</text>')
p += [f'<text x="{L}" y="1010" font-size="12" class="note">Gaps denote unavailable, partial, failed, or non-reproduced observations; missing observations are never encoded as zero.</text>','</svg>']
(OUT/'jsonnet_openra_nopcommerce_comparison.svg').write_text('\n'.join(p)+'\n');print(OUT/'jsonnet_openra_nopcommerce_comparison.svg')
