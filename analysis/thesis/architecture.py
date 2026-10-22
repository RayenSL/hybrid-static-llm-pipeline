#!/usr/bin/env python3
"""Render the thesis overview as editable SVG, vector PDF, and a PNG preview.

Requires reportlab and pypdfium2. Uses the current attached thesis, especially
sections 1.3, 4.1–4.6 and 5.1. This is an overview of the controlled study flow;
the separate industrial evidence is identified in the bottom strip and caption.
"""
from pathlib import Path
import os

from reportlab.graphics.shapes import Drawing, Group, Rect, String, Line, Polygon, PolyLine
from reportlab.graphics import renderPDF, renderSVG
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import argparse
import pypdfium2 as pdfium


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
OUT = args.out
OUT.mkdir(parents=True, exist_ok=True)
W, H = 1600, 1550
INK = '#183342'
MUTED = '#536873'
EDGE = '#BAC9CE'
ARROW = '#657B86'
BLUE = '#286A8C'
TEAL = '#14786E'
PURPLE = '#735895'
WHITE = '#FFFFFF'
font_dir = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
if (font_dir / 'arial.ttf').exists():
    pdfmetrics.registerFont(TTFont('OverviewSans', str(font_dir / 'arial.ttf')))
    pdfmetrics.registerFont(TTFont('OverviewBold', str(font_dir / 'arialbd.ttf')))
else:
    font_dir = Path('/usr/share/fonts/truetype/dejavu')
    pdfmetrics.registerFont(TTFont('OverviewSans', str(font_dir / 'DejaVuSans.ttf')))
    pdfmetrics.registerFont(TTFont('OverviewBold', str(font_dir / 'DejaVuSans-Bold.ttf')))

d = Drawing(W, H)


def box(x, y, w, h, fill=WHITE, stroke=EDGE, radius=14, width=1.5):
    d.add(Rect(x, H-y-h, w, h, rx=radius, ry=radius,
               fillColor=HexColor(fill), strokeColor=HexColor(stroke), strokeWidth=width))


def label(x, y, value, size=23, color=INK, bold=False, anchor='start', max_width=None):
    font = 'OverviewBold' if bold else 'OverviewSans'
    measured = pdfmetrics.stringWidth(value, font, size)
    if max_width is not None and measured > max_width:
        raise ValueError(f'Text overflows ({measured:.1f} > {max_width}): {value}')
    d.add(String(x, H-y, value, fontName=font, fontSize=size,
                 fillColor=HexColor(color), textAnchor=anchor))


def route(points, color=ARROW, width=2.4, arrow=True, dashed=False):
    coords = [v for x, y in points for v in (x, H-y)]
    d.add(PolyLine(coords, strokeColor=HexColor(color), strokeWidth=width,
                   fillColor=None, strokeDashArray=[7, 6] if dashed else None,
                   strokeLineJoin=1))
    if arrow:
        x, y = points[-1]
        px, py = points[-2]
        dx, dy = x-px, y-py
        length = (dx*dx+dy*dy)**0.5
        ux, uy = dx/length, dy/length
        pts = [(x,y), (x-11*ux+4.6*uy,y-11*uy-4.6*ux),
               (x-11*ux-4.6*uy,y-11*uy+4.6*ux)]
        d.add(Polygon([v for xx, yy in pts for v in (xx,H-yy)],
                      fillColor=HexColor(color), strokeColor=None))


def badge(x, y, value, color):
    box(x,y,66,34,fill=color,stroke=color,radius=7)
    label(x+33,y+24,value,19,WHITE,True,'middle')


def pill(x,y,w,value,fill='#F1F5F6',color=INK,size=21):
    box(x,y,w,42,fill=fill,stroke=fill,radius=9)
    label(x+w/2,y+28,value,size,color,False,'middle',w-18)


# White background keeps the exported PDF and SVG identical to the preview.
box(0,0,W,H,WHITE,WHITE,0,0)
label(60,58,'HybridLens: from anti-pattern repair to maintenance',36,bold=True)
label(60,94,'Experimental conditions and model assignments',24,MUTED)
route([(1040,88),(1090,88)])
label(1108,95,'State flow',20,MUTED)
route([(1260,88),(1310,88)],BLUE,1.8,False,True)
label(1328,95,'Shared study scope',20,MUTED,max_width=212)

# RQ1 precedes RQ2 in the reading order. Both annotate shared repair studies.
label(60,151,'INITIAL REPAIR STUDIES',19,BLUE,True)
label(1540,151,'Shared experiments · RQ1 followed by RQ2',21,MUTED,anchor='end')
root = d

# Keep panel-local geometry while placing the effectiveness panel first.
d = Group()
box(1220,133,320,310,'#EFF5F9','#C7DBE7',12)
badge(1240,151,'RQ1',BLUE)
label(1320,176,'Effectiveness',26,BLUE,True,max_width=202)
label(1240,216,'Strict success: all three',22,BLUE,True,max_width=280)
for j, value in enumerate(['Build passes','Target resolved','Private oracle passes']):
    y = 232+43*j
    box(1240,y,280,34,'#DDEFE9','#C1DCD1',7,0.8)
    label(1380,y+24,value,22,TEAL,False,'middle',256)
