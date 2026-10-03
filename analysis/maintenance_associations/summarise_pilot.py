"""Create a human review sheet and coverage report, never inferred outcome labels."""
import csv,json
from pathlib import Path
BASE=Path(__file__).resolve().parent
p=BASE/'results/history-pilot'
sample=json.loads((p/'validation-sample.json').read_text())
http=json.loads((p/'public-evidence-probes.json').read_text())
acq=json.loads((p/'history-acquisition.json').read_text())
rows=list(csv.DictReader((p/'message-coverage.csv').open()))
with (p/'independent-review.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['repository','commit','commit_url','year','sampling_probability','message','changed_file_count','reviewer_label','evidence_url','rationale','reviewer'])
 w.writeheader()
 for x in sample:
  w.writerow({'repository':x['repository'],'commit':x['commit'],'commit_url':'https://github.com/'+x['repository'].replace('__','/')+'/commit/'+x['commit'],'year':x['year'],'sampling_probability':x['selection_probability'],'message':x['message'],'changed_file_count':len(x['changed_paths']),'reviewer_label':'','evidence_url':'','rationale':'','reviewer':''})
lines=['# Executed history and public-evidence pilot','','No association estimates or confirmed corrective labels have been produced. Message counts below measure candidate evidence availability, not bugs.','','## Acquisition','']
for x in acq:lines.append(f"- {x['repository']}: {x['mainline_events']:,} frozen-mainline events; {len(x['verified_snapshots'])} sampled commits verified; {x['timestamp_reversals']} adjacent timestamp reversals.")
lines+=['','The persistent clones retain full ancestry and trees with blob filtering. Source archives are checked separately against Git blob identities. Missing source blobs will require retrieval for patch review; clone completion does not imply all historical file contents are local.','','## Message evidence, 2007–2025','','| Repository | Events | Keyword candidates | Reference syntax |','|---|---:|---:|---:|']
for x in acq:
 r=[y for y in rows if y['repository']==x['repository']]
 nums=[sum(int(y[k]) for y in r) for k in ['mainline_events','keyword_candidates','events_with_reference_syntax']]
 lines.append('| '+x['repository']+' | '+' | '.join(f'{n:,}' for n in nums)+' |')
lines+=['','## Public endpoint pilot','',f'{len(http)} repository/year probe records; {sum(x.get("http_status")==200 for x in http)} successful HTTP responses. A successful response is not a validated link between a change and an issue. The pilot does not establish complete issue history or PR readiness-event coverage.','']
for x in http:lines.append(f"- {x['repository']} {x['year']}: {x.get('http_status',x.get('status',x.get('network_error')))}")
lines+=['','## Review required','',f'The seeded sample contains {len(sample)} changes across three repositories, three fixed years and two keyword strata. `independent-review.csv` deliberately omits keyword-stratum flags from reviewer-facing columns; messages still contain their original words. Label as confirmed corrective, confirmed non-corrective, uncertain or inaccessible, and record supporting evidence and rationale. The machine sample preserves stratum sizes and probabilities.','', 'This packet supports independent human classification; it is not an independently validated dataset. Method-level review duration requires PR-base scans and timeline acquisition; class co-change requires hunk and lineage validation; API migration requires symbol tracking. No missing outcome is encoded as zero.','', 'Tomcat supplemental XML probes returned login pages rather than issue records; HTTP success alone is insufficient. See ACQUISITION_NOTES.md and the archived Java pilot responses.', '', 'Next: complete independent detector/label validation and issue-link coverage assessment before estimating the planned associations. The pilot output may be used to amend acquisition choices before outcome modelling.']
(p/'PILOT_REPORT.md').write_text('\n'.join(lines)+'\n')
print('\n'.join(lines))
