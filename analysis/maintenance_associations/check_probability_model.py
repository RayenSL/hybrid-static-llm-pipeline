"""Diagnostic logistic sensitivity, added after observing LPM range violations."""
import os
for name in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[name]='1'
import argparse,json,sys
from pathlib import Path
BASE=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--packages',type=Path,required=True);ap.add_argument('--results',type=Path,default=BASE/'results/final-automated-analysis-v0.7');a=ap.parse_args();sys.path.insert(0,str(a.packages.resolve()))
import numpy as np,pandas as pd,patsy,statsmodels.api as sm
from scipy import stats
from scipy.special import expit
from statsmodels.stats.sandwich_covariance import cov_cluster_2groups
from statsmodels.stats.multitest import multipletests
OUT=a.results
if (OUT/'logistic-sensitivity.json').exists():raise FileExistsError('Preserve previous diagnostic results')
f=pd.read_csv(OUT/'analysis-input.csv.gz',dtype={'snapshot':str},float_precision='round_trip');models=json.loads((OUT/'models.json').read_text());results=[]
for main in models:
 if main['endpoint']!='binary' or main['status']!='fitted':continue
 rid=main['repository'];rule=main['rule'];df=f[f.rid==rid].copy();eligible=df.named_definitions>0 if rule=='LongMethod' else df.classes>0 if rule=='GodClass' else df.resolved_api_pairs>0
 df=df[eligible&df[rule+'_findings'].notna()].copy();df['flag']=(df[rule+'_findings']>0).astype(int);pieces=[]
 for year,g in df.groupby('snapshot'):
  if g.flag.nunique()!=2:continue
  mask=np.ones(len(g),dtype=bool)
  for cov in ['file_ploc','prior365_raw_changes']:
   bounds=g.groupby('flag')[cov].agg(['min','max']);mask&=g[cov].between(bounds['min'].max(),bounds['max'].min()).to_numpy()
  h=g[mask]
  if h.flag.nunique()==2:pieces.append(h)
 df=pd.concat(pieces);assert len(df)==main['n']
 terms=['flag','C(snapshot)']
 for name in ['logsize','logprior']:
  if df[name].nunique()>=5:
   knot=float((df[name].min()+df[name].max())/2);terms.append(f'bs({name}, knots=({knot!r},), degree=3, include_intercept=False)')
  elif df[name].nunique()>1:terms.append(name)
 X=patsy.dmatrix('1+'+'+'.join(terms),df,return_type='dataframe');i=list(X.columns).index('flag');y=(df.following365_raw_changes.to_numpy()>0).astype(float)
 lpm=sm.OLS(y,X).fit();assert np.isclose(float(lpm.params.iloc[i])*100,main['effect'],rtol=1e-9,atol=1e-9)
 record={'repository':rid,'rule':rule,'n':len(df),'lpm_coefficient_reproduced':True,'lpm_prediction_min':float(lpm.fittedvalues.min()),'lpm_prediction_max':float(lpm.fittedvalues.max()),'status':'not_fitted'}
 try:
  model=sm.GLM(y,X,family=sm.families.Binomial()).fit(maxiter=200)
  if not model.converged:record['reason']='not_converged'
  else:
   covariance,_,_=cov_cluster_2groups(model,df.lineage.to_numpy(),pd.factorize(df.snapshot)[0],use_correction=True)
   x1=X.to_numpy().copy();x0=x1.copy();x1[:,i]=1;x0[:,i]=0;p1=expit(x1@model.params.to_numpy());p0=expit(x0@model.params.to_numpy());effect=float(np.mean(p1-p0));gradient=np.mean(p1[:,None]*(1-p1[:,None])*x1-p0[:,None]*(1-p0[:,None])*x0,axis=0);variance=float(gradient@covariance@gradient);dof=min(df.lineage.nunique(),df.snapshot.nunique())-1
   record.update(status='fitted',effect=effect*100,reference_df=int(dof),model='binomial logit; standardised probability difference',ci_low=None,ci_high=None,p_value=None)
   if variance>0 and np.isfinite(variance):
    se=np.sqrt(variance);critical=stats.t.ppf(.975,dof);record.update(ci_low=float((effect-critical*se)*100),ci_high=float((effect+critical*se)*100),p_value=float(2*stats.t.sf(abs(effect/se),dof)))
   else:record['interval_status']='unavailable_nonpositive_cluster_variance'
 except (ValueError,np.linalg.LinAlgError) as error:record['reason']=str(error)
 results.append(record);print(rid,rule,record.get('effect'),record.get('ci_low'),record.get('ci_high'),flush=True)
valid=[r for r in results if r.get('p_value') is not None]
if valid:
 for r,p in zip(valid,multipletests([r['p_value'] for r in valid],method='holm')[1]):r['holm_p_value']=float(p)
(OUT/'logistic-sensitivity.json').write_text(json.dumps(results,indent=2,allow_nan=False)+'\n');pd.DataFrame(results).to_csv(OUT/'logistic-sensitivity.csv',index=False)
