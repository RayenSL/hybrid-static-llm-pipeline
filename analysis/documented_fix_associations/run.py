"""Exploratory association of detector findings with observable fix-labelled edits."""
import os
for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'): os.environ[name]='1'
import argparse,bisect,collections,csv,gzip,hashlib,json,re,sqlite3,subprocess,sys
from pathlib import Path
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1]
P=argparse.ArgumentParser();P.add_argument('--packages',type=Path,required=True);P.add_argument('--output',type=Path,default=BASE/'results/v1.0');a=P.parse_args()
sys.path.insert(0,str(a.packages.resolve()))
import numpy as np,pandas as pd,patsy,statsmodels.api as sm
from scipy import stats
from statsmodels.stats.sandwich_covariance import cov_cluster_2groups
from statsmodels.stats.multitest import multipletests
RULES=['LongMethod','GodClass','ObsoleteApiUsage'];REPOS=['odoo__odoo','jenkinsci__jenkins','apache__tomcat'];DAY=86400
OUT=a.output.resolve()
if OUT.exists() and any(OUT.iterdir()):raise SystemExit(f'Refusing to overwrite {OUT}')
OUT.mkdir(parents=True,exist_ok=True)
def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def canonical(x):return (json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def csvout(name,rows,fields=None):
 path=OUT/name
 if not rows and fields is None:raise ValueError('Fields needed for empty table')
 with path.open('w',newline='',encoding='utf8') as f:
  w=csv.DictWriter(f,fieldnames=fields or list(rows[0]),lineterminator='\n',extrasaction='ignore');w.writeheader();w.writerows(rows)
def qualifies(repo,subject):
 if re.match(r'^\s*Revert\b',subject,re.I):return False
 if repo=='odoo__odoo':return bool(re.match(r'^\s*\[FIX\]',subject,re.I))
 if repo=='jenkinsci__jenkins':return bool(re.search(r'\bJENKINS-\d+\b',subject,re.I) and re.search(r'\b(?:fix|fixed|fixes|regression)\b',subject,re.I))
 bug=bool(re.search(r'\b(?:BZ|Bug)\s*[-#:]?\s*\d+\b|https?://bz\.apache\.org/bugzilla/show_bug\.cgi\?id=\d+',subject,re.I))
 return bug and bool(re.search(r'\b(?:fix|fixed|fixes|correct|resolve)\b',subject,re.I))

def candidate_history(repo):
 git='tmp/maintenance-associations/git/'+repo
 head=subprocess.run(['git','--git-dir='+git,'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
 proc=subprocess.run(['git','--git-dir='+git,'log','--first-parent','--format=%H%x09%s','HEAD'],capture_output=True,text=True,check=True)
 subjects={line[:40]:line[41:] for line in proc.stdout.splitlines() if len(line)>=41 and line[40]=='\t'}
 return head,subjects

def extract_outcome(df):
 all_candidates=[];all_file_events=[];extra=[]
 counts=np.zeros(len(df),dtype=int)
 for repo in REPOS:
  sub=df[df.rid==repo];dbpath=ROOT/f'tmp/maintenance-associations/file-events/{repo}.sqlite'
  con=sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True)
  events={h:(seq,t) for seq,h,t in con.execute('select seq,commit_hash,timestamp from events')}
  head,subjects=candidate_history(repo)
  if not set(events).issubset(subjects):raise ValueError(f'Missing first-parent messages for {repo}')
  qualified={h:subjects[h] for h in events if qualifies(repo,subjects[h])}
  byseq={events[h][0]:(h,events[h][1],subject) for h,subject in qualified.items()}
  bylineage=collections.defaultdict(list)
  total_mods=0
  for seq,lineage,path in con.execute("select seq,lineage,path from changes where status='M'"):
   total_mods+=1
   if seq in byseq:
    h,t,subject=byseq[seq]
    bylineage[int(lineage)].append((seq,int(t),h,path))
    all_file_events.append({'repository':repo,'seq':seq,'commit':h,'timestamp':t,'lineage':lineage,'path':path,'subject':subject})
  for lineage in bylineage:bylineage[lineage].sort()
  for idx,row in sub.iterrows():
   sequence=events.get(row.baseline_commit)
   if sequence is None:raise ValueError(f'Missing baseline: {repo} {row.baseline_commit}')
   base_seq=sequence[0];t=int(row.baseline_timestamp);list_=bylineage.get(int(row.lineage),[])
   pos=bisect.bisect_right(list_,(base_seq,10**20,'',''))
   count=sum(t < event[1] <= t+365*DAY for event in list_[pos:])
   counts[idx]=count
  all_candidates.extend({'repository':repo,'seq':events[h][0],'commit':h,'timestamp':events[h][1],'subject':subject} for h,subject in qualified.items())
  extra.append({'repository':repo,'git_head':head,'event_database_sha256':sha(dbpath),
                'history_commits':len(events),'qualifying_commits':len(qualified),
                'qualifying_modified_file_events':len([x for x in all_file_events if x['repository']==repo]),
                'all_modified_file_events':total_mods})
  con.close()
 df['documented_fix_events']=counts
 if not (df.documented_fix_events<=df.following365_modifications).all():raise ValueError('Candidate count exceeds all modifications')
 return all_candidates,all_file_events,extra

def design(f):
 terms=['flag','C(snapshot)']
 for name in ('logsize','logprior'):
  if f[name].nunique()>=5:
   knot=float((f[name].min()+f[name].max())/2)
   terms.append(f'bs({name}, knots=({knot!r},), degree=3, include_intercept=False)')
  elif f[name].nunique()>1:terms.append(name)
 return patsy.dmatrix('1+'+'+'.join(terms),f,return_type='dataframe')

def fit(f):
 y=(f.documented_fix_events.to_numpy()>0).astype(float)
 result={'status':'not_fitted','n':len(f),'flagged_rows':int(f.flag.sum()),'years':int(f.snapshot.nunique()),
         'flagged_lineages':int(f.loc[f.flag==1,'lineage'].nunique())}
 why=[]
 if f.snapshot.nunique()<2:why.append('fewer_than_two_comparison_years')
 for flag in (0,1):
  part=f[f.flag==flag];events=y[f.flag.to_numpy()==flag]
  if part.lineage.nunique()<20:why.append(f'group_{flag}_fewer_than_20_lineages')
  if (events>0).sum()<10 or (events==0).sum()<10:why.append(f'group_{flag}_fewer_than_10_events_or_nonevents')
 if why:result['reason']=';'.join(why);return result
 X=design(f);rank=np.linalg.matrix_rank(X.to_numpy())
 if rank<len(X.columns):result['reason']='rank_deficient_design';return result
 model=sm.OLS(y,X).fit();idx=list(X.columns).index('flag');beta=float(model.params.iloc[idx])
 covariance,_,_=cov_cluster_2groups(model,f.lineage.to_numpy(),pd.factorize(f.snapshot)[0],use_correction=True)
 variance=float(covariance[idx,idx]);df=min(f.lineage.nunique(),f.snapshot.nunique())-1
 result.update(status='fitted',reason='',difference_pp=beta*100,reference_df=int(df),
               prediction_outside_unit_interval_fraction=float(np.mean((model.predict(X)<0)|(model.predict(X)>1))))
 if variance>0 and np.isfinite(variance):
  se=variance**.5;crit=stats.t.ppf(.975,df)
  result.update(ci_low_pp=(beta-crit*se)*100,ci_high_pp=(beta+crit*se)*100,p_value=float(2*stats.t.sf(abs(beta/se),df)))
 else:result.update(ci_low_pp=None,ci_high_pp=None,p_value=None,interval_status='nonpositive_cluster_variance')
 return result

input_path=ROOT/'analysis/maintenance_associations/results/final-automated-analysis-v0.7/analysis-input.csv.gz'
df=pd.read_csv(input_path,compression='gzip',dtype={'snapshot':str})
if len(df)!=80993:raise ValueError('Unexpected cohort size')
candidates,file_events,history=extract_outcome(df)
csvout('candidate-commits.csv',sorted(candidates,key=lambda r:(r['repository'],r['seq'])))
csvout('candidate-file-events.csv',sorted(file_events,key=lambda r:(r['repository'],r['seq'],r['path'])))
with (OUT/'analysis-input.csv.gz').open('wb') as f:
 with gzip.GzipFile(filename='',fileobj=f,mode='wb',mtime=0) as z:z.write(df.to_csv(index=False,lineterminator='\n').encode())
df['logsize']=np.log1p(df.file_ploc);df['logprior']=np.log1p(df.prior365_raw_changes)
descriptive=[];support=[];models=[]
for repo in REPOS:
 for rule in RULES:
  f=df[df.rid==repo].copy()
  complete=f[rule+'_findings'].notna()
  eligible=f.named_definitions>0 if rule=='LongMethod' else f.classes>0 if rule=='GodClass' else f.resolved_api_pairs>0
  f=f[complete&eligible].copy();f['flag']=(f[rule+'_findings']>0).astype(int)
  for flag,g in f.groupby('flag'):
   descriptive.append({'repository':repo,'rule':rule,'flagged':int(flag),'rows':len(g),
                       'lineages':int(g.lineage.nunique()),'any_labelled_fix_fraction':float((g.documented_fix_events>0).mean()),
                       'mean_labelled_fix_events':float(g.documented_fix_events.mean()),
                       'median_ploc':float(g.file_ploc.median()),'median_prior_changes':float(g.prior365_raw_changes.median())})
  keep=[]
  for year,g in f.groupby('snapshot'):
   if g.flag.nunique()!=2:continue
   mask=np.ones(len(g),dtype=bool)
   for cov in ('file_ploc','prior365_raw_changes'):
    ranges=g.groupby('flag')[cov].agg(['min','max']);lo=ranges['min'].max();hi=ranges['max'].min()
    mask &= g[cov].between(lo,hi).to_numpy()
   h=g[mask]
   if h.flag.nunique()==2:keep.append(h)
  chosen=pd.concat(keep) if keep else f.iloc[:0].copy()
  support.append({'repository':repo,'rule':rule,'eligible_rows':len(f),'eligible_flagged_rows':int(f.flag.sum()),
                  'comparison_rows':len(chosen),'comparison_flagged_rows':int(chosen.flag.sum()),
                  'excluded_rows':len(f)-len(chosen),'comparison_years':','.join(sorted(chosen.snapshot.unique()))})
  models.append({'repository':repo,'rule':rule,**fit(chosen)})
  print(repo,rule,'eligible',len(f),'comparison',len(chosen),'model',models[-1]['status'],models[-1].get('difference_pp',models[-1].get('reason')),flush=True)
valid=[m for m in models if m.get('p_value') is not None]
if valid:
 adjusted=multipletests([m['p_value'] for m in valid],method='holm')[1]
 for m,p in zip(valid,adjusted):m['holm_p_value']=float(p)
for name,rows in [('descriptive',descriptive),('support',support),('models',models)]:
 csvout(name+'.csv',rows);(OUT/(name+'.json')).write_bytes(canonical(rows))
provenance={'protocol':'v1.0','input_sha256':sha(input_path),'script_sha256':sha(Path(__file__)),
            'protocol_sha256':sha(BASE/'PROTOCOL.md'),'history':history,'cohort_rows':len(df),
            'candidate_commits':len(candidates),'candidate_file_events':len(file_events)}
(OUT/'provenance.json').write_bytes(canonical(provenance))
seals={p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file()}
(OUT/'SHA256SUMS.json').write_bytes(canonical(seals))
print('Completed',OUT,flush=True)
