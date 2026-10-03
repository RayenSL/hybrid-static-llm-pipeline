"""Sample unflagged resolved API pairs; preserve the earlier review handoff."""
import argparse,csv,zipfile,hashlib,json,random,tarfile
from pathlib import Path
from urllib.parse import quote
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--inventory',type=Path,default=BASE/'results/api-reference-inventory-v0.6');ap.add_argument('--output',type=Path,default=BASE/'results/api-control-review-v0.6');a=ap.parse_args();OUT=a.output
if OUT.exists():raise FileExistsError('Use a fresh review directory')
records=json.loads((a.inventory/'manifest.json').read_text());assert len(records)==9
OUT.mkdir(parents=True);(OUT/'sources').mkdir();cases=[];strata=[];summaries=[]
for record in records:
 p=a.inventory/record['file'];assert hashlib.sha256(p.read_bytes()).hexdigest()==record['sha256'];d=json.loads(p.read_text());rid=d['repository'];year=d['year']
 population=[r for r in d['references'] if not r['detector_flagged']];assert len(population)==d['unflagged_count']
 n=min(5,len(population));seed=f'20260922:api-unflagged:{rid}:{year}';selected=random.Random(seed).sample(population,n)
 strata.append({'repository':rid,'year':year,'commit':d['commit'],'population':len(population),'sample_size':n,'selection_probability':n/len(population) if population else None,'seed':seed})
 summaries.append({'repository':rid,'year':year,'eligible_pairs':d['eligible_count'],'flagged_pairs':d['flagged_count'],'unflagged_pairs':d['unflagged_count'],'pairs_without_source_line':sum(not r['source_location_available'] for r in d['references']),'sample_size':n,'sampled_pairs_without_source_line':sum(not r['source_location_available'] for r in selected)})
 archive=(ROOT/'tmp/maintenance-associations/calendar-frontier-v0.2-sources' if rid=='odoo__odoo' and year in {'2019','2024'} else ROOT/'tmp/multilanguage-evolution/annual-sources')/(rid+'-'+year+'.tar')
 with archive.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==d['archive_sha256']
 with tarfile.open(archive) as tar:
  for r in selected:
   identity=[rid,year,d['commit'],r['path'],r['symbol']];case=hashlib.sha256(json.dumps(identity,separators=(',',':')).encode()).hexdigest()[:16]
   paths={}
   for field,hashfield in [('path','source_sha256'),('declaration_path','declaration_source_sha256')]:
    raw=tar.extractfile(tar.getmember(r[field])).read();assert hashlib.sha256(raw).hexdigest()==r[hashfield];filename=r[hashfield]+Path(r[field]).suffix;dest=OUT/'sources'/filename
    if dest.exists():assert dest.read_bytes()==raw
    else:dest.write_bytes(raw)
    paths[field]='sources/'+filename
   cases.append({'case_id':case,'repository':rid,'year':year,'commit':d['commit'],'rule':'ObsoleteApiUsage','path':r['path'],'line':r['line'] if r['source_location_available'] else '', 'symbol':r['symbol'],'source_location_available':r['source_location_available'],'declaration_path':r['declaration_path'],'declaration_line':r['declaration_line'] if r['declaration_location_available'] else '', 'declaration_owner_fallback':r.get('declaration_owner_fallback',False),'source_file':paths['path'],'declaration_file':paths['declaration_path'],'source_url':'https://github.com/'+rid.replace('__','/')+'/blob/'+d['commit']+'/'+quote(r['path'])+('#L'+str(r['line']) if r['source_location_available'] else ''),'stratum_size':len(population),'selection_probability':n/len(population),'independent_rule_satisfied':'','evidence':'','rationale':'','reviewer':''})
assert len({r['case_id'] for r in cases})==len(cases)
with (OUT/'api-reference-review.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(cases[0]));w.writeheader();w.writerows(cases)
(OUT/'sampling.json').write_text(json.dumps({'strata':strata,'sample_cases':len(cases),'sampling_frame':'Detector-resolved source-file/API pairs unflagged by the frozen rule; not confirmed negatives.','independent_labels_completed':False},indent=2)+'\n')
(OUT/'coverage.json').write_text(json.dumps(summaries,indent=2)+'\n')
lines=['# Unflagged source-API review supplement','','This supplement addresses the missing API-reference control sample. It leaves the previous 203-case detector worksheet and the corrective/lineage worksheets unchanged. All independent labels remain blank.','','| Repository | Year | Resolved pairs | Flagged pairs | Unflagged pairs | Pairs without a source line | Sample |','|---|---:|---:|---:|---:|---:|---:|']
for r in summaries:lines.append('| '+r['repository']+' | '+r['year']+' | '+' | '.join(str(r[k]) for k in ['eligible_pairs','flagged_pairs','unflagged_pairs','pairs_without_source_line','sample_size'])+' |')
lines+=['','## Evidence checks','','Original adapter sources were left unchanged. For every snapshot, removing the new reference-inventory field from the instrumented output yields exactly the original raw output. The resolved-pair totals and every original API finding reconcile to the frozen result, including finding lines, declaration paths and deprecation origins. The pinned runtime and sealed production-source archives were reused. These checks establish preservation of detector behaviour, not empirical correctness.','','## Reviewer instructions','','Open `api-reference-review.csv` and assess whether each source-file/API pair satisfies the frozen source-declared Obsolete API Usage rule. Use the recorded commit, source and declaration files, and any additional context needed from that revision. Record `yes`, `no` or `uncertain` in `independent_rule_satisfied`, with evidence, rationale and a reviewer identifier. Assess source deprecation and reference binding; do not apply current external-library or platform deprecations retrospectively. Do not fill a negative label solely because this is the unflagged sample.','', 'A blank line means the compiler supplied no valid source position, not a missing file. Where `declaration_owner_fallback` is true, the declaration file and line provide owning-type context for an implicit member. These cases may require uncertainty rather than a forced label. Whole source files are included; one representative location does not list every occurrence of a pair.','', 'The sample contains up to five pairs per repository and year, selected uniformly without replacement with recorded fixed seeds and probabilities. It does not cover unresolved bindings, external APIs or references missed by the detector. Together with the previous positive sample it supports a small operational-rule validation pilot, not a precise population-wide recall claim or automatic validation of file-level controls.','','## Reproduction','','Restore the pinned semantic runtime, export the inventories, then prepare a fresh supplement:','','```sh','python3 analysis/multilanguage_evolution/prepare_semantic_runtime.py --root /tmp/api-reference-runtime','python3 analysis/maintenance_associations/export_api_reference_inventory.py --runtime /tmp/api-reference-runtime','python3 analysis/maintenance_associations/prepare_api_control_review.py','```','','Both study scripts require fresh output directories. Pass `--output` for a new export and `--inventory` plus `--output` for its corresponding review supplement. Independent review and the other study admission gates remain pending.']
(OUT/'REPORT.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines))

# Portable supplement: fixed timestamps and file order keep packaging reproducible.
files=[p for p in OUT.rglob('*') if p.is_file()]
seals={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
(OUT/'REVIEWER_SHA256SUMS.json').write_text(json.dumps(seals,indent=2)+'\n');files.append(OUT/'REVIEWER_SHA256SUMS.json')
with zipfile.ZipFile(OUT/'api-review-supplement.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for p in sorted(files):
  info=zipfile.ZipInfo(str(p.relative_to(OUT)),date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,p.read_bytes())