label(1240,376,'Plus wider quality outcomes',21,max_width=280)
label(1240,406,'Context: build + resolution;',20,MUTED,max_width=280)
label(1240,431,'behaviour reported separately.',20,MUTED,max_width=280)
d.translate(-1160,-40)
root.add(d)

# Conditions follow effectiveness, with the detailed experimental grid intact.
d = Group()
box(60,133,1110,310,'#EFF5F9','#C7DBE7',12)
badge(84,151,'RQ2',BLUE)
label(166,176,'Conditions affecting repair',28,BLUE,True,max_width=620)
label(1146,176,'gpt-5.6-sol',23,BLUE,True,'end')
label(84,216,'2 × 2 × 2 factorial: 8 arms',24,BLUE,True,max_width=535)
label(84,247,'Grounding / repair control',20,MUTED,max_width=310)
label(506,247,'Visible tests',20,MUTED,anchor='middle')
factorial_rows = [
    'Ungrounded · single-shot',
    'Grounded · single-shot',
    'Ungrounded · iterative',
    'Grounded · iterative',
]
for j, name in enumerate(factorial_rows):
    y = 260 + 39*j
    label(84,y+24,name,23,max_width=340)
    for x, value in ((434,'OFF'),(521,'ON')):
        box(x,y,75,32,'#DCEAF3','#C4D9E8',7,0.8)
        label(x+37.5,y+23,value,21,BLUE,True,'middle')
label(84,431,'26 targets × 8 arms × 3 repeats = 624 assignments',21,MUTED,max_width=520)
d.add(Line(627,H-203,627,H-426,strokeColor=HexColor('#C7DBE7'),strokeWidth=1.3))
label(660,216,'Separate context study: 4 levels',24,BLUE,True,max_width=486)
label(660,247,'Nested payloads; Minimal is already grounded',20,MUTED,max_width=486)
levels = [
    ('Minimal','Anti-pattern label + fragment'),
    ('Structural','+ diagnosis and metrics'),
    ('Relational','+ members and source window'),
    ('Full','+ referenced type source'),
]
for j, (name, detail) in enumerate(levels):
    y = 260 + 39*j
    box(660,y,486,32,'#E3EEF5','#CFDFE9',7,0.8)
    label(674,y+23,name,21,BLUE,True,max_width=125)
    label(805,y+23,detail,20,max_width=328)
    if j < 3:
        route([(693,y+32),(693,y+39)],BLUE,1.5,False)
label(660,431,'Single-shot · tests OFF · 36 × 4 × 3 = 432',21,MUTED,max_width=486)
d.translate(370,-40)
root.add(d)
d = root

# A common dashed connector expresses the shared experimental scope. No
# individual RQ is attached to source loading merely because it sits above it.
route([(220,483),(220,515),(1380,515)],BLUE,1.8,False,True)
route([(985,483),(985,515)],BLUE,1.8,False,True)
for x in (735,1040,1380):
    route([(x,515),(x,560)],BLUE,1.8,False,True)

# Leave room for the shared scope connector, shifting the existing flow down.
d = Group()
label(60,477,'SHARED INITIAL REPAIR PIPELINE',19,MUTED,True)

nodes = [
    (60,210,'Original code',['Frozen, buildable','source'], '#F4F6F7'),
    (320,240,'Static analyser',['Target location,','findings and metrics'], '#F0F6F8'),
    (610,250,'Context builder',['Assigned context','and detector evidence'], '#F0F6F8'),
    (910,260,'LLM repair',['gpt-5.6-sol','Single-shot or iterative','Complete-file edits'], '#F0F6F8'),
    (1220,320,'Final evaluation',['Build · detector · behaviour','Study-specific acceptance'], '#EDF7F3'),
]
for x,w,title,lines,fill in nodes:
    box(x,500,w,158,fill)
    label(x+w/2,543,title,27,INK,True,'middle',w-24)
    for j,s in enumerate(lines):
        label(x+w/2,583+j*28,s,22,MUTED,False,'middle',w-20)
for (x,w,*_), (nx,*_) in zip(nodes,nodes[1:]):
    route([(x+w,579),(nx,579)])

# Source and accepted repair meet as a pair; original code is not lost.
route([(165,658),(165,794),(450,794)])
route([(1380,658),(1380,794),(1150,794)],TEAL)
label(185,768,'Retain original',22,MUTED)
label(1265,740,'Select accepted',22,TEAL,anchor='middle',max_width=210)
label(1265,768,'repairs',22,TEAL,anchor='middle',max_width=210)
box(450,718,700,152,'#FAFCFC','#A6C2BE',14)
label(800,757,'SELECTED ORIGINAL–REPAIR PAIRS',20,TEAL,True,'middle')
pill(480,784,270,'Original code','#EDF1F3',size=24)
pill(790,784,330,'Accepted repaired code','#DDF0E9',TEAL,size=24)
label(770,813,'+',27,MUTED,anchor='middle')
label(800,853,'21 corpus pairs · four cumulative maintenance requirements',21,MUTED,anchor='middle',max_width=660)

