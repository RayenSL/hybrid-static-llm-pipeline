"""Publish coverage and diagnostic counts without promoting partial measurements."""
import argparse,collections,csv,gzip,hashlib,io,json,shutil,sys,tarfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'ingest'))
from validate_multi_rule import validate,canonical
CASES={'odoo__odoo':'Odoo','jenkinsci__jenkins':'Jenkins','apache__tomcat':'Apache Tomcat'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--results',type=Path,required=True);ap.add_argument('--output',type=Path,default=HERE/'results');ap.add_argument('--bundle',action='store_true');a=ap.parse_args();a.output.mkdir(exist_ok=True,parents=True)
    rows=[];evidence=[];rawfiles=[]
    for repo,title in CASES.items():
        history=json.loads((HERE/'selection/histories'/f'{repo}.json').read_text());manifest=json.loads((a.results/(repo+'-manifest.json')).read_text());by_label={x['label']:x for x in manifest}
        if len(manifest)!=len(history['observations']):raise ValueError('Incomplete campaign: '+repo)
        rawfiles.append(a.results/(repo+'-manifest.json'))
        for obs in history['observations']:
            m=by_label[obs['label']];p=a.results/m['file'];d=json.loads(p.read_text());validate(d)
            if m['sha256']!=sha(p) or m['commit']!=obs['commit'] or d['commit']!=obs['commit']:raise ValueError('Snapshot or result seal mismatch')
            if m.get('syntax_replay_identical') is not True or m.get('semantic_replay_identical') is not True:raise ValueError('Unreplayed result')
            base=repo+'-'+obs['label'];syntax=a.results/(base+'.syntax.json');scope=a.results/(base+'.scope.json')
            if sha(syntax)!=d['syntax_report_sha256'] or sha(scope)!=d['scope_sha256']:raise ValueError('Companion evidence mismatch')
            rawfiles.extend([p,syntax,scope])
            for rule in d['rules']:
                rows.append({'repository':title,'language':d['language'],'snapshot':obs['label'],'year':int(obs['label'][-4:]),'commit':obs['commit'],'actual_commit_date':obs['committer_date'],'rule':rule['rule'],'status':rule['status'],'primary_count':rule['finding_count'],'observed_count':rule['observed_finding_count'],'unverified_candidates':len(rule['candidates']),'unit':rule['unit'],'eligible_count':rule['eligible_count'],'assessed_count':rule['assessed_count'],'eligible_files':len(d['inventory']),'tracked_files_in_analysed_language':obs['inventory']['tracked_language_files'].get(d['language'],0),'tracked_other_recognised_language_files':sum(v for k,v in obs['inventory']['tracked_language_files'].items() if k not in {d['language'],'other'}),'physical_lines':sum(x['physical_lines'] for x in d['inventory']),'result_sha256':m['sha256'],'scope_sha256':d['scope_sha256'],'archive_sha256':d['archive_sha256'],'admitted':False,'limitations':' | '.join(rule['limitations'])})
            evidence.append({'repository':repo,'snapshot':obs['label'],'commit':obs['commit'],'result_sha256':m['sha256'],'adapter_sha256':d['adapter_sha256'],'syntax_report_sha256':d['syntax_report_sha256'],'tool':d['tool'],'syntax_replay_identical':True,'semantic_replay_identical':True,'semantic_error_codes':dict(collections.Counter(x.get('code',x.get('reason','unknown')) for x in d['semantic_diagnostics']))})
    csvpath=a.output/'three-rule-annual-coverage.csv'
    with csvpath.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    (a.output/'three-rule-replay-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    table=[]
    for title in CASES.values():
        counts=[]
        for rule in ['LongMethod','GodClass','ObsoleteApiUsage']:
            rr=[r for r in rows if r['repository']==title and r['rule']==rule]
            counts.append(f"{sum(r['status']=='complete' for r in rr)}/{len(rr)}")
        table.append('| '+title+' | '+' | '.join(counts)+' |')
    lines=[
        '# Three-rule annual detector campaign','',
        '**Experimental results: scientific admission remains pending.**','',
        'The campaign ran all three detector modules on 21 frozen snapshots of each repository (63 snapshots; 189 rule observations). Each syntax and semantic scan was recomputed and compared byte for byte. This establishes repeatability from the same sealed source archives, not independent Git acquisition or independent detector validation.','',
        '## Complete rule observations','',
        '| Repository | Long Method | God Class | Source-declared obsolete API usage |',
        '|---|---:|---:|---:|',*table,'',
        'Complete means that the declared static-analysis model covered the reviewed source population. It does not imply perfect runtime binding or scientific admission. Partial and unavailable observations retain an empty primary_count and must remain missing in plots.','',
        '## Fixed 2026 endpoint','',
        '| Repository | Long Method | God Class | Source-declared obsolete API usage |',
        '|---|---:|---:|---:|'
    ]
    for title in CASES.values():
        rr={r['rule']:r for r in rows if r['repository']==title and r['snapshot']=='endpoint-2026'}
        def value(rule):
            row=rr[rule]
            return str(row['primary_count']) if row['status']=='complete' else 'missing'
        lines.append('| '+title+' | '+' | '.join(value(k) for k in ['LongMethod','GodClass','ObsoleteApiUsage'])+' |')
    lines += [
        '',
        'God Class counts use class declarations as their denominator. Long Method counts use named definitions with bodies. Source-declared obsolete API counts use distinct `(source file, source API)` pairs resolved inside the analysed revision; third-party library and platform deprecations are outside this population.','',
        '## Scope and validity','',
        'Odoo is analysed in Python; Jenkins and Tomcat are analysed in Java. Other implementation languages are outside these adapters. The CSV includes production-source physical lines and tracked language-file counts as size and scope indicators. Tomcat’s explicit JavaCC-generated parser files are excluded, while JJTree-only node skeletons that may contain maintained logic are retained.','',
        'God Class retains the conjunction ATFD > 4, WMC ≥ 47 and TCC < 1/3. The language adapters follow the existing Roslyn detector’s best-effort semantic model: resolved source-owned attributes contribute to the metrics, while unresolved bindings are skipped and disclosed in diagnostic fields. Historical Python 2 syntax is converted with a restricted syntax-only, line-preserving compatibility pass.','',
        'Obsolete API Usage detects references to deprecations declared in the same source revision. Java uses compiler deprecation metadata; Python recognises resolved PEP 702 decorators and direct unconditional `warnings.warn(..., DeprecationWarning)` statements. This avoids retrospectively applying current dependency metadata to old snapshots. A future external-dependency analysis requires versioned historical catalogues and is a separate population.','',
        'Tomcat’s 2021 and 2022 God Class and obsolete-API observations are missing because an optional module requires a different Java language level from the root profile. The other observations are not interpolated across these gaps.','',
        '## Consequence for the thesis','',
        'The campaign now provides descriptive trajectories for the declared operational definitions, within the agreed maximum of two gaps per case. The outputs remain `admitted: false`: independent detector validation, current application build or smoke checks, and final repository-scope review are still required before the trajectories are used as thesis evidence.','',
        '## Evidence','',
        '`three-rule-annual-coverage.csv` contains every rule observation and denominator. `three-rule-replay-evidence.json` records result hashes, compiler profiles and diagnostics. The compressed evidence bundle retains raw findings, class metrics, syntax inventories, scopes, source seals and detector code. No target application source was executed by the campaign.'
    ]
    (a.output/'THREE_RULE_ANALYSIS.md').write_text('\n'.join(lines)+'\n')
    if a.bundle:
        archive=a.results/'three-rule-evidence.tar.gz'
        code=[p for directory in ['detectors','contracts','ingest','protocols','tests'] for p in (HERE/directory).rglob('*') if p.is_file() and p.suffix in {'.py','.java','.json','.txt','.md'}]
        code.extend(HERE/name for name in ['README.md','run_three_rules.py','prepare_linux_runtime.py','prepare_semantic_runtime.py','audit_history.py','export_sources.py','publish_three_rules.py','plot_rule_coverage.py','plot_three_rule_trajectories.py','assemble_three_rule_campaign.py'])
        code.extend(HERE/'selection/histories'/name for repo in CASES for name in [repo+'.json',repo+'.history.json.gz'])
        with archive.open('wb') as f,gzip.GzipFile(filename='',fileobj=f,mode='wb',mtime=0) as gz,tarfile.open(fileobj=gz,mode='w|') as tar:
            for p,name in [(p,'raw/'+p.name) for p in sorted(rawfiles)]+[(p,'code/'+str(p.relative_to(HERE))) for p in sorted(code)]:
                data=p.read_bytes();info=tarfile.TarInfo(name);info.size=len(data);info.mtime=0;info.mode=0o644;tar.addfile(info,io.BytesIO(data))
        dest=a.output/archive.name
        if shutil.disk_usage(a.output).free<archive.stat().st_size+10*1024*1024:raise OSError('Not enough workspace space for the evidence bundle; preserved at '+str(archive))
        shutil.copyfile(archive,dest)
        (a.output/'three-rule-bundle-manifest.json').write_text(json.dumps({'file':dest.name,'sha256':sha(dest),'bytes':dest.stat().st_size,'raw_files':len(rawfiles),'code_files':len(code)},indent=2)+'\n')
    print('Published',len(rows),'rule observations',flush=True)
if __name__=='__main__':main()
