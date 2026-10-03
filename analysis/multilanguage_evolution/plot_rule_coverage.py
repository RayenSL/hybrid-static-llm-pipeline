"""Plot rule availability; never turn diagnostic counts into prevalence curves."""
import argparse,csv,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--packages',type=Path);ap.add_argument('--csv',type=Path,default=HERE/'results/three-rule-annual-coverage.csv');a=ap.parse_args()
    if a.packages:sys.path.insert(0,str(a.packages.resolve()))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch
    import numpy as np
    rows=list(csv.DictReader(a.csv.open()));projects=['Odoo','Jenkins','Apache Tomcat'];rules=['LongMethod','GodClass','ObsoleteApiUsage'];names={'LongMethod':'Long Method','GodClass':'God Class','ObsoleteApiUsage':'Obsolete API Usage'};years=list(range(2006,2027));values={'complete':0,'partial':1,'unavailable':2};matrix=[];labels=[]
    if len(rows)!=189:raise ValueError('Expected all 189 scheduled rule observations')
    for project in projects:
        for rule in rules:
            cells=[next(r for r in rows if r['repository']==project and r['rule']==rule and int(r['year'])==year) for year in years]
            matrix.append([values[r['status']] for r in cells]);labels.append(project+' — '+names[rule])
    colours=['#0072B2','#E6AB02','#BBBBBB'];plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'svg.hashsalt':'three-rule-coverage-v1','pdf.fonttype':42})
    fig,ax=plt.subplots(figsize=(11.5,4.9),layout='constrained');ax.imshow(np.array(matrix),cmap=ListedColormap(colours),vmin=0,vmax=2,aspect='auto',interpolation='nearest')
    ax.set_yticks(range(9),labels);ax.set_xticks(range(21),[str(y) for y in years],rotation=45,ha='right');ax.set_xlabel('Snapshot year (2006: earliest source; 2026: fixed September endpoint)')
    ax.set_xticks(np.arange(-.5,21,1),minor=True);ax.set_yticks(np.arange(-.5,9,1),minor=True);ax.grid(which='minor',color='white',linewidth=1);ax.tick_params(which='minor',bottom=False,left=False)
    for y in [2.5,5.5]:ax.axhline(y,color='white',linewidth=4)
    ax.set_title('Annual detector coverage across the three selected codebases',loc='left',pad=12)
    fig.legend(handles=[Patch(facecolor=c,label=l) for c,l in zip(colours,['Complete measurement','Partial coverage','Unavailable'])],loc='outside lower center',ncol=3,frameon=False)
    fig.suptitle('Experimental measurements; scientific admission remains pending',fontsize=9,color='#555555')
    dest=HERE/'figures';dest.mkdir(exist_ok=True)
    for ext in ['svg','pdf','png']:
        metadata={'CreationDate':None,'ModDate':None} if ext=='pdf' else {'Date':None} if ext=='svg' else None
        fig.savefig(dest/f'three_rule_annual_coverage.{ext}',dpi=160,metadata=metadata)
