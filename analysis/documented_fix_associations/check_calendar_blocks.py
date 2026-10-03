"""Post-fit leave-one-three-year-block-out diagnostic for Tomcat Long Method."""
import argparse,csv,sys
from pathlib import Path
BASE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--packages',type=Path,required=True);p.add_argument('--results',type=Path,default=BASE/'results/v1.0');a=p.parse_args();sys.path.insert(0,str(a.packages.resolve()))
import numpy as np,pandas as pd,patsy,statsmodels.api as sm
f=pd.read_csv(a.results/'analysis-input.csv.gz',compression='gzip',dtype={'snapshot':str})
f=f[(f.rid=='apache__tomcat')&(f.LongMethod_findings.notna())&(f.named_definitions>0)].copy();f['flag']=(f.LongMethod_findings>0).astype(int)
keep=[]
for year,g in f.groupby('snapshot'):
 if g.flag.nunique()!=2:continue
 mask=np.ones(len(g),dtype=bool)
 for cov in ('file_ploc','prior365_raw_changes'):
  r=g.groupby('flag')[cov].agg(['min','max']);mask &= g[cov].between(r['min'].max(),r['max'].min()).to_numpy()
 h=g[mask]
 if h.flag.nunique()==2:keep.append(h)
f=pd.concat(keep);rows=[]
for start in (2007,2010,2013,2016,2019,2022):
 g=f[~f.snapshot.astype(int).between(start,start+2)].copy();g['logsize']=np.log1p(g.file_ploc);g['logprior']=np.log1p(g.prior365_raw_changes)
 terms=['flag','C(snapshot)']
 for cov in ('logsize','logprior'):
  knot=float((g[cov].min()+g[cov].max())/2);terms.append(f'bs({cov}, knots=({knot!r},), degree=3, include_intercept=False)')
 X=patsy.dmatrix('1+'+'+'.join(terms),g,return_type='dataframe');y=(g.documented_fix_events>0).astype(float)
 m=sm.OLS(y,X).fit();rows.append({'omitted_years':f'{start}-{start+2}','n':len(g),'difference_pp':float(m.params['flag']*100)})
out=a.results/'calendar-block-sensitivity.csv'
if out.exists():raise SystemExit('Refusing overwrite')
with out.open('w',newline='') as fh:
 w=csv.DictWriter(fh,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
for row in rows:print(row)
