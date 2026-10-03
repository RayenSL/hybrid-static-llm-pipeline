"""Three-rule adapter envelope. Partial observations never become primary zeroes."""
import argparse,hashlib,importlib.util,json,subprocess,tarfile,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
RULES=('LongMethod','GodClass','ObsoleteApiUsage')
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()+b'\n'
def sha(data):return hashlib.sha256(data).hexdigest()
def finding(rule,row,sources,metrics):
    identity=[rule,row['path'],row['line'],row['symbol']]
    return {'id':sha(canonical(identity)),'rule':rule,'path':row['path'],'line':row['line'],'symbol':row['symbol'],'source_sha256':sha(sources[row['path']]),'metrics':metrics}
def finish(rule,unit,eligible,assessed,hits,reasons,candidates=None):
    status='partial' if reasons else 'complete'
    if eligible is None and not assessed and not hits:status='unavailable'
    return {'rule':rule,'status':status,'unit':unit,'eligible_count':eligible,'assessed_count':assessed,'finding_count':len(hits) if status=='complete' else None,'observed_finding_count':len(hits),'findings':hits,'candidates':candidates or [],'limitations':reasons}
def run(archive,syntax,java=None,java_classes=None,classpath='',java_profile=None):
    spec=importlib.util.spec_from_file_location('syntax_validator',HERE.parent/'ingest/validate.py');validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator);validator.validate(syntax)
    if syntax['archive_sha256']!=sha(archive.read_bytes()):raise ValueError('Archive hash mismatch')
    expected=sha((HERE/'syntax_probe.py').read_bytes()+((HERE/'legacy_python.py').read_bytes() if syntax['scope'].get('python_parser') in {'legacy','legacy3'} else b''))
    if syntax['tool']['adapter_sha256']!=expected:raise ValueError('Stale syntax detector output; regenerate with current adapter')
    if syntax['scope_sha256']!=sha(canonical(syntax['scope'])):raise ValueError('Scope hash mismatch')
    sources={}
    with tarfile.open(archive) as t:
        for item in syntax['inventory']:
            path=item['path'];p=Path(path)
            if p.is_absolute() or '..' in p.parts or '\\' in path or ':' in path:raise ValueError('Unsafe source path')
            m=t.getmember(path)
            if not m.isfile():raise ValueError('Expected a regular source member')
            data=t.extractfile(m).read()
            if sha(data)!=item['sha256']:raise ValueError('Source seal mismatch')
            sources[path]=data
    complete=syntax['status']['syntax']=='complete';lang=syntax['language'];rules=[]
    hits=[]
    for d in syntax['definitions']:
        if d['metrics']['cyclomatic_complexity']>10:
            row={'path':d['path'],'line':d['span']['line_start'],'symbol':d['symbol']}
            f=finding('LongMethod',row,sources,{'CC':d['metrics']['cyclomatic_complexity'],'physical_lines':d['metrics']['physical_lines']})
            f['severity']='critical' if d['metrics']['physical_lines']>50 else 'warning';hits.append(f)
    rules.append(finish('LongMethod','named definitions with bodies',len(syntax['definitions']) if complete else None,len(syntax['definitions']),hits,[] if complete else ['Incomplete syntax coverage; counts are diagnostic.']))
    if lang=='python':
        spec=importlib.util.spec_from_file_location('python_semantic',HERE/'python/semantic.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        complexities={(d['path'],d['span']['line_start']):d['metrics']['cyclomatic_complexity'] for d in syntax['definitions']}
        raw=mod.analyse(sources,complexities);semantic_ok=not raw['diagnostics'];compiler={'engine':'CPython AST with conservative source bindings','runtime':__import__('sys').version.split()[0]}
    elif lang=='java':
        if java_profile and java_profile['commit']!=syntax['commit']:raise ValueError('Java release profile commit mismatch')
        release=(java_profile or {}).get('compiler_release') or 21
        if not java or not java_classes:raise ValueError('Java requires a compiled SemanticScan and pinned JDK')
        with tempfile.TemporaryDirectory(prefix='evolution-java-') as temp:
            temp=Path(temp);root=temp/'source';root.mkdir()
            for path,data in sources.items():dest=root/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
            output=temp/'semantic.json'
            proc=subprocess.run([str(java),'-Xmx2g','-cp',str(java_classes),'SemanticScan',str(root),str(output),classpath,str(release)],capture_output=True,text=True,timeout=600)
            if proc.returncode:raise RuntimeError('Java semantic scan failed: '+proc.stderr[-2000:])
            raw=json.loads(output.read_text());semantic_ok=raw['semantic_errors']==0 and raw['parse_errors']==0
            compiler={'engine':'javac attribution, annotation processing disabled','runtime':raw['runtime'],'classpath_configured':bool(classpath),'compiler_release':release,'release_profile_sha256':sha(canonical(java_profile)) if java_profile else None,'compiled_adapter_sha256':sha(canonical([(p.name,sha(p.read_bytes())) for p in sorted(java_classes.glob('SemanticScan*.class'))])),'java_executable_sha256':sha(java.read_bytes())}
            if classpath:
                import os
                entries=[]
                for index,entry in enumerate(classpath.split(os.pathsep)):
                    base=Path(entry)
                    if '*' in entry:raise ValueError('Classpath wildcards must be expanded explicitly for sealing')
                    if not base.exists():raise FileNotFoundError(base)
                    for p in sorted(base.rglob('*')) if base.is_dir() else [base]:
                        if p.is_file():entries.append([index,str(p.relative_to(base)) if base.is_dir() else p.name,sha(p.read_bytes())])
                compiler['classpath_sha256']=sha(canonical(entries))
    else:raise ValueError('Only Python and Java are implemented for this suite')
    gc_syntax_ok=(raw['parse_errors']==0) if lang=='java' else not raw['diagnostics']
    gc=[];candidates=[];assessed=0;records=[]
    for c in raw['classes']:
        # Match the existing Roslyn detector's best-effort semantics: unresolved
        # bindings are skipped by the metric walk and reported as diagnostics, but
        # do not invalidate otherwise parsed class metrics.
        resolved=gc_syntax_ok and c.get('wmc_complete',True)
        metrics={'ATFD':c['atfd'],'WMC':c['wmc'],'TCC':c['tcc'],'public_methods':c['public_methods']}
        trigger=c['atfd']>4 and c['wmc']>=47 and c['tcc']<1/3
        # WMC alone can disprove this conjunction without pretending ATFD/TCC are resolved.
        decisive=gc_syntax_ok and (resolved or (c.get('wmc_complete',True) and c['wmc']<47))
        assessed+=int(decisive)
        records.append({**c,'assessment':'resolved' if resolved else 'negative_by_WMC' if decisive else 'unresolved'})
        if trigger:
            f=finding('GodClass',c,sources,metrics)
            (gc if resolved and gc_syntax_ok else candidates).append(f)
    reasons=[]
    if not gc_syntax_ok:reasons.append('Source parsing is incomplete for this semantic adapter.')
    if assessed<len(raw['classes']):reasons.append('Some class declarations lack a complete WMC measurement.')
    rules.append(finish('GodClass','class declarations',len(raw['classes']) if gc_syntax_ok else None,assessed,gc,reasons,candidates))
    api=[]
    for ref in raw['obsolete']:
        f=finding('ObsoleteApiUsage',ref,sources,{});f['declaration_path']=ref['declaration_path'];f['deprecation_origin']=ref['deprecation_origin'];api.append(f)
    api_reasons=[]
    if not gc_syntax_ok:api_reasons.append('Source parsing is incomplete for this semantic adapter.')
    eligible=raw.get('source_api_references') if not api_reasons else None
    rules.append(finish('ObsoleteApiUsage','distinct (source file, source-declared deprecated API) pairs',eligible,eligible or 0,api,api_reasons))
    return {'schema_version':'evolution.multi-rule/0.2','admitted':False,'repository':syntax['repository'],'commit':syntax['commit'],'language':lang,'archive_sha256':syntax['archive_sha256'],'scope_sha256':syntax['scope_sha256'],'scope':syntax['scope'],'syntax_report_sha256':sha(canonical(syntax)),'tool':compiler,'adapter_sha256':sha(b''.join(p.read_bytes() for p in [Path(__file__),HERE/'python/semantic.py',HERE/'java/SemanticScan.java'])),'inventory':syntax['inventory'],'rules':rules,'class_metrics':records,'semantic_diagnostics':raw['diagnostics'],'semantic_coverage':{k:raw[k] for k in ['parse_errors','semantic_errors','unresolved_references','source_api_references','declarations','deprecation_markers','parse_modes'] if k in raw},'limitations':['Experimental language mappings; no claim of identical .NET semantics.',"God Class follows the existing detector's best-effort binding model; unresolved symbols are skipped and disclosed.",'Obsolete API Usage is scoped to deprecations declared in the analysed revision; historical external dependencies are outside the primary measurement.','No primary zero or prevalence for incomplete rules.','Target source is never executed; current build/runtime feasibility is separate.']}
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--archive',type=Path,required=True);ap.add_argument('--syntax-report',type=Path,required=True);ap.add_argument('--java',type=Path);ap.add_argument('--java-classes',type=Path);ap.add_argument('--classpath',default='');ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    d=run(a.archive,json.loads(a.syntax_report.read_text()),a.java,a.java_classes,a.classpath);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical(d));print(json.dumps({r['rule']:{'status':r['status'],'observed':r['observed_finding_count']} for r in d['rules']}))
