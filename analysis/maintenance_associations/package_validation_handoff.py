"""Make a portable reviewer packet without the coordinator's detector predictions."""
import argparse,csv,hashlib,json,shutil,zipfile
from pathlib import Path
BASE=Path(__file__).resolve().parent;OUT=BASE/'results/validation-handoff-v0.5'
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=OUT);OUT=ap.parse_args().output
if (OUT/'reviewer-packet.zip').exists():raise FileExistsError('Preserve the previous handoff package')
manifest=json.loads((OUT/'manifest.json').read_text())
patches=BASE/'results/lineage-patch-evidence';records=json.loads((patches/'manifest.json').read_text())['records']
index=['# Lineage patch evidence','','Record decisions in `lineage-review.csv`. Read the patch before consulting automated linkage suggestions, which are deliberately omitted from this package. The complete source history may be necessary to resolve absorption or a move outside the bounded patch.','','| Repository | Lineage | Commit | Evidence |','|---|---:|---|---|']
for r in records:
 source=patches/r['directory'];dest=OUT/'lineage-evidence'/r['directory'];dest.mkdir(parents=True,exist_ok=True)
 for name in ['commit.txt','selected-paths.patch','whole-change.json','supplementary-channel-rename.patch']:
  if (source/name).exists():shutil.copyfile(source/name,dest/name)
 index.append(f"| {r['repository']} | {r['lineage']} | {r['event_commit'][:12]} | [metadata](lineage-evidence/{r['directory']}/commit.txt), [patch](lineage-evidence/{r['directory']}/selected-paths.patch) |")
