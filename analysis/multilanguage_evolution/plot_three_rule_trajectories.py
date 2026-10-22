"""Plot complete annual counts, prevalence denominators, and production-source size."""
import argparse,csv,math,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
PROJECTS=('Odoo','Jenkins','Apache Tomcat')
RULES=('LongMethod','GodClass','ObsoleteApiUsage')
RULE_NAMES={'LongMethod':'Long Method','GodClass':'God Class','ObsoleteApiUsage':'Source-declared obsolete API usage'}
COLOURS={'LongMethod':'#0072B2','GodClass':'#D55E00','ObsoleteApiUsage':'#009E73'}

def number(row,key):
    value=row[key]
    return float(value) if value not in {'',None} else math.nan

def series(rows,project,rule,key):
    selected=sorted((r for r in rows if r['repository']==project and r['rule']==rule),key=lambda r:int(r['year']))
    return [int(r['year']) for r in selected],[number(r,key) if r['status']=='complete' else math.nan for r in selected]

def missing_bands(ax,rows,project,rule):
    for row in rows:
        if row['repository']==project and row['rule']==rule and row['status']!='complete':
            year=int(row['year']);ax.axvspan(year-.42,year+.42,color='#D0D0D0',alpha=.7,linewidth=0)

def save(fig,dest,stem):
    for ext in ('pdf','svg','png'):
        metadata={'CreationDate':None,'ModDate':None} if ext=='pdf' else {'Date':None} if ext=='svg' else None
        fig.savefig(dest/f'{stem}.{ext}',dpi=180,metadata=metadata)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--packages',type=Path);ap.add_argument('--csv',type=Path,default=HERE/'results/three-rule-annual-coverage.csv');ap.add_argument('--out',type=Path,default=HERE/'figures');args=ap.parse_args()
    if args.packages:sys.path.insert(0,str(args.packages.resolve()))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    rows=list(csv.DictReader(args.csv.open()))
    if len(rows)!=189:raise ValueError('Expected all 189 scheduled rule observations')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8.5,'pdf.fonttype':42,'svg.hashsalt':'three-rule-trajectories-v1'})
    years=list(range(2006,2027));dest=args.out;dest.mkdir(parents=True,exist_ok=True)

    fig,axes=plt.subplots(4,3,figsize=(11.7,9.0),sharex=True,layout='constrained')
    for column,project in enumerate(PROJECTS):
        axes[0,column].set_title(project,fontweight='bold')
        for row_index,rule in enumerate(RULES):
            ax=axes[row_index,column];x,y=series(rows,project,rule,'primary_count')
            missing_bands(ax,rows,project,rule);ax.plot(x,y,color=COLOURS[rule],marker='o',markersize=2.7,linewidth=1.25)
            ax.grid(axis='y',color='#E5E5E5',linewidth=.6);ax.set_xlim(2005.6,2026.4);ax.set_ylim(bottom=0)
            if column==0:ax.set_ylabel(RULE_NAMES[rule]+'\nfindings')
        size_rows=sorted((r for r in rows if r['repository']==project and r['rule']=='GodClass'),key=lambda r:int(r['year']))
        x=[int(r['year']) for r in size_rows];y=[number(r,'physical_lines')/1000 for r in size_rows]
        ax=axes[3,column];ax.plot(x,y,color='#4D4D4D',marker='o',markersize=2.7,linewidth=1.25);ax.fill_between(x,y,color='#BDBDBD',alpha=.25)
        ax.grid(axis='y',color='#E5E5E5',linewidth=.6);ax.set_ylim(bottom=0);ax.set_xticks(years[::2]);ax.tick_params(axis='x',rotation=45)
        if column==0:ax.set_ylabel('Production-source size\n(thousand PLOC)')
    fig.suptitle('Annual anti-pattern findings and analysed codebase size',fontsize=12)
    fig.supxlabel('Snapshot year (2006: earliest preserved source; 2026: fixed September endpoint)\nGrey bands are missing observations; lines are not interpolated. Experimental measurements; scientific admission remains pending.',fontsize=8)
    save(fig,dest,'three_rule_annual_counts')

    fig,axes=plt.subplots(3,3,figsize=(11.7,7.0),sharex=True,layout='constrained')
    for column,project in enumerate(PROJECTS):
        axes[0,column].set_title(project,fontweight='bold')
        for row_index,rule in enumerate(RULES):
            ax=axes[row_index,column];selected=sorted((r for r in rows if r['repository']==project and r['rule']==rule),key=lambda r:int(r['year']))
            x=[int(r['year']) for r in selected];y=[]
            for r in selected:
                findings=number(r,'primary_count');eligible=number(r,'eligible_count')
                y.append(100*findings/eligible if r['status']=='complete' and eligible>0 else math.nan)
            missing_bands(ax,rows,project,rule);ax.plot(x,y,color=COLOURS[rule],marker='o',markersize=2.7,linewidth=1.25)
            ax.grid(axis='y',color='#E5E5E5',linewidth=.6);ax.set_xlim(2005.6,2026.4);ax.set_ylim(bottom=0);ax.set_xticks(years[::2]);ax.tick_params(axis='x',rotation=45)
            if column==0:ax.set_ylabel(RULE_NAMES[rule]+'\nprevalence (%)')
    fig.suptitle('Annual anti-pattern prevalence within rule-specific populations',fontsize=12)
    fig.supxlabel('Snapshot year (2006: earliest preserved source; 2026: fixed September endpoint)\nDenominators: named definitions, classes, and resolved source file/API pairs. Zero-denominator points are omitted.',fontsize=8)
    save(fig,dest,'three_rule_annual_prevalence')
if __name__=='__main__':main()
