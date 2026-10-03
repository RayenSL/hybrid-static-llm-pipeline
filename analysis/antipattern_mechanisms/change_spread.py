"""Explore whether edits to God-Class files co-modify other baseline production files."""
import os
for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[name]='1'
import argparse,bisect,collections,csv,gzip,hashlib,json,math,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BASE=Path(__file__).resolve().parent
P=argparse.ArgumentParser();P.add_argument('--packages',type=Path,required=True);P.add_argument('--output',type=Path,required=True);a=P.parse_args()
sys.path.insert(0,str(a.packages.resolve()))
import numpy as np,pandas as pd,patsy,statsmodels.api as sm
from scipy import stats
from statsmodels.stats.sandwich_covariance import cov_cluster_2groups
OUT=a.output.resolve()
if OUT.exists() and any(OUT.iterdir()):raise SystemExit(f'Refusing to overwrite {OUT}')
OUT.mkdir(parents=True,exist_ok=True)
REPOS=('odoo__odoo','jenkinsci__jenkins','apache__tomcat');DAY=86400
INPUT=ROOT/'analysis/maintenance_associations/results/final-automated-analysis-v0.7/analysis-input.csv.gz'
def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(name,rows,fields):
 with (OUT/name).open('w',newline='',encoding='utf8') as f:
  w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n',extrasaction='ignore');w.writeheader();w.writerows(rows)
