"""Archive sampled PR details and paginated timeline evidence; no effort estimates."""
import datetime as dt,hashlib,json,time,urllib.request,urllib.error
from pathlib import Path
BASE=Path(__file__).resolve().parent
source=BASE/'results/history-pilot/public-evidence-probes.json'
out=BASE/'results/review-evidence';out.mkdir(exist_ok=True)
records=[]
for probe in json.loads(source.read_text()):
 if not probe.get('is_pull_request') or probe.get('http_status')!=200:continue
 api=probe['url'];prefix=probe['repository']+'-'+str(probe['year']);responses=[];detail=None;timeline=[]
 urls=[('detail',api.replace('/issues/','/pulls/')),('timeline',api+'/timeline?per_page=100')]
 for kind,initial in urls:
  url=initial;page=0
  while url and page<10:
   page+=1;r={'kind':kind,'url':url,'retrieved_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
   try:
    req=urllib.request.Request(url,headers={'User-Agent':'maintenance-association-research','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req,timeout=30) as response:
     body=response.read();r['http_status']=response.status;links=response.headers.get('Link','');r['link']=links;r['rate_limit_remaining']=response.headers.get('X-RateLimit-Remaining')
   except urllib.error.HTTPError as ex:body=ex.read();r['http_status']=ex.code;links=''
   except OSError as ex:r['network_error']=str(ex);responses.append(r);break
   name=f'{prefix}-{kind}-{page}.json';(out/name).write_bytes(body);r['file']=name;r['sha256']=hashlib.sha256(body).hexdigest();responses.append(r)
   if r['http_status']!=200:break
   data=json.loads(body)
   if kind=='detail':detail=data
   else:timeline.extend(data)
   url=None
   for link in links.split(','):
    if 'rel="next"' in link:url=link.split('<',1)[1].split('>',1)[0]
   if page==10 and url:r['pagination_truncated']=True
  if responses and responses[-1].get('http_status') in [403,429]:break
 record={'repository':probe['repository'],'pilot_year':probe['year'],'sample_commit':probe['commit'],'responses':responses,'timeline_pages_complete':bool([r for r in responses if r['kind']=='timeline']) and all(r.get('http_status')==200 and not r.get('pagination_truncated') for r in responses if r['kind']=='timeline'),'draft_classification':'not_assessed','independent_validation':False}
 if detail:
  record.update({'base_sha':detail['base']['sha'],'head_sha':detail['head']['sha'],'merge_commit_sha':detail.get('merge_commit_sha'),'sample_commit_equals_merge_commit':detail.get('merge_commit_sha')==probe['commit'],'created_at':detail['created_at'],'merged_at':detail.get('merged_at'),'closed_at':detail.get('closed_at'),'current_draft':detail.get('draft'),'changed_files':detail.get('changed_files'),'additions':detail.get('additions'),'deletions':detail.get('deletions')})
  record['base_revision_warning']='API base SHA is captured as returned; readiness-time base identity and historical exposure require validation.'
 record['ready_for_review_events']=[{'created_at':e.get('created_at'),'event':e.get('event')} for e in timeline if e.get('event') in ['ready_for_review','convert_to_draft']]
 record['review_events']=[{'submitted_at':e.get('submitted_at'),'state':e.get('state')} for e in timeline if e.get('event')=='reviewed']
 record['duration_warning']='No readiness transition is not proof of readiness at creation; this merged-PR pilot is not a duration-analysis cohort.'
 records.append(record);print(prefix,'detail',bool(detail),'timeline events',len(timeline),flush=True)
(out/'manifest.json').write_text(json.dumps(records,indent=2)+'\n')