# Both studies receive matched pairs; no arrow suggests RQ3 runs become RQ4 runs.
route([(800,870),(800,915),(410,915),(410,960)],TEAL)
route([(800,915),(1190,915),(1190,960)],TEAL)
label(60,936,'SUBSEQUENT MAINTENANCE',19,MUTED,True)
label(1540,936,'Fresh runs for each study',21,MUTED,anchor='end')

box(60,960,710,380,'#F0F8F6','#A7CEC4',14)
badge(84,982,'RQ3',TEAL)
label(166,1009,'Durability after repair',28,TEAL,True,max_width=576)
pill(84,1034,252,'gpt-5.6-sol','#DCEEE8',TEAL,size=24)
label(358,1062,'Initial durability study',23,TEAL,max_width=388)
label(84,1103,'Same requirements, supporting context and checks',24,max_width=662)
pill(84,1125,302,'O–N · Original + neutral','#E2EBED',size=22)
label(410,1153,'vs',23,MUTED,anchor='middle')
pill(434,1125,312,'R–N · Repaired + neutral','#DCEEE8',TEAL,size=22)
label(84,1197,'Neutral comparison also repeated in both RQ4 model runs.',21,MUTED,max_width=662)
label(84,1231,'Measure after each accepted step',23,TEAL,True,max_width=662)
label(84,1262,'Newly present findings · recurrence',24,max_width=662)
label(84,1292,'Decision-burden accrual · completion',24,max_width=662)
label(84,1316,'Compare pairs over the common completed steps.',22,MUTED,max_width=662)

box(830,960,710,380,'#F6F3F9','#C8BAD8',14)
badge(854,982,'RQ4',PURPLE)
label(936,1009,'Interventions during maintenance',28,PURPLE,True,max_width=580)
pill(854,1034,280,'gpt-5.6-sol','#EBE5F2',PURPLE,size=24)
pill(1150,1034,366,'Claude Opus 5.5','#EBE5F2',PURPLE,size=24)
label(994,1101,'Initial controlled run',20,MUTED,anchor='middle',max_width=280)
label(1333,1101,'Second-model replication',20,MUTED,anchor='middle',max_width=366)
label(854,1135,'ARM',18,MUTED,True)
label(946,1135,'START',18,MUTED,True)
label(1120,1135,'POLICY — ALL FOUR ARMS PER MODEL',18,MUTED,True,max_width=396)
maintenance_arms = [
    ('O–N','Original','Neutral'),
    ('R–N','Repaired','Neutral'),
    ('R–D','Repaired','Design guidance'),
    ('R–L','Repaired','Conditional analyser feedback'),
]
for j, (arm, start, policy) in enumerate(maintenance_arms):
    y = 1146+35*j
    box(852,y,666,31,'#EEE8F4' if j in (2,3) else '#F6F3F9',
        '#EEE8F4' if j in (2,3) else '#F6F3F9',5,0)
    label(860,y+23,arm,22,PURPLE,True,max_width=76)
    label(946,y+23,start,22,max_width=158)
    label(1120,y+23,policy,22,max_width=396)
label(854,1299,'Compare R–N with R–D and R–L within each model.',21,PURPLE,max_width=662)
label(854,1326,'R–L: a new finding triggers one separate quality call.',21,MUTED,max_width=662)

label(800,1374,'Maintenance advances through accepted steps: build, API, requirement and regression checks.',23,MUTED,anchor='middle')

# Additional studies are named separately so the controlled flow does not imply
# that the industrial introduction-point experiment starts from accepted repairs.
d.add(Line(60,H-1396,1540,H-1396,strokeColor=HexColor('#D8E0E3'),strokeWidth=1.3))
label(60,1427,'INDUSTRIAL EVIDENCE',18,MUTED,True)
label(315,1427,'Repair probes (RQ1–2) · historical replay (RQ3) · introduction-point intervention (RQ4)',21,MUTED,max_width=1225)
label(315,1457,'The industrial RQ4 study starts independently from historical post-commit code.',21,MUTED,max_width=1225)
d.translate(0,-60)
root.add(d)
d = root

pdf = OUT/'hybridlens-overall-architecture.pdf'
svg = OUT/'hybridlens-overall-architecture.svg'
png = OUT/'hybridlens-overall-architecture.png'
renderPDF.drawToFile(d,str(pdf),title='HybridLens: overall architecture and research questions',author='')
renderSVG.drawToFile(d,str(svg))
# Give editable SVG text portable font names instead of PDF-only font aliases.
source = svg.read_text(encoding='utf-8')
source = source.replace('font-family: OverviewBold;', 'font-family: Arial, Helvetica, sans-serif; font-weight: bold;')
source = source.replace('font-family: OverviewSans;', 'font-family: Arial, Helvetica, sans-serif;')
svg.write_text(source,encoding='utf-8')
with pdfium.PdfDocument(str(pdf)) as doc:
    page=doc[0]
    bitmap=page.render(scale=1.5)
    bitmap.to_pil().save(png)
    bitmap.close()
    page.close()
for p in (pdf,svg,png):
    print(p)