def dump(name,obj):(OUT/name).write_text(json.dumps(obj,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf8')
df=pd.read_csv(INPUT,compression='gzip',dtype={'snapshot':str})
if len(df)!=80993:raise ValueError('Unexpected corrected cohort size')
file_rows=[];event_rows=[];db_hashes={};mismatches=[]
for repo in REPOS:
 f=df[df.rid==repo].copy();dbpath=ROOT/f'tmp/maintenance-associations/file-events/{repo}.sqlite';db_hashes[repo]=sha(dbpath)
 con=sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True)
 events={h:(int(seq),int(ts)) for seq,h,ts in con.execute('select seq,commit_hash,timestamp from events')}
 byseq=collections.defaultdict(set);bylineage=collections.defaultdict(list)
 for seq,lineage in con.execute("select seq,lineage from changes where status='M'"):
  seq=int(seq);lineage=int(lineage);byseq[seq].add(lineage);bylineage[lineage].append(seq)
 timestamps={seq:t for seq,h,t in con.execute('select seq,commit_hash,timestamp from events')}
 for lineage in bylineage:bylineage[lineage].sort()
 print(repo,'modification events',sum(len(v) for v in bylineage.values()),flush=True)
 for year,g in f.groupby('snapshot',sort=True):
  commits=g.baseline_commit.unique()
  if len(commits)!=1:raise ValueError('Multiple baseline commits')
  base_seq,base_t=events[commits[0]];production=set(int(x) for x in g.lineage)
  # A file's recorded modifications are joined to the baseline production inventory.
  co_by_seq={}
  for seq,lineages in byseq.items():
   if seq<=base_seq:continue
   t=timestamps[seq]
   if not base_t<t<=base_t+365*DAY:continue
   n=len(lineages & production)
   if n:co_by_seq[seq]=n
  for row in g.itertuples():
   if pd.isna(row.GodClass_findings) or row.classes<=0:continue
   lineage=int(row.lineage);seqs=bylineage.get(lineage,[]);start=bisect.bisect_right(seqs,base_seq)
   selected=[s for s in seqs[start:] if s in co_by_seq]
   expected=int(row.following365_modifications)
   if len(selected)!=expected:mismatches.append({'repository':repo,'year':year,'path':row.baseline_path,'expected':expected,'observed':len(selected)})
   co=[max(0,co_by_seq[s]-1) for s in selected]
   kept=[x for x in co if x<20] # keep commits with at most 20 baseline-production files including this one
   file_rows.append({'repository':repo,'year':year,'baseline_commit':row.baseline_commit,'path':row.baseline_path,
                     'lineage':lineage,'flag':int(row.GodClass_findings>0),'file_ploc':int(row.file_ploc),
                     'prior365_changes':int(row.prior365_raw_changes),'modification_events':len(co),
                     'events_with_cochange':sum(x>0 for x in co),'other_file_modifications':sum(co),
                     'cochange_fraction':sum(x>0 for x in co)/len(co) if co else '',
                     'nonbulk_events':len(kept),'nonbulk_cochange_fraction':sum(x>0 for x in kept)/len(kept) if kept else ''})
   for s,n in zip(selected,co):
    event_rows.append({'repository':repo,'year':year,'baseline_path':row.baseline_path,'lineage':lineage,'flag':int(row.GodClass_findings>0),
                       'seq':s,'timestamp':timestamps[s],'other_baseline_production_modifications':n,'any_cochange':int(n>0),'bulk_excluded':int(n>=20)})
 con.close()
if mismatches:
 write('event-count-mismatches.csv',mismatches,['repository','year','path','expected','observed'])
 raise ValueError(f'{len(mismatches)} event counts differ from corrected cohort; audit required')
# Reproduce the prior overlap restriction before selecting files with follow-up modifications.
rows=pd.DataFrame(file_rows);rows['logsize']=np.log1p(rows.file_ploc);rows['logprior']=np.log1p(rows.prior365_changes)
def design(f):
 terms=['flag','C(year)']
 for name in ('logsize','logprior'):
  if f[name].nunique()>=5:
   knot=float((f[name].min()+f[name].max())/2)
   terms.append(f'bs({name}, knots=({knot!r},), degree=3, include_intercept=False)')
  elif f[name].nunique()>1:terms.append(name)
 return patsy.dmatrix('1+'+'+'.join(terms),f,return_type='dataframe')
def model(f,outcome):
 result={'n_files':len(f),'flagged_files':int(f.flag.sum()),'lineages':int(f.lineage.nunique()),'years':int(f.year.nunique()),'status':'not_fitted'}
 if len(f)<50 or f.year.nunique()<2 or min(f.groupby('flag').lineage.nunique().reindex([0,1],fill_value=0))<20:
  result['reason']='insufficient_support';return result
 X=design(f);y=f[outcome].astype(float).to_numpy()
 if np.linalg.matrix_rank(X.to_numpy())<X.shape[1]:result['reason']='rank_deficient_design';return result
 fit=sm.OLS(y,X).fit();idx=list(X.columns).index('flag');cov,_,_=cov_cluster_2groups(fit,f.lineage.to_numpy(),pd.factorize(f.year)[0],use_correction=True)
 var=float(cov[idx,idx]);beta=float(fit.params.iloc[idx]);df=min(f.lineage.nunique(),f.year.nunique())-1
 result.update(status='fitted',difference_pp=100*beta,reference_df=int(df),cluster_variance=var)
 if var>0 and math.isfinite(var):
  se=math.sqrt(var);crit=stats.t.ppf(.975,df)
  result.update(ci_low_pp=100*(beta-crit*se),ci_high_pp=100*(beta+crit*se),p_value=float(2*stats.t.sf(abs(beta/se),df)))
 return result
support=[];models=[];descriptive=[]
for repo in REPOS:
 f=rows[rows.repository==repo].copy()
 for flag,g in f.groupby('flag'):
  positive=g[g.modification_events>0]
  descriptive.append({'repository':repo,'flag':int(flag),'eligible_files':len(g),'files_with_modifications':len(positive),
                      'modification_events':int(g.modification_events.sum()),'events_with_other_production_file':int(g.events_with_cochange.sum()),
                      'event_cochange_fraction':float(g.events_with_cochange.sum()/g.modification_events.sum()) if g.modification_events.sum() else None,
                      'mean_file_cochange_fraction':float(positive.cochange_fraction.astype(float).mean()) if len(positive) else None})
 keep=[]
 for year,g in f.groupby('year'):
  if g.flag.nunique()!=2:continue
  mask=np.ones(len(g),dtype=bool)
  for col in ('file_ploc','prior365_changes'):
   bounds=g.groupby('flag')[col].agg(['min','max']);mask &= g[col].between(bounds['min'].max(),bounds['max'].min()).to_numpy()
  h=g[mask]
  if h.flag.nunique()==2:keep.append(h)
 selected=pd.concat(keep) if keep else f.iloc[:0].copy()
 mod=selected[selected.modification_events>0].copy();bulk=selected[selected.nonbulk_events>0].copy()
 support.append({'repository':repo,'eligible_rows':len(f),'overlap_rows':len(selected),'overlap_flagged_rows':int(selected.flag.sum()),
                 'modified_rows':len(mod),'modified_flagged_rows':int(mod.flag.sum()),
                 'nonbulk_rows':len(bulk),'nonbulk_flagged_rows':int(bulk.flag.sum())})
 models.append({'repository':repo,'analysis':'main_all_modifications',**model(mod,'cochange_fraction')})
 models.append({'repository':repo,'analysis':'exclude_bulk_commits',**model(bulk,'nonbulk_cochange_fraction')})
 print(repo,models[-2:],flush=True)
write('file-outcomes.csv',file_rows,['repository','year','baseline_commit','path','lineage','flag','file_ploc','prior365_changes','modification_events','events_with_cochange','other_file_modifications','cochange_fraction','nonbulk_events','nonbulk_cochange_fraction'])
write('event-audit.csv',event_rows,['repository','year','baseline_path','lineage','flag','seq','timestamp','other_baseline_production_modifications','any_cochange','bulk_excluded'])
for name,data in [('descriptive',descriptive),('support',support),('models',models)]:dump(name+'.json',data)
dump('provenance.json',{'protocol_sha256':sha(BASE/'PROTOCOL.md'),'script_sha256':sha(Path(__file__)),'input_sha256':sha(INPUT),'event_databases_sha256':db_hashes,'baseline_rows':len(df)})
dump('SHA256SUMS.json',{p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file()})
