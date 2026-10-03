"""Publication figure for exploratory documented-fix-labelled comparisons."""
import argparse,csv,sys
from pathlib import Path
BASE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--packages',type=Path,required=True);p.add_argument('--results',type=Path,default=BASE/'results/v1.0');a=p.parse_args()
sys.path.insert(0,str(a.packages.resolve()))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
with (a.results/'models.csv').open() as f:models={(r['repository'],r['rule']):r for r in csv.DictReader(f)}
repos=[('odoo__odoo','Odoo'),('jenkinsci__jenkins','Jenkins'),('apache__tomcat','Apache Tomcat')]
rules=[('LongMethod','Long Method',(-4,8)),('GodClass','God Class',(-4,8)),('ObsoleteApiUsage','Source-declared obsolete API',(-23,25))]
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'pdf.fonttype':42})
fig,axes=plt.subplots(1,3,figsize=(11.4,3.4),layout='constrained')
for ax,(rule,title,limits) in zip(axes,rules):
 ax.axvline(0,color='#777777',linestyle='--',linewidth=.8)
 for i,(repo,label) in enumerate(repos):
  r=models[(repo,rule)]
  if r['status']=='fitted' and r['ci_low_pp'] and r['ci_high_pp']:
   value=float(r['difference_pp']);lo=float(r['ci_low_pp']);hi=float(r['ci_high_pp'])
   ax.errorbar(value,i,xerr=[[value-lo],[hi-value]],fmt='o',color='#245B78',markersize=5,capsize=3,lw=1.3)
  else:ax.text(.98,i,'Too sparse',ha='right',va='center',transform=ax.get_yaxis_transform(),fontsize=8,color='#666666')
 ax.set_title(title);ax.set_xlim(*limits);ax.set_ylim(2.55,-.55);ax.set_yticks(range(3),[label for _,label in repos]);ax.grid(axis='x',alpha=.2)
 ax.spines[['top','right']].set_visible(False)
fig.supxlabel('Adjusted difference in probability of a fix-labelled file edit (percentage points)')
fig.savefig(a.results/'adjusted-documented-fix-probability.pdf',metadata={'Title':'Exploratory fix-labelled edit associations','CreationDate':None,'ModDate':None})
fig.savefig(a.results/'adjusted-documented-fix-probability.png',dpi=180)
plt.close(fig)
