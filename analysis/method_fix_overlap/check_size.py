"""Post-fit sensitivity to residual method-size imbalance in matched pairs."""
import argparse,csv,json,math,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--packages',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
sys.path.insert(0,str(a.packages.resolve()))
import numpy as np,statsmodels.api as sm
from scipy import stats
from statsmodels.stats.sandwich_covariance import cov_cluster_2groups
source=Path(__file__).parent/'results/v0.1/pairs.csv'
rows=[r for r in csv.DictReader(source.open()) if r['flagged_unresolved']=='False' and r['control_unresolved']=='False']
def fit(sub,ratio_adjusted=False):
 y=np.array([int(r['flagged_body_edit'])-int(r['control_body_edit']) for r in sub],dtype=float)
 lr=np.array([math.log(int(r['flagged_lines'])/int(r['control_lines'])) for r in sub])
 X=np.column_stack((np.ones(len(sub)),lr)) if ratio_adjusted else np.ones((len(sub),1))
 m=sm.OLS(y,X).fit();lineage=np.array([int(r['lineage']) for r in sub]);years=np.array([int(r['year']) for r in sub]);cov,_,_=cov_cluster_2groups(m,lineage,years,use_correction=True)
 df=min(len(set(lineage)),len(set(years)))-1;b=float(m.params[0]);var=float(cov[0,0]);se=math.sqrt(var) if var>0 else float('nan');crit=stats.t.ppf(.975,df)
 return {'pairs':len(sub),'flagged_body_edits':sum(int(r['flagged_body_edit']) for r in sub),'control_body_edits':sum(int(r['control_body_edit']) for r in sub),
         'estimate_pp':b*100,'ci_low_pp':(b-crit*se)*100,'ci_high_pp':(b+crit*se)*100,'p_value':float(2*stats.t.sf(abs(b/se),df)),
         'median_flagged_lines':float(np.median([int(r['flagged_lines']) for r in sub])),'median_control_lines':float(np.median([int(r['control_lines']) for r in sub]))}
out=[]
for repo in ('jenkinsci__jenkins','apache__tomcat'):
 base=[r for r in rows if r['repository']==repo]
 for cal in (1.1,1.25,1.5,2.0):
  sub=[r for r in base if max(int(r['flagged_lines']),int(r['control_lines']))<=cal*min(int(r['flagged_lines']),int(r['control_lines']))]
  out.append({'repository':repo,'max_size_ratio':cal,'adjustment':'paired_difference',**fit(sub)})
 out.append({'repository':repo,'max_size_ratio':2.0,'adjustment':'log_size_ratio',**fit(base,True)})
a.output.write_text(json.dumps(out,indent=2)+'\n')
for r in out:print(r['repository'],r['max_size_ratio'],r['adjustment'],r['pairs'],round(r['estimate_pp'],3),round(r['ci_low_pp'],3),round(r['ci_high_pp'],3))
