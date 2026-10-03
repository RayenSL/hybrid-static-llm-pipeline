"""Final automated file-change associations, under the dated v0.7 specification."""
import os
for name in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[name]='1'
import argparse,collections,csv,gzip,hashlib,json,shutil,sqlite3,sys,tempfile,warnings
from pathlib import Path
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--packages',type=Path,required=True);ap.add_argument('--output',type=Path,default=BASE/'results/final-automated-analysis-v0.7');a=ap.parse_args();sys.path.insert(0,str(a.packages.resolve()))
import numpy as np,pandas as pd,patsy,statsmodels.api as sm
from scipy import stats
from statsmodels.stats.sandwich_covariance import cov_cluster_2groups
from statsmodels.stats.multitest import multipletests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
OUT=a.output
if OUT.exists():raise FileExistsError('Preserve previous results; use a fresh output directory')
OUT.mkdir(parents=True)
RULES=['LongMethod','GodClass','ObsoleteApiUsage'];NAMES={'odoo__odoo':'Odoo','jenkinsci__jenkins':'Jenkins','apache__tomcat':'Tomcat'};DAY=86400
inputs={}
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def seal(p):inputs[str(p.relative_to(ROOT))]=sha(p)
manifest_path=BASE/'results/file-cohorts-v0.2/combined-cohort-manifest.json';seal(manifest_path);manifest=json.loads(manifest_path.read_text())
api_manifest=BASE/'results/api-reference-inventory-v0.6/manifest.json';seal(api_manifest);api_counts={}
for record in json.loads(api_manifest.read_text()):
 p=api_manifest.parent/record['file'];assert sha(p)==record['sha256'];seal(p);d=json.loads(p.read_text());c=collections.Counter(r['path'] for r in d['references'])
 for path,count in c.items():api_counts[(d['repository'],str(d['year']),path)]=count
frames=[]
audit_manifest_path=BASE/'results/window-lineage-audit/manifest.json';seal(audit_manifest_path);audit_manifest={r['repository']:r for r in json.loads(audit_manifest_path.read_text())}
for record in manifest:
 rid=record['repository'];p=BASE/record['csv'];assert sha(p)==record['sha256'];seal(p);f=pd.read_csv(p,dtype={'snapshot':str});f['rid']=rid
 audit_path=BASE/f'results/window-lineage-audit/{rid}.csv.gz';assert sha(audit_path)==audit_manifest[rid]['audit_sha256'];seal(audit_path)
 audit=pd.read_csv(audit_path,dtype={'snapshot':str})
 cols=['snapshot','baseline_path','prior_membership_difference','followup_membership_difference','terminal_deletion_events','outside_path_scope_events','type_change_events']
 f=f.merge(audit[cols],on=['snapshot','baseline_path'],how='left',validate='one_to_one');assert not f['terminal_deletion_events'].isna().any()
 f['resolved_api_pairs']=[api_counts.get((rid,y,path),np.nan) for y,path in zip(f.snapshot,f.baseline_path)]
 # Independent sensitivity: M-status changes only, not pure moves or deletion events.
 dbpath=ROOT/f'tmp/maintenance-associations/file-events/{rid}.sqlite';dbseal=BASE/f'results/file-events/{rid}.json';seal(dbseal)
 with tempfile.TemporaryDirectory(prefix='final-activity-') as tmp:
  local=Path(tmp)/'events.sqlite';shutil.copyfile(dbpath,local);assert sha(local)==json.loads(dbseal.read_text())['database_sha256'];db=sqlite3.connect(local)
  events=list(db.execute('SELECT seq,commit_hash,timestamp FROM events ORDER BY seq'));seqs={h:s for s,h,t in events};times=np.array([0]+[t for s,h,t in events]);cache={};counts=[]
  for r in f.itertuples():
   if r.lineage not in cache:cache[r.lineage]=np.array([x[0] for x in db.execute("SELECT DISTINCT seq FROM changes WHERE lineage=? AND status='M' ORDER BY seq",(int(r.lineage),))],dtype=int)
   h=cache[r.lineage];t=int(r.baseline_timestamp);counts.append(int(np.sum((h>seqs[r.baseline_commit])&(times[h]>t)&(times[h]<=t+365*DAY))))
  f['following365_modifications']=counts;db.close()
 assert (f.following365_modifications<=f.following365_raw_changes).all()
 frames.append(f);print(rid,len(f),'observations loaded and modification-only counts checked',flush=True)
all_data=pd.concat(frames,ignore_index=True);all_data['logsize']=np.log1p(all_data.file_ploc);all_data['logprior']=np.log1p(all_data.prior365_raw_changes)
# Deterministic analysis-input table for replay.
with (OUT/'analysis-input.csv.gz').open('wb') as binary:
 with gzip.GzipFile(filename='',fileobj=binary,mode='wb',mtime=0) as z:z.write(all_data.to_csv(index=False,lineterminator='\n').encode())

