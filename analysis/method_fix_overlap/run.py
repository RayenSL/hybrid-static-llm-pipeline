"""Exploratory within-file, method-level overlap with issue-linked fix-labelled edits."""
import os
for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[name]='1'
import argparse,collections,csv,gzip,hashlib,json,math,re,sqlite3,subprocess,sys,tarfile,difflib
from pathlib import Path
from tree_sitter import Language,Parser
import tree_sitter_java
ROOT=Path(__file__).resolve().parents[2];BASE=Path(__file__).resolve().parent
P=argparse.ArgumentParser();P.add_argument('--parser-packages',type=Path,required=True);P.add_argument('--statistics-packages',type=Path,required=True);P.add_argument('--output',type=Path,required=True);P.add_argument('--preflight',action='store_true');a=P.parse_args()
# Parser imports must resolve from the checksum-pinned package directory supplied by caller.
# Imports above are loaded through PYTHONPATH; validate their versions here.
from importlib.metadata import version
assert version('tree-sitter')=='0.25.2' and version('tree-sitter-java')=='0.23.5'
sys.path.insert(0,str(a.statistics_packages.resolve()))
import numpy as np,pandas as pd,statsmodels.api as sm
from scipy import stats
from statsmodels.stats.sandwich_covariance import cov_cluster_2groups
OUT=a.output.resolve()
if OUT.exists() and any(OUT.iterdir()):raise SystemExit(f'Refusing to overwrite {OUT}')
OUT.mkdir(parents=True,exist_ok=True)
REPOS=('jenkinsci__jenkins','apache__tomcat');DAY=86400
BUNDLE=ROOT/'analysis/multilanguage_evolution/results/three-rule-evidence.tar.gz'
COHORT=ROOT/'analysis/maintenance_associations/results/final-automated-analysis-v0.7/analysis-input.csv.gz'
EVENTS=ROOT/'analysis/documented_fix_associations/results/v1.0/candidate-file-events.csv'
PARSER=Parser(Language(tree_sitter_java.language()))
def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def dump(name,obj):
 (OUT/name).write_text(json.dumps(obj,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf8')
def write(name,rows,fields):
 with (OUT/name).open('w',newline='',encoding='utf8') as f:
  w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n',extrasaction='ignore');w.writeheader();w.writerows(rows)
def gitdir(repo):return ROOT/'tmp/maintenance-associations/git'/repo
class BlobReader:
 def __init__(self,repo):
  self.proc=subprocess.Popen(['git',f'--git-dir={gitdir(repo)}','cat-file','--batch'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 def read(self,oid):
  self.proc.stdin.write((oid+'\n').encode());self.proc.stdin.flush()
  header=self.proc.stdout.readline().split()
  if len(header)!=3 or header[1]!=b'blob':raise ValueError(f'Blob unavailable {oid}: {header!r}')
  data=self.proc.stdout.read(int(header[2]));assert self.proc.stdout.read(1)==b'\n'
  return data
 def close(self):
  self.proc.stdin.close();self.proc.stdout.close();self.proc.terminate();self.proc.wait()
def walk(root):
 stack=[root]
 while stack:
  n=stack.pop();yield n;stack.extend(reversed(n.children))
def name_of(n):
 name=n.child_by_field_name('name')
 if name:return name.text.decode('utf8','replace')
 decl=n.child_by_field_name('declarator')
 if decl:
  while decl.child_by_field_name('declarator'):decl=decl.child_by_field_name('declarator')
  return decl.text.decode('utf8','replace')
 return '<unnamed>'
BOUNDARIES={'function_definition','method_declaration','constructor_declaration','lambda','lambda_expression','class_definition','class_declaration','interface_declaration','enum_declaration','record_declaration','class_specifier','struct_specifier'}
def methods(data):
 tree=PARSER.parse(data);out=collections.defaultdict(list)
 for n in walk(tree.root_node):
  if n.type not in ('method_declaration','constructor_declaration'):continue
  body=n.child_by_field_name('body')
  if body is None:continue
  outer=[];parent=n.parent
  while parent:
   if parent.type in BOUNDARIES and parent.child_by_field_name('name'):outer.append(name_of(parent))
   parent=parent.parent
  sym='.'.join(list(reversed(outer))+[name_of(n)])
  out[sym].append({'declaration_start':n.start_point.row+1,'declaration_end':n.end_point.row+1,
                   'body_start':body.start_point.row+1,'body_end':body.end_point.row+1})
 return out,tree.root_node.has_error
def changed_old_lines(old,new):
 left=old.splitlines();right=new.splitlines();changes=[]
 for tag,i1,i2,j1,j2 in difflib.SequenceMatcher(None,left,right,autojunk=True).get_opcodes():
  if tag!='equal':changes.append((i1,i2,tag))
 return changes
def intersects(changes,lo,hi,body=False):
 for i1,i2,_ in changes:
  if i1<i2:
   if i1+1<=hi and i2>=lo:return True
  elif (lo<=i1<hi if body else lo-1<=i1<=hi):return True
 return False
# Exact baseline file lineage and timestamp from the corrected cohort.
cohorts={}
with gzip.open(COHORT,'rt',encoding='utf8',newline='') as f:
 for r in csv.DictReader(f):
  if r['rid'] in REPOS:cohorts[(r['rid'],r['baseline_commit'],r['baseline_path'])]=r
# All first-parent events, with blob identities supplied by the sealed event database.
candidates=collections.defaultdict(list)
with EVENTS.open(newline='',encoding='utf8') as f:
 for r in csv.DictReader(f):
  if r['repository'] in REPOS and r['path'].endswith('.java'):
   candidates[(r['repository'],int(r['lineage']))].append(r)
for group in candidates.values():group.sort(key=lambda r:int(r['seq']))
pairs=[];matching=[];snapshots=[];source_hashes={}
with tarfile.open(BUNDLE,'r:gz') as archive:
 for repo in REPOS:
  db=sqlite3.connect('file:'+str(ROOT/f'tmp/maintenance-associations/file-events/{repo}.sqlite')+'?mode=ro',uri=True)
  event_lookup={h:(int(seq),int(timestamp)) for seq,h,timestamp in db.execute('select seq,commit_hash,timestamp from events')}
  for year in range(2007,2025):
   member=f'raw/{repo}-{year}.syntax.json';raw=archive.extractfile(member).read();source_hashes[member]=hashlib.sha256(raw).hexdigest();x=json.loads(raw)
   if x['status']['syntax']!='complete':continue
   commit=x['commit'];seq,timestamp=event_lookup[commit]
   finding_ids={d['id'] for d in x['findings']}
   groups=collections.defaultdict(list)
   for d in x['definitions']:groups[d['path']].append(d)
   snapshots.append({'repository':repo,'year':year,'commit':commit,'seq':seq,'timestamp':timestamp,'definitions':len(x['definitions']),'findings':len(x['findings'])})
   for path,ds in groups.items():
    cohort=cohorts.get((repo,commit,path))
    if cohort is None:continue
    symbols=collections.Counter(d['symbol'] for d in ds)
    flagged=[d for d in ds if d['id'] in finding_ids and symbols[d['symbol']]==1]
    controls=[d for d in ds if d['id'] not in finding_ids and symbols[d['symbol']]==1]
    for d in ds:
     if (d['id'] in finding_ids)!=(d['metrics']['cyclomatic_complexity']>10):raise ValueError('Finding/threshold disagreement')
    for d in sorted(flagged,key=lambda d:d['symbol']):
     n=d['metrics']['physical_lines']
     valid=[c for c in controls if max(n,c['metrics']['physical_lines'])<=2*min(n,c['metrics']['physical_lines'])]
     record={'repository':repo,'year':year,'commit':commit,'path':path,'lineage':int(cohort['lineage']),'flagged_symbol':d['symbol'],'flagged_lines':n,'status':'unmatched'}
     if valid:
      c=min(valid,key=lambda c:(abs(math.log1p(n)-math.log1p(c['metrics']['physical_lines'])),c['symbol']))
      controls.remove(c);record.update(status='matched',control_symbol=c['symbol'],control_lines=c['metrics']['physical_lines'])
      pairs.append({'repository':repo,'year':year,'commit':commit,'baseline_seq':seq,'baseline_timestamp':timestamp,
                    'baseline_path':path,'lineage':int(cohort['lineage']),'flagged_symbol':d['symbol'],'control_symbol':c['symbol'],
                    'flagged_lines':n,'control_lines':c['metrics']['physical_lines'],'file_ploc':int(cohort['file_ploc']),
                    'prior365_file_changes':int(cohort['prior365_raw_changes']),
                    'flagged_body_edit':0,'control_body_edit':0,'flagged_declaration_edit':0,'control_declaration_edit':0,
                    'flagged_unresolved':False,'control_unresolved':False,'candidate_file_events':0})
     matching.append(record)
  db.close()
  print(repo,'matched pairs',sum(p['repository']==repo for p in pairs),flush=True)
# Restrict to the candidate events that could affect a matched pair. Each event is parsed once.
by_event=collections.defaultdict(list)
for i,p in enumerate(pairs):
 for e in candidates.get((p['repository'],p['lineage']),[]):
  if int(e['seq'])<=p['baseline_seq']:continue
  if not p['baseline_timestamp']<int(e['timestamp'])<=p['baseline_timestamp']+365*DAY:continue
  by_event[(p['repository'],int(e['seq']),p['lineage'],e['path'])].append(i)
  p['candidate_file_events']+=1
# Fetch precise old/new blobs from the sealed lineage ledger; no source checkout is modified.
event_meta={}
for repo in REPOS:
 dbpath=ROOT/f'tmp/maintenance-associations/file-events/{repo}.sqlite'
 con=sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True)
 wanted={(seq,lineage,path) for r,seq,lineage,path in by_event if r==repo}
 for seq,path,old_blob,new_blob,lineage in con.execute("select seq,path,old_blob,new_blob,lineage from changes where status='M'"):
  key=(int(seq),int(lineage),path)
  if key in wanted:event_meta[(repo,*key)]=(old_blob,new_blob)
 con.close()
 if sum(k[0]==repo for k in event_meta)!=len(wanted):raise ValueError('Candidate event blob identity missing')
availability=[];missing_rows=[]
for repo in REPOS:
 related=[(k,v) for k,v in event_meta.items() if k[0]==repo]
 oids=sorted({oid for _,v in related for oid in v})
 env=os.environ.copy();env['GIT_NO_LAZY_FETCH']='1'
 proc=subprocess.run(['git',f'--git-dir={gitdir(repo)}','cat-file','--batch-all-objects','--batch-check=%(objectname)'],capture_output=True,text=True,env=env,check=True)
 local=set(proc.stdout.splitlines()) & set(oids)
 both=sum(all(oid in local for oid in v) for _,v in related)
 availability.append({'repository':repo,'candidate_event_keys':len(related),'unique_blobs':len(oids),'local_blobs':len(local),'events_with_both_blobs_local':both,
                      'matched_pairs':sum(p['repository']==repo for p in pairs),
                      'unmatched_flagged_definitions':sum(m['repository']==repo and m['status']=='unmatched' for m in matching)})
 missing_rows += [{'repository':repo,'blob':oid} for oid in oids if oid not in local]
dump('availability.json',availability)
write('missing-blobs.csv',missing_rows,['repository','blob'])
print(availability,flush=True)
if a.preflight:
 dump('provenance.json',{'protocol':'v0.1','script_sha256':sha(Path(__file__)),'protocol_sha256':sha(BASE/'PROTOCOL.md'),
  'bundle_sha256':sha(BUNDLE),'cohort_sha256':sha(COHORT),'candidate_file_events_sha256':sha(EVENTS),
  'event_databases_sha256':{r:sha(ROOT/f'tmp/maintenance-associations/file-events/{r}.sqlite') for r in REPOS},
  'parser_versions':{'tree-sitter':version('tree-sitter'),'tree-sitter-java':version('tree-sitter-java')},
  'syntax_reports_sha256':source_hashes})
 dump('SHA256SUMS.json',{p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file()})
 raise SystemExit(0)
if missing_rows:raise SystemExit(f'{len(missing_rows)} required source blobs are absent; inspect {OUT}/missing-blobs.csv and restore them before analysis')
event_audit=[]
for repo in REPOS:
 reader=BlobReader(repo)
 try:
  subset=sorted((k,ids) for k,ids in by_event.items() if k[0]==repo)
  for j,(key,ids) in enumerate(subset,1):
   _,seq,lineage,path=key;old_oid,new_oid=event_meta[key]
   old=reader.read(old_oid);new=reader.read(new_oid)
   parsed,parse_error=methods(old);changes=changed_old_lines(old,new)
   for i in ids:
    p=pairs[i]
    audit={'repository':repo,'year':p['year'],'baseline_commit':p['commit'],'baseline_path':p['baseline_path'],
           'lineage':lineage,'seq':seq,'event_path':path,'flagged_symbol':p['flagged_symbol'],'control_symbol':p['control_symbol'],
           'old_blob':old_oid,'new_blob':new_oid,'parse_error':int(parse_error)}
    for label in ('flagged','control'):
     sym=p[label+'_symbol'];options=parsed.get(sym,[])
     if parse_error or len(options)!=1:
      p[label+'_unresolved']=True;audit[label+'_status']='parse_error' if parse_error else ('missing' if not options else 'ambiguous')
      audit[label+'_body_edit']='';audit[label+'_declaration_edit']=''
     else:
      m=options[0];body=intersects(changes,m['body_start'],m['body_end'],True)
      declaration=intersects(changes,m['declaration_start'],m['declaration_end'])
      p[label+'_body_edit']|=int(body);p[label+'_declaration_edit']|=int(declaration)
      audit[label+'_status']='matched';audit[label+'_body_edit']=int(body);audit[label+'_declaration_edit']=int(declaration)
    event_audit.append(audit)
   if j%100==0:print(repo,'events',j,'/',len(subset),flush=True)
 finally:reader.close()
# Paired-difference estimates. An unresolved method cannot silently become a zero.
results=[]
for repo in REPOS:
 allpairs=[p for p in pairs if p['repository']==repo]
 complete=[p for p in allpairs if not(p['flagged_unresolved'] or p['control_unresolved'])]
 diff=np.array([p['flagged_body_edit']-p['control_body_edit'] for p in complete],dtype=float)
 result={'repository':repo,'matched_pairs':len(allpairs),'complete_pairs':len(complete),
         'unresolved_pairs':len(allpairs)-len(complete),'candidate_event_exposed_pairs':sum(p['candidate_file_events']>0 for p in allpairs),
         'flagged_body_edit_pairs':sum(p['flagged_body_edit'] for p in complete),
         'control_body_edit_pairs':sum(p['control_body_edit'] for p in complete),
         'flagged_risk':float(np.mean([p['flagged_body_edit'] for p in complete])),
         'control_risk':float(np.mean([p['control_body_edit'] for p in complete])),
         'difference_pp':float(diff.mean()*100),
         'distinct_lineages':len({p['lineage'] for p in complete}),'years':len({p['year'] for p in complete})}
 if len(complete)>1 and result['distinct_lineages']>1 and result['years']>1:
  model=sm.OLS(diff,np.ones((len(diff),1))).fit()
  lineage=np.array([p['lineage'] for p in complete]);year=np.array([p['year'] for p in complete])
  cov,_,_=cov_cluster_2groups(model,lineage,year,use_correction=True)
  var=float(cov[0,0]);df=min(result['distinct_lineages'],result['years'])-1
  result['cluster_variance']=var;result['reference_df']=df
  if var>0 and math.isfinite(var):
   se=math.sqrt(var);critical=stats.t.ppf(.975,df);b=diff.mean()
   result.update(ci_low_pp=float((b-critical*se)*100),ci_high_pp=float((b+critical*se)*100),
                 p_value=float(2*stats.t.sf(abs(b/se),df)))
 results.append(result)
 print(repo,result,flush=True)
write('matching.csv',matching,['repository','year','commit','path','lineage','flagged_symbol','flagged_lines','status','control_symbol','control_lines'])
write('pairs.csv',pairs,['repository','year','commit','baseline_seq','baseline_timestamp','baseline_path','lineage','flagged_symbol','control_symbol','flagged_lines','control_lines','file_ploc','prior365_file_changes','flagged_body_edit','control_body_edit','flagged_declaration_edit','control_declaration_edit','flagged_unresolved','control_unresolved','candidate_file_events'])
write('event-audit.csv',event_audit,['repository','year','baseline_commit','baseline_path','lineage','seq','event_path','flagged_symbol','control_symbol','old_blob','new_blob','parse_error','flagged_status','flagged_body_edit','flagged_declaration_edit','control_status','control_body_edit','control_declaration_edit'])
write('snapshots.csv',snapshots,['repository','year','commit','seq','timestamp','definitions','findings'])
dump('results.json',results)
dump('provenance.json',{'protocol':'v0.1','script_sha256':sha(Path(__file__)),'protocol_sha256':sha(BASE/'PROTOCOL.md'),
 'bundle_sha256':sha(BUNDLE),'cohort_sha256':sha(COHORT),'candidate_file_events_sha256':sha(EVENTS),
 'event_databases_sha256':{r:sha(ROOT/f'tmp/maintenance-associations/file-events/{r}.sqlite') for r in REPOS},
 'parser_versions':{'tree-sitter':version('tree-sitter'),'tree-sitter-java':version('tree-sitter-java')},
 'syntax_reports_sha256':source_hashes,'candidate_event_keys':len(by_event),'event_audit_rows':len(event_audit)})
dump('SHA256SUMS.json',{p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file()})
