"""Resolve provenance questions without altering snapshots or fitting associations."""
import bisect,csv,datetime as dt,hashlib,html,json,re,sqlite3,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'analysis/maintenance_associations'
OUT=BASE/'results/linkage-audit';OUT.mkdir(exist_ok=True)
chronology=[]
for rid in ['odoo__odoo','jenkinsci__jenkins','apache__tomcat']:
 db=sqlite3.connect(f'file:{ROOT}/tmp/maintenance-associations/file-events/{rid}.sqlite?mode=ro',uri=True)
 events=list(db.execute('SELECT seq,commit_hash,timestamp FROM events ORDER BY seq'));db.close()
 idx={h:i for i,(s,h,t) in enumerate(events)};prefix=[];sources=[];maximum=-1;source=None
 for seq,h,t in events:
  if t>maximum:maximum=t;source=h
  prefix.append(maximum);sources.append(source)
 manifest=json.loads((ROOT/f'analysis/multilanguage_evolution/selection/histories/{rid}.json').read_text())
 for sample in manifest['observations']:
  label=sample['label']
  if not label.isdigit():continue
  year=int(label);boundary=dt.datetime(year+1,1,1,tzinfo=dt.timezone.utc).timestamp()
  i=idx[sample['commit']];t=events[i][2];safe=bisect.bisect_left(prefix,boundary)-1
  candidate=events[safe][1] if safe>=0 else None
  followup_end=t+365*86400;j=bisect.bisect_right(prefix,followup_end)
  reversal_count=sum(events[k][2]<events[k-1][2] for k in range(i+1,j))
  row={'repository':rid,'snapshot':label,'frozen_commit':sample['commit'],'frozen_commit_timestamp':t,'latest_ancestor_timestamp':prefix[i],'latest_ancestor_commit':sources[i],'baseline_clock_shift_seconds':prefix[i]-t,'year_boundary_utc':dt.datetime.fromtimestamp(boundary,dt.timezone.utc).isoformat(),'ancestor_dates_within_labelled_year':prefix[i]<boundary,'followup_internal_reversals':reversal_count,'calendar_frontier_candidate':candidate,'candidate_differs':candidate!=sample['commit'],'rescan_required_if_candidate_adopted':candidate!=sample['commit'],'candidate_is_historical_tip_proven':False}
  if prefix[i]>t:
   repo=ROOT/f'tmp/maintenance-associations/git/{rid}'
   row['commit_evidence']=[subprocess.check_output(['git','--git-dir',str(repo),'show','-s','--format=%H%n%aI%n%cI%n%P%n%s',h],text=True).strip() for h in [sample['commit'],sources[i]]]
  chronology.append(row)