def design(f):
 terms=['flag','C(snapshot)']
 for name in ['logsize','logprior']:
  distinct=f[name].nunique()
  if distinct>=5:
   knot=float((f[name].min()+f[name].max())/2);terms.append(f'bs({name}, knots=({knot!r},), degree=3, include_intercept=False)')
  elif distinct>1:terms.append(name)
 return patsy.dmatrix('1+'+'+'.join(terms),f,return_type='dataframe')
def reasons(f,counts):
 why=[]
 if f.snapshot.nunique()<2:why.append('fewer_than_two_comparison_years')
 for flag in [0,1]:
  part=f[f.flag==flag];y=counts[f.flag.to_numpy()==flag]
  if part.lineage.nunique()<20:why.append(f'group_{flag}_fewer_than_20_lineages')
  if sum(y>0)<10 or sum(y==0)<10:why.append(f'group_{flag}_fewer_than_10_events_or_nonevents')
 return why

def fit(f,column,kind,robust=True):
 counts=f[column].to_numpy(float);why=reasons(f,counts)
 result={'n':len(f),'flagged_rows':int(f.flag.sum()),'years':int(f.snapshot.nunique()),'lineages':int(f.lineage.nunique()),'flagged_lineages':int(f.loc[f.flag==1,'lineage'].nunique()),'status':'not_fitted','reason':';'.join(why)}
 if why:return result
 X=design(f);idx=list(X.columns).index('flag');rank=np.linalg.matrix_rank(X.to_numpy());result['design_columns']=len(X.columns);result['design_rank']=int(rank)
 if rank<len(X.columns):result['reason']='rank_deficient_design';return result
 y=(counts>0).astype(float) if kind=='binary' else counts
 try:
  if kind=='binary':model=sm.OLS(y,X).fit()
  else:
   model=sm.GLM(y,X,family=sm.families.Poisson()).fit(maxiter=100)
   if not model.converged:result['reason']='poisson_did_not_converge';return result
  beta=float(model.params.iloc[idx]);result.update(status='fitted',reason='',coefficient=beta,effect=beta*100 if kind=='binary' else float(np.exp(beta)))
  prediction=np.asarray(model.predict(X));result['prediction_outside_unit_interval_fraction']=float(np.mean((prediction<0)|(prediction>1))) if kind=='binary' else None
  if kind=='count':result['pearson_dispersion']=float(np.sum((y-prediction)**2/np.maximum(prediction,1e-12))/(len(y)-rank))
  if robust:
   covariance,_,_=cov_cluster_2groups(model,f.lineage.to_numpy(),pd.factorize(f.snapshot)[0],use_correction=True);variance=float(covariance[idx,idx]);df=min(f.lineage.nunique(),f.snapshot.nunique())-1;result['reference_df']=int(df)
   if not np.isfinite(variance) or variance<=0:result.update(interval_status='unavailable_nonpositive_cluster_variance',p_value=None,ci_low=None,ci_high=None)
   else:
    se=float(np.sqrt(variance));critical=float(stats.t.ppf(.975,df));lo=beta-critical*se;hi=beta+critical*se
    result.update(interval_status='available',standard_error=se,p_value=float(2*stats.t.sf(abs(beta/se),df)),ci_low=lo*100 if kind=='binary' else float(np.exp(lo)),ci_high=hi*100 if kind=='binary' else float(np.exp(hi)))
  return result
 except (ValueError,np.linalg.LinAlgError) as e:result.update(status='not_fitted',reason=type(e).__name__+':'+str(e));return result

