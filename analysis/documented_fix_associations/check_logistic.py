"""Post-fit bounded-probability diagnostic for the documented-fix analysis."""
import os
for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[name]='1'
import argparse,csv,gzip,hashlib,json,sys,warnings
from pathlib import Path
BASE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--packages',type=Path,required=True);p.add_argument('--results',type=Path,default=BASE/'results/v1.0');a=p.parse_args()
sys.path.insert(0,str(a.packages.resolve()))
import numpy as np,pandas as pd,patsy,statsmodels.api as sm
from scipy import stats
from statsmodels.stats.sandwich_covariance import cov_cluster_2groups
f=pd.read_csv(a.results/'analysis-input.csv.gz',compression='gzip',dtype={'snapshot':str})
f['logsize']=np.log1p(f.file_ploc);f['logprior']=np.log1p(f.prior365_raw_changes)
results=[]
for repo in ('odoo__odoo','jenkinsci__jenkins','apache__tomcat'):
 for rule in ('LongMethod','GodClass','ObsoleteApiUsage'):
  g=f[f.rid==repo].copy();complete=g[rule+'_findings'].notna();eligible=g.named_definitions>0 if rule=='LongMethod' else g.classes>0 if rule=='GodClass' else g.resolved_api_pairs>0
  g=g[complete&eligible].copy();g['flag']=(g[rule+'_findings']>0).astype(int);keep=[]
  for year,h in g.groupby('snapshot'):
   if h.flag.nunique()!=2:continue
   mask=np.ones(len(h),dtype=bool)
   for cov in ('file_ploc','prior365_raw_changes'):
    ranges=h.groupby('flag')[cov].agg(['min','max']);mask &= h[cov].between(ranges['min'].max(),ranges['max'].min()).to_numpy()
   h=h[mask]
   if h.flag.nunique()==2:keep.append(h)
  g=pd.concat(keep) if keep else g.iloc[:0].copy()
  modelrow={'repository':repo,'rule':rule,'n':len(g),'flagged_rows':int(g.flag.sum()),'status':'not_fitted'}
  if len(g)==0 or g.snapshot.nunique()<2 or any(g[g.flag==x].lineage.nunique()<20 or (g[g.flag==x].documented_fix_events>0).sum()<10 or (g[g.flag==x].documented_fix_events==0).sum()<10 for x in (0,1)):
   modelrow['reason']='same_feasibility_gate_as_primary';results.append(modelrow);continue
  terms=['flag','C(snapshot)']
  for cov in ('logsize','logprior'):
   if g[cov].nunique()>=5:
    knot=float((g[cov].min()+g[cov].max())/2);terms.append(f'bs({cov}, knots=({knot!r},), degree=3, include_intercept=False)')
   elif g[cov].nunique()>1:terms.append(cov)
  X=patsy.dmatrix('1+'+'+'.join(terms),g,return_type='dataframe')
  y=(g.documented_fix_events>0).astype(float)
  with warnings.catch_warnings():
   warnings.simplefilter('ignore')
   try:m=sm.GLM(y,X,family=sm.families.Binomial()).fit(maxiter=200)
   except Exception as e:modelrow['reason']=type(e).__name__+': '+str(e);results.append(modelrow);continue
  if not m.converged:modelrow['reason']='not_converged';results.append(modelrow);continue
  X1=X.copy();X0=X.copy();X1['flag']=1;X0['flag']=0
  p1=np.asarray(m.predict(X1));p0=np.asarray(m.predict(X0));effect=float((p1-p0).mean())
  modelrow.update(status='fitted',difference_pp=effect*100,average_p1=float(p1.mean()),average_p0=float(p0.mean()))
  try:
   cov,_,_=cov_cluster_2groups(m,g.lineage.to_numpy(),pd.factorize(g.snapshot)[0],use_correction=True)
   gradient=np.mean(p1[:,None]*(1-p1[:,None])*X1.to_numpy()-p0[:,None]*(1-p0[:,None])*X0.to_numpy(),axis=0)
   var=float(gradient@cov@gradient);degrees=min(g.lineage.nunique(),g.snapshot.nunique())-1
   if np.isfinite(var) and var>0:
    margin=stats.t.ppf(.975,degrees)*var**.5
    modelrow.update(ci_low_pp=(effect-margin)*100,ci_high_pp=(effect+margin)*100,interval_status='available')
   else:modelrow['interval_status']='nonfinite_or_nonpositive_variance'
  except Exception as e:modelrow['interval_status']=type(e).__name__+': '+str(e)
  results.append(modelrow)
  print(repo,rule,modelrow['status'],modelrow.get('difference_pp'),modelrow.get('interval_status'),flush=True)
output=a.results/'logistic-sensitivity.csv'
if output.exists():raise SystemExit('Refusing overwrite')
fields=sorted(set().union(*(set(r) for r in results)))
with output.open('w',newline='') as file:
 writer=csv.DictWriter(file,fieldnames=fields,lineterminator='\n');writer.writeheader();writer.writerows(results)
(a.results/'logistic-sensitivity.json').write_text(json.dumps(results,sort_keys=True,indent=2,allow_nan=False)+'\n')