(OUT/'LINEAGE_EVIDENCE.md').write_text('\n'.join(index)+'\n')
shutil.copyfile(BASE.parent/'multilanguage_evolution/detectors/SEMANTIC_RULES.md',OUT/'DETECTOR_RULES.md')
shutil.copyfile(BASE/'protocols/followup-observation-v0.4.md',OUT/'FOLLOWUP_RULES.md')
text='''# Independent review: start here

This packet supports validation of an observational maintenance study of Odoo, Jenkins and Apache Tomcat. The study uses three operational anti-pattern rules. No correlations have been estimated, and no independent labels have been supplied.

## What to review

| Worksheet | Cases | Task |
|---|---:|---|
| `detector-review.csv` | 203 | Assess whether the source unit satisfies the stated rule. The packet mixes reported findings and unflagged structural units. |
| `corrective-review.csv` | 90 | Assess whether the recorded change restores intended behaviour, using the patch and supporting issue or changelog evidence. |
| `lineage-review.csv` | 50 | Assess continuation, removal, repository extraction, absorption or production-scope exit. |

These are three separate pilot samples, not 343 independent projects or equivalent observations. Review may be divided between suitably qualified people. Record the actual reviewer for every decision. Retain disagreement records if more than one reviewer assesses a case; do not overwrite one person's labels with another's.

## How to return decisions

1. Extract the zip and copy the three CSV worksheets into a separate submission folder. Keep their filenames and frozen evidence columns unchanged. The coordinator retains the original blank templates.
2. Open the worksheets in a spreadsheet editor or CSV-aware editor. Save as UTF-8 CSV with the original column names. Keep commit hashes and case IDs as text.
3. Complete only the label, reviewer, evidence, rationale and (where present) linked-destination columns. Use a real reviewer identifier and a short evidence-based explanation. Uncertain and inaccessible cases are valid review results; guessing is not required.
4. Return the three CSV files to the study coordinator. Partial submissions may retain completely blank rows. Once a row is started, provide its label and supporting fields together. Do not modify the packet's source files or archived patches.

## Detector review

Use `DETECTOR_RULES.md`, not a general impression of whether code looks complex. Long Method is complexity greater than 10; length alone is insufficient. God Class requires all three metric conditions. Obsolete API Usage is restricted to resolved references to deprecations declared in the same source snapshot.

Read the source file named in `source_file` at the recorded line. `declaration_file` supplies local declaration context for relevant API cases. Frozen GitHub links provide a second access route. Files are stored by content hash, so the worksheet's original path identifies their role. Some decisions require other source files or binding context from the frozen revision; record uncertainty if the supplied context does not suffice.

Allowed values for `independent_rule_satisfied`: `yes`, `no`, `uncertain`. Supply `evidence`, `rationale` and `reviewer`. Rule satisfaction and whether repair would be desirable are separate questions. Do not treat an unflagged unit as a known negative. Detector predictions and calculated metrics are kept in a separate coordinator ledger, omitted from this zip.

The packet has no unflagged API-reference controls. It cannot establish missed APIs, parser omissions, complete file-control validity or cross-language semantic equivalence. A small stratified review must not be reported as precise population-wide precision or recall.

## Corrective-change review

Allowed `reviewer_label` values: `confirmed_corrective`, `confirmed_non_corrective`, `uncertain`, `inaccessible`. Supply `evidence_url`, `rationale` and `reviewer`. An archived local evidence reference is also acceptable in the evidence field. For inaccessible records, identify the attempted source and explain the access problem.

Use the immutable commit link, patch and relevant supporting records. The 'fix' keyword and Odoo's [FIX] prefix are candidate-selection aids, not ground truth. Refactoring, deletion, dependency updates and removal of detector findings are not automatically corrective. Missing issue evidence does not establish a negative. This packet includes links for corrective review, not a complete offline archive of every issue and patch.

## Lineage review

Use `LINEAGE_EVIDENCE.md` for local patches and commit records. Whole-change path/blob metadata are archived alongside each selected-path patch. The patch is bounded: lack of a displayed match does not establish removal. Search the whole frozen change when the basename changes, code splits or functionality is absorbed into an existing file.

Allowed `classification` values: `continuation`, `removal`, `repository_extraction`, `scope_exit`, `absorption`, `uncertain`, `inaccessible`. Supply `evidence`, `rationale` and `reviewer`. Supply `linked_destination` for continuation, extraction, scope exit or absorption; use a path, immutable URL or other precise identity. A commit's claim of external migration is not by itself verified destination identity. Use uncertainty when necessary.

`FOLLOWUP_RULES.md` explains why identity matters: continued production code stays tracked, verified exits are distinct from unresolved identity, and unknown follow-up is not a zero outcome. Reviewers provide evidence; they do not need to fit models or decide censoring assumptions.

## Independence and completion

The study protocol requires independent human assessment. Machine screening and this packet's preparation do not fulfil that requirement. Reviewer identity alone does not prove independence; the coordinator must document the review process. A completed worksheet can still contain uncertainty and cannot automatically admit the study for inference.

The coordinator can check a returned submission with:

```sh
python3 analysis/maintenance_associations/check_review_submission.py --submission /path/to/returned/csvs --output /path/to/new-review-check.json
```

The checker reports completeness and formatting/evidence-field problems. It does not assess whether a judgement is correct, estimate agreement or calculate correlations.
'''
(OUT/'START_HERE.md').write_text(text)
# Coordinator instructions and reviewer bundle deliberately exclude machine predictions.
(OUT/'coordinator/README.md').write_text('Keep the detector sampling ledger separate from initial reviewer assessment. It records predicted stratum, calculated evidence and inclusion probabilities. Reconcile returned judgments only after preserving the independent submission. Original positive examples from superseded Odoo commits are retained elsewhere but are not the current review sample. A completed submission does not verify independence or admit inference.\n')
files=[p for p in OUT.rglob('*') if p.is_file() and 'coordinator' not in p.relative_to(OUT).parts and p.name not in {'reviewer-packet.zip','REVIEWER_SHA256SUMS.json'}]
seals={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
(OUT/'REVIEWER_SHA256SUMS.json').write_text(json.dumps(seals,indent=2)+'\n');files.append(OUT/'REVIEWER_SHA256SUMS.json')
with zipfile.ZipFile(OUT/'reviewer-packet.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for p in sorted(files):
  info=zipfile.ZipInfo(str(p.relative_to(OUT)),date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,p.read_bytes())
print('Packaged',len(files),'files for independent review; prediction ledger excluded.')
