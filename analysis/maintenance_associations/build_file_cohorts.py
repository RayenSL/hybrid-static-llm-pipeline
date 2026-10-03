"""Join frozen baseline files/findings to raw change activity; no corrective labels."""
import argparse,bisect,collections,csv,datetime as dt,gzip,hashlib,json,sqlite3,tarfile,tempfile,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'analysis/maintenance_associations'
NAMES={'odoo__odoo':'Odoo','jenkinsci__jenkins':'Jenkins','apache__tomcat':'Apache Tomcat'}
RULES=['LongMethod','GodClass','ObsoleteApiUsage'];DAY=86400
ap=argparse.ArgumentParser()
ap.add_argument('--repository',choices=list(NAMES))
ap.add_argument('--output',type=Path,default=BASE/'results/file-cohorts')
ap.add_argument('--calendar-correction',type=Path,help='Directory containing the v0.2 replacement reports')
a=ap.parse_args()
if a.calendar_correction and a.output.resolve()==(BASE/'results/file-cohorts').resolve():
 raise ValueError('Corrected cohorts require a separate output directory')
eligible={}
with (BASE/'results/baseline-eligibility.csv').open() as f:
 for r in csv.DictReader(f):
  if r['temporally_eligible']=='True':eligible[(r['repository'],r['snapshot'],r['rule'])]=r
out=a.output;out.mkdir(parents=True,exist_ok=True)
if any((out/(rid+'.csv.gz')).exists() for rid in NAMES if not a.repository or rid==a.repository):raise FileExistsError('Use a fresh cohort output directory')
reports=[];syntax_counts={}
with tarfile.open(ROOT/'analysis/multilanguage_evolution/results/three-rule-evidence.tar.gz') as archive:
 for m in archive:
  if m.name.endswith('.syntax.json'):
   key=Path(m.name).name.removesuffix('.syntax.json');data=json.load(archive.extractfile(m))
   syntax_counts[key]=collections.Counter(d['path'] for d in data['definitions'])
  elif m.name.endswith('.three-rules.json'):
   key=Path(m.name).name.removesuffix('.three-rules.json');rid,label=key.split('-',1)
   if any((NAMES[rid],label,r) in eligible for r in RULES):reports.append((rid,label,key,json.load(archive.extractfile(m))))
replacement_commits={}
if a.calendar_correction:
 correction=a.calendar_correction
 manifest=json.loads((correction/'manifest.json').read_text())
 frozen=json.loads((BASE/'protocols/calendar-frontier-v0.2.json').read_text())
 assert {(r['snapshot'],r['proposed_commit']) for r in manifest}=={(r['snapshot'],r['proposed_commit']) for r in frozen['replacements']}
 for record in manifest:
  rid=record['repository'];label=record['snapshot'];key=rid+'-'+label
  if a.repository and rid!=a.repository:continue
  p=correction/(key+'.three-rules.json')
  assert hashlib.sha256(p.read_bytes()).hexdigest()==record['sha256']
  data=json.loads(p.read_text());assert data['commit']==record['proposed_commit']
  syntax_path=correction/(key+'.syntax.json');syntax=json.loads(syntax_path.read_text())
  assert hashlib.sha256(syntax_path.read_bytes()).hexdigest()==data['syntax_report_sha256']
  assert syntax['commit']==data['commit']
  old=next(d for rr,ll,kk,d in reports if rr==rid and ll==label)
  assert old['commit']==record['frozen_commit']
  reports=[r for r in reports if not (r[0]==rid and r[1]==label)]
  reports.append((rid,label,key,data))
  syntax_counts[key]=collections.Counter(d['path'] for d in syntax['definitions'])
  replacement_commits[(rid,label)]=data['commit']
