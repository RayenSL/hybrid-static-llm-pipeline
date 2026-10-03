"""Independently reconstruct the two-way score sandwich for the key count results."""
import os
for name in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[name]='1'
import argparse,json,sys
from pathlib import Path
BASE=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--packages',type=Path,required=True);a=ap.parse_args();sys.path.insert(0,str(a.packages.resolve()))
import numpy as np,pandas as pd,patsy,statsmodels.api as sm
OUT=BASE/'results/final-automated-analysis-v0.7';df=pd.read_csv(OUT/'analysis-input.csv.gz',dtype={'snapshot':str},float_precision='round_trip');models=json.loads((OUT/'models.json').read_text());checks=[]
for rid in ['jenkinsci__jenkins','apache__tomcat']:
 f=df[(df.rid==rid)&(df.classes>0)&df.GodClass_findings.notna()].copy();f['flag']=(f.GodClass_findings>0).astype(int);pieces=[]
 for year,g in f.groupby('snapshot'):
  if g.flag.nunique()!=2:continue
  mask=np.ones(len(g),bool)
  for c in ['file_ploc','prior365_raw_changes']:
   b=g.groupby('flag')[c].agg(['min','max']);mask&=g[c].between(b['min'].max(),b['max'].min()).to_numpy()
  if g[mask].flag.nunique()==2:pieces.append(g[mask])
 f=pd.concat(pieces);terms=['flag','C(snapshot)']
 for c in ['logsize','logprior']:
  knot=float((f[c].min()+f[c].max())/2);terms.append(f'bs({c}, knots=({knot!r},), degree=3, include_intercept=False)')
 design=patsy.dmatrix('1+'+'+'.join(terms),f,return_type='dataframe');i=list(design.columns).index('flag');X=design.to_numpy();y=f.following365_raw_changes.to_numpy();m=sm.GLM(y,X,family=sm.families.Poisson()).fit(maxiter=100);mu=m.predict(X)
 scores=X*(y-mu)[:,None];bread=np.linalg.inv(X.T@(mu[:,None]*X));n,k=X.shape
 def meat(groups):
  ids,uniques=pd.factorize(groups);sums=np.zeros((len(uniques),k));np.add.at(sums,ids,scores);G=len(uniques)
  return (G/(G-1))*((n-1)/(n-k))*(sums.T@sums)
 covariance=bread@(meat(f.lineage.to_numpy())+meat(f.snapshot.to_numpy())-meat(pd.MultiIndex.from_arrays([f.lineage,f.snapshot])))@bread
 reference=next(r for r in models if r['repository']==rid and r['rule']=='GodClass' and r['endpoint']=='count')
 assert n==reference['n'];assert np.isclose(float(np.exp(m.params[i])),reference['effect'],rtol=1e-9,atol=1e-9)
 assert np.isclose(covariance[i,i],reference['standard_error']**2,rtol=1e-6,atol=1e-10)
 checks.append({'repository':rid,'rule':'GodClass','comparison_rows':n,'coefficient_reproduced':True,'two_way_covariance_reconstructed_from_cluster_scores':True,'reported_variance':reference['standard_error']**2,'independently_computed_variance':float(covariance[i,i])})
(OUT/'statistical-verification.json').write_text(json.dumps({'checks':checks,'all_passed':True},indent=2)+'\n');print(json.dumps(checks,indent=2))