models=[];descriptive=[];support=[];sensitivity=[];block_results=[]
for rid in NAMES:
 for rule in RULES:
  f=all_data[all_data.rid==rid].copy();complete=f[rule+'_findings'].notna()
  eligible=f.named_definitions>0 if rule=='LongMethod' else f.classes>0 if rule=='GodClass' else f.resolved_api_pairs>0
  f=f[complete&eligible].copy();f['flag']=(f[rule+'_findings']>0).astype(int)
  for flag,g in f.groupby('flag'):
   descriptive.append({'repository':rid,'rule':rule,'flagged':int(flag),'rows':len(g),'lineages':g.lineage.nunique(),'years':g.snapshot.nunique(),'any_change_fraction':float((g.following365_raw_changes>0).mean()),'mean_changes':float(g.following365_raw_changes.mean()),'median_changes':float(g.following365_raw_changes.median()),'median_ploc':float(g.file_ploc.median()),'median_prior_changes':float(g.prior365_raw_changes.median())})
  keep=[]
  for year,g in f.groupby('snapshot'):
   if g.flag.nunique()!=2:continue
   mask=np.ones(len(g),dtype=bool)
   for covariate in ['file_ploc','prior365_raw_changes']:
    bounds=g.groupby('flag')[covariate].agg(['min','max']);low=bounds['min'].max();high=bounds['max'].min();mask&=g[covariate].between(low,high).to_numpy()
   h=g[mask]
   if h.flag.nunique()==2:keep.append(h)
  chosen=pd.concat(keep) if keep else f.iloc[:0].copy()
  support.append({'repository':rid,'rule':rule,'eligible_rows':len(f),'eligible_flagged_rows':int(f.flag.sum()),'comparison_rows':len(chosen),'comparison_flagged_rows':int(chosen.flag.sum()),'excluded_rows':len(f)-len(chosen),'comparison_years':','.join(sorted(chosen.snapshot.unique()))})
  for kind in ['binary','count']:models.append({'repository':rid,'rule':rule,'endpoint':kind,**fit(chosen,'following365_raw_changes',kind)})
  for label,column,subset in [('ancestry_clock','following365_ancestry_clock_changes',chosen),('modification_only','following365_modifications',chosen),('no_recorded_exit_selected','following365_raw_changes',chosen[(chosen.terminal_deletion_events==0)&(chosen.outside_path_scope_events==0)&(chosen.type_change_events==0)])]:
   for kind in ['binary','count']:sensitivity.append({'repository':rid,'rule':rule,'variant':label,'endpoint':kind,**fit(subset,column,kind)})
  if any(m['repository']==rid and m['rule']==rule and m['endpoint']=='binary' and m['status']=='fitted' for m in models):
   blocks=(chosen.snapshot.astype(int)-2007)//3
   for block in sorted(blocks.unique()):block_results.append({'repository':rid,'rule':rule,'omitted_block_start':2007+int(block)*3,**fit(chosen[blocks!=block],'following365_raw_changes','binary',robust=False)})
  print(rid,rule,'eligible',len(f),'comparison',len(chosen),'main',models[-2]['status'],models[-2].get('effect',models[-2]['reason']),flush=True)
primary=[r for r in models if r['endpoint']=='binary' and r.get('p_value') is not None]
if primary:
 adjusted=multipletests([r['p_value'] for r in primary],method='holm')[1]
 for r,p in zip(primary,adjusted):r['holm_p_value']=float(p)
for name,rows in [('models',models),('descriptive',descriptive),('support',support),('sensitivity',sensitivity),('calendar-blocks',block_results)]:
 (OUT/(name+'.json')).write_text(json.dumps(rows,indent=2,allow_nan=False)+'\n');pd.DataFrame(rows).to_csv(OUT/(name+'.csv'),index=False)
# Vector figures: independent repository comparisons, no cross-project pooled estimate.
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'pdf.fonttype':42,'svg.fonttype':'none'})
for endpoint,filename,label,null in [('binary','adjusted-change-probability','Adjusted difference in change probability (percentage points)',0),('count','adjusted-change-count','Adjusted mean change-count ratio',1)]:
 fig,axes=plt.subplots(1,3,figsize=(11.4,3.5),layout='constrained')
 for ax,rule in zip(axes,RULES):
  ax.axvline(null,color='0.6',linewidth=.8,linestyle='--')
  for i,rid in enumerate(NAMES):
   r=next(r for r in models if r['repository']==rid and r['rule']==rule and r['endpoint']==endpoint)
   if r['status']=='fitted':
    value=r['effect'];lo=r.get('ci_low');hi=r.get('ci_high')
    if lo is not None and np.isfinite([lo,hi]).all():ax.errorbar(value,i,xerr=[[value-lo],[hi-value]],fmt='o',color='#245b78',capsize=3,markersize=5)
    else:ax.plot(value,i,'o',color='#245b78')
   else:ax.text(.98,i,'Descriptive only',ha='right',va='center',transform=ax.get_yaxis_transform(),fontsize=8,color='0.45')
  if endpoint=='count':ax.set_xscale('log')
  ax.set_yticks(range(3),list(NAMES.values()));ax.set_ylim(2.6,-.6);ax.set_title({'LongMethod':'Long Method','GodClass':'God Class','ObsoleteApiUsage':'Source-declared obsolete API'}[rule]);ax.grid(axis='x',alpha=.15);ax.spines[['top','right']].set_visible(False)
 fig.supxlabel(label);fig.savefig(OUT/(filename+'.pdf'));fig.savefig(OUT/(filename+'.png'),dpi=180);plt.close(fig)
seal(BASE/'protocols/final-automated-analysis-v0.7.md');seal(BASE/'protocols/statistics-runtime-lock.json');seal(Path(__file__))
(OUT/'input-seals.json').write_text(json.dumps(inputs,indent=2)+'\n')
(OUT/'execution.json').write_text(json.dumps({'protocol':'0.7','evidence_basis':'automated','human_validation_requirement_waived_by_user':True,'independent_validation_performed':False,'corrective_outcomes_estimated':False,'file_change_associations_estimated':True,'input_rows':len(all_data),'main_contrasts_with_intervals':len(primary),'packages':{x:__import__(x).__version__ for x in ['numpy','scipy','pandas','statsmodels','patsy','matplotlib']}},indent=2)+'\n')
print('Analysis completed:',OUT,flush=True)