summaries=[];replacement_eligibility=[]
for rid in NAMES:
 if a.repository and rid!=a.repository:continue
 dbpath=ROOT/f'tmp/maintenance-associations/file-events/{rid}.sqlite'
 local=tempfile.TemporaryDirectory(prefix='maintenance-cohort-')
 localdb=Path(local.name)/'events.sqlite';shutil.copyfile(dbpath,localdb)
 expected=json.loads((BASE/'results/file-events'/f'{rid}.json').read_text())['database_sha256']
 with localdb.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==expected,'File-event database seal mismatch'
 db=sqlite3.connect(f'file:{localdb}?mode=ro',uri=True)
 event_rows=list(db.execute('SELECT seq,commit_hash,timestamp FROM events ORDER BY seq'))
 seq_by_hash={h:s for s,h,t in event_rows};timestamps=[0]+[t for s,h,t in event_rows]
 effective=[0];clock=0
 for s,h,t in event_rows:clock=max(clock,t);effective.append(clock)
 if a.calendar_correction:
  history_info=json.loads((ROOT/f'analysis/multilanguage_evolution/selection/histories/{rid}.json').read_text())
  start=dt.datetime.fromisoformat(history_info['earliest_source']['committer_date']).timestamp()
  cutoff=dt.datetime.fromisoformat('2026-09-14T00:00:00+00:00').timestamp()
  for rr,label,key,data in reports:
   if rr!=rid or (rid,label) not in replacement_commits:continue
   t=timestamps[seq_by_hash[data['commit']]]
   for rule in data['rules']:
    reasons=[]
    if rule['status']!='complete':reasons.append('incomplete_detector_observation')
    if t+365*DAY>cutoff:reasons.append('insufficient_follow_up_before_cutoff')
    if t-365*DAY<start:reasons.append('insufficient_preserved_baseline_history')
    entry={'repository':NAMES[rid],'snapshot':label,'rule':rule['rule'],'commit':data['commit'],'baseline_timestamp':t,'follow_up_end_timestamp':t+365*DAY,'temporally_eligible':not reasons,'exclusion_reasons':reasons,'scientifically_admitted':False}
    replacement_eligibility.append(entry)
    k=(NAMES[rid],label,rule['rule'])
    if reasons:eligible.pop(k,None)
    else:eligible[k]=entry
 history_cache={}
 def history(lineage):
  if lineage not in history_cache:
   groups=collections.defaultdict(set)
   for seq,status in db.execute('SELECT seq,status FROM changes WHERE lineage=? ORDER BY seq',(lineage,)):groups[seq].add(status)
   history_cache[lineage]=[(seq,'D' in statuses and 'A' not in statuses) for seq,statuses in sorted(groups.items())]
  return history_cache[lineage]
 csv_path=out/(rid+'.csv.gz');row_count=0;unresolved=0;clock_flags=0;deletions=0
 columns=['repository','snapshot','baseline_commit','baseline_path','lineage','baseline_timestamp','file_ploc','named_definitions','classes','LongMethod_findings','GodClass_findings','ObsoleteApiUsage_findings','prior365_raw_changes','following365_raw_changes','following365_ancestry_clock_changes','baseline_clock_shift_seconds','first_followup_deletion_commit','lineage_status','confirmed_corrective_changes','scientifically_admitted']
 with csv_path.open('wb') as compressed:
  with gzip.GzipFile(filename='',mode='wb',fileobj=compressed,mtime=0) as gz:
   import io
   with io.TextIOWrapper(gz,encoding='utf-8',newline='') as text:
    writer=csv.DictWriter(text,fieldnames=columns);writer.writeheader()
    for rr,label,key,data in sorted(reports,key=lambda x:(x[0],x[1])):
     if rr!=rid or not any((NAMES[rid],label,r) in eligible for r in RULES):continue
     baseline=seq_by_hash[data['commit']];t=timestamps[baseline];classes=collections.Counter(c['path'] for c in data['class_metrics'])
     findings={r['rule']:collections.Counter(f['path'] for f in r['findings']) for r in data['rules']}
     for inv in data['inventory']:
      path=inv['path'];match=db.execute('SELECT lineage,status FROM changes WHERE path=? AND seq<=? ORDER BY seq DESC LIMIT 1',(path,baseline)).fetchone()
      if match is None or match[1]=='D':raise ValueError('Baseline path not live: '+rid+' '+label+' '+path)
      lineage=match[0];hist=history(lineage)
      prior=[s for s,d in hist if s<=baseline and t-365*DAY<timestamps[s]<=t]
      future=[s for s,d in hist if s>baseline and t<timestamps[s]<=t+365*DAY]
      ordered=[s for s,d in hist if s>baseline and t<effective[s]<=t+365*DAY]
      dead=[s for s,d in hist if d and s>baseline and t<effective[s]<=t+365*DAY]
      deleted=event_rows[dead[0]-1][1] if dead else ''
      shift=effective[baseline]-t
      record={'repository':NAMES[rid],'snapshot':label,'baseline_commit':data['commit'],'baseline_path':path,'lineage':lineage,'baseline_timestamp':t,'file_ploc':inv['physical_lines'],'named_definitions':syntax_counts[key][path],'classes':classes[path],'prior365_raw_changes':len(prior),'following365_raw_changes':len(future),'following365_ancestry_clock_changes':len(ordered),'baseline_clock_shift_seconds':shift,'first_followup_deletion_commit':deleted,'lineage_status':'deletion_or_edited_move_unresolved' if dead else 'exact_moves_only_edited_moves_not_validated','confirmed_corrective_changes':'','scientifically_admitted':False}
      for rule in RULES:record[rule+'_findings']=findings[rule][path] if (NAMES[rid],label,rule) in eligible else ''
      writer.writerow(record);row_count+=1;clock_flags+=int(shift>0);deletions+=bool(dead)
 db.close();local.cleanup()
 summaries.append({'repository':rid,'file_baseline_rows':row_count,'baseline_clock_shift_rows':clock_flags,'followup_deletion_or_unresolved_move_rows':deletions,'sha256':hashlib.sha256(csv_path.read_bytes()).hexdigest(),'csv':csv_path.name,'interpretation':'Raw change activity only. No corrective outcomes, no association estimates. Ancestry clock is a diagnostic sensitivity, not a substituted primary time definition.'})
 print(rid,row_count,'file-baseline rows',flush=True)
(out/'manifest.json').write_text(json.dumps(summaries,indent=2)+'\n')

if a.calendar_correction:(out/'replacement-eligibility.json').write_text(json.dumps(replacement_eligibility,indent=2)+'\n')