(OUT/'chronology.json').write_text(json.dumps(chronology,indent=2)+'\n')
links=[]
for record in json.loads((BASE/'results/review-evidence/manifest.json').read_text()):
 rid=record['repository'];year=record['pilot_year'];commit=record['sample_commit'];timeline=[];evidence=[]
 for response in record['responses']:
  if response['kind']=='timeline' and response.get('http_status')==200:
   path=BASE/'results/review-evidence'/response['file'];timeline.extend(json.loads(path.read_text()));evidence.append({'path':str(path.relative_to(BASE)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
 merged=[e for e in timeline if e.get('event')=='merged' and e.get('commit_id')==commit]
 status='unresolved';integration_time=None;time_zone_verified=False
 if merged:status='explicit_github_merge_event';integration_time=merged[0]['created_at'];time_zone_verified=True
 bot=None
 if rid=='odoo__odoo':
  detail=next(x for x in record['responses'] if x['kind']=='detail');number=detail['url'].rsplit('/',1)[-1];path=OUT/f'odoo-{number}.html'
  text=path.read_text();plain=html.unescape(re.sub('<[^>]+>',' ',text));match=re.search(r'Merged\s+at\s+([0-9a-f]{40})',plain)
  if match and match.group(1)==commit:
   status='explicit_odoo_mergebot_commit';bot=commit
   date=re.search(r'title="merged at ([^"]+)"',text);integration_time=date.group(1) if date else None
  evidence.append({'path':str(path.relative_to(BASE)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
 history=json.loads((ROOT/f'analysis/multilanguage_evolution/selection/histories/{rid}.json').read_text())
 repo=ROOT/f'tmp/maintenance-associations/git/{rid}'
 subprocess.run(['git','--git-dir',str(repo),'merge-base','--is-ancestor',commit,history['endpoint']['commit']],check=True)
 links.append({'repository':rid,'pilot_year':year,'sample_commit':commit,'linkage_status':status,'mainline_ancestry_verified':True,'integration_timestamp_as_reported':integration_time,'integration_timestamp_timezone_verified':time_zone_verified,'github_merged_at':record['merged_at'],'github_closed_at':record['closed_at'],'current_merge_sha_matches_sample':record['sample_commit_equals_merge_commit'],'readiness_events':record['ready_for_review_events'],'evidence':evidence,'ready_to_merge_duration':None,'reason_duration_missing':'No explicit readiness event' if not record['ready_for_review_events'] else 'Merge-bot timestamp timezone requires verification; pilot is not a duration cohort','independent_corrective_label':None})
(OUT/'resolved-pr-links.json').write_text(json.dumps(links,indent=2)+'\n')
lines=['# Chronology and PR identity audit','','No detector counts, frozen snapshots or primary outcomes were changed. No associations were estimated.','','## Calendar integrity','', '| Repository | Annual snapshots inspected | Ancestor dates cross year boundary | Baseline date precedes an ancestor |','|---|---:|---:|---:|']
for rid in ['odoo__odoo','jenkinsci__jenkins','apache__tomcat']:
 rs=[r for r in chronology if r['repository']==rid];lines.append(f"| {rid} | {len(rs)} | {sum(not r['ancestor_dates_within_labelled_year'] for r in rs)} | {sum(r['baseline_clock_shift_seconds']>0 for r in rs)} |")
lines+=['','The Odoo 2018, 2019, 2020, 2023 and 2024 labelled snapshots contain ancestors with committer dates beyond their nominal year boundary. For example, the selected 2019 commit directly names a parent dated March 2020. Git records prove this metadata inconsistency; they do not establish its historical cause (rewriting, imports or erroneous dates require further evidence).','', 'Those existing points remain valid measurements of their specific source commits but are not established contemporaneous year-end observations. Calendar correlations using them are on hold. The existing thesis figure has not been silently replaced.','', 'The audit proposes conservative candidate commits whose entire first-parent ancestry has declared dates before the year boundary. These are candidate sampling repairs, not proven historical branch tips. Adopting them requires a dated protocol amendment, new source seals and new detector scans. It is invalid to carry the old counts onto new commits.','', 'Odoo 2015 also has a baseline-date reversal within its labelled year; the year boundary itself is not crossed. Follow-up windows anchored at actual commit time still need attention. Internal follow-up reversals are recorded for every case.','','## PR linkage','']
for r in links:lines.append(f"- {r['repository']} {r['pilot_year']}: {r['linkage_status']}.")
lines+=['','All five sampled mainline commits now have explicit project evidence linking them to their PRs. Jenkins 2014 is resolved by its historical merged timeline event even though the current PR detail field differs. The two Odoo merge-bot pages explicitly name the sampled commits; GitHub merged_at is null for both. GitHub closure is therefore not used as their integration time.','', 'Only the sampled Odoo 2024 PR has an explicit readiness event. Its merge-bot timestamp has no timezone in the archived field, so no duration is calculated. The earlier wording describing this as a uniformly GitHub-merged sample was inaccurate; it is a sample of PR references associated with integrated mainline changes.','', '## Remaining work','', 'Resolve or amend annual sampling before time-based inference, validate file lineage and corrective labels, and acquire an appropriately selected PR cohort if retaining the readiness-duration outcome. Successful identity linkage does not establish that a change was corrective or caused by an anti-pattern.']
(OUT/'AUDIT_REPORT.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines))
