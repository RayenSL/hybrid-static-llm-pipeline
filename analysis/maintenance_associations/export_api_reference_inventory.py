"""Instrument copies of frozen adapters; export API controls without altering findings."""
import argparse,hashlib,importlib.util,json,subprocess,sys,tarfile,tempfile
from pathlib import Path
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1];EV=ROOT/'analysis/multilanguage_evolution';DETECTORS=EV/'detectors'
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()+b'\n'
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def replace_once(source,old,new):
 if source.count(old)!=1:raise ValueError('Adapter instrumentation anchor changed')
 return source.replace(old,new)
def load_python(path,name):
 spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--runtime',type=Path,required=True);ap.add_argument('--output',type=Path,default=BASE/'results/api-reference-inventory-v0.6');a=ap.parse_args();out=a.output
 if out.exists():raise FileExistsError('Use a fresh evidence output directory')
 out.mkdir(parents=True);runtime=json.loads((a.runtime/'runtime-paths.json').read_text());sys.path.insert(0,runtime['parser_packages'])
 original_hashes=json.loads((BASE/'protocols/calendar-frontier-v0.2.json').read_text())['detector_inputs']
 for name in ['detectors/python/semantic.py','detectors/java/SemanticScan.java']:assert sha(EV/name)==original_hashes[name]
 generated=out/'instrumented-adapters';generated.mkdir()
 py=(DETECTORS/'python/semantic.py').read_text()
 py=replace_once(py,'source_references=set()','source_references=set();reference_inventory={}')
 anchor='                    source_references.add((path,target))'
 py=replace_once(py,anchor,anchor+"\n                    reference_inventory.setdefault((path,target),{'path':path,'line':x.lineno,'symbol':target,'declaration_path':symbols[target][1],'declaration_line':symbols[target][2].lineno})")
 py=replace_once(py,"'source_api_references':len(source_references),","'source_api_references':len(source_references),'reference_inventory':list(reference_inventory.values()),")
 (generated/'semantic.py').write_text(py)
 java=(DETECTORS/'java/SemanticScan.java').read_text()
 java=replace_once(java,'var sourceApiReferences=new TreeSet<String>();','var sourceApiReferences=new TreeSet<String>();var sourceReferenceInventory=new TreeMap<String,Object>();')
 anchor='        sourceApiReferences.add(path(u)+"|"+symbol(e));'
 java=replace_once(java,anchor,anchor+'\n        var declaration=trees.getPath(e);boolean fallback=declaration==null;if(fallback)declaration=trees.getPath(owner);String referenceKey=path(u)+"|"+symbol(e);if(!sourceReferenceInventory.containsKey(referenceKey)||(((Number)((Map<?,?>)sourceReferenceInventory.get(referenceKey)).get("line")).longValue()<1&&line(u,n)>=1))sourceReferenceInventory.put(referenceKey,obj("path",path(u),"line",line(u,n),"symbol",symbol(e),"declaration_path",path(declaration.getCompilationUnit()),"declaration_line",line(declaration.getCompilationUnit(),declaration.getLeaf()),"declaration_owner_fallback",fallback));')
 java=replace_once(java,'"source_api_references",sourceApiReferences.size(),','"source_api_references",sourceApiReferences.size(),"reference_inventory",sourceReferenceInventory.values(),')
 (generated/'SemanticScan.java').write_text(java)
 classes=a.runtime/'inventory-classes';classes.mkdir(exist_ok=True);java_exe=Path(runtime['java'])
 subprocess.run([str(java_exe.with_name('javac')),'-d',str(classes),str(generated/'SemanticScan.java')],check=True)
 original=load_python(DETECTORS/'python/semantic.py','original_semantic');instrumented=load_python(generated/'semantic.py','inventory_semantic')
 observations={};syntaxes={}
 with tarfile.open(EV/'results/three-rule-evidence.tar.gz') as tar:
  for m in tar:
   name=Path(m.name).name
   for suffix,store in [('.three-rules.json',observations),('.syntax.json',syntaxes)]:
    if name.endswith(suffix):
     key=name.removesuffix(suffix)
     if key.rsplit('-',1)[-1] in {'2014','2019','2024'}:store[key]=json.load(tar.extractfile(m))
 correction=BASE/'results/calendar-frontier-v0.2'
 for r in json.loads((correction/'manifest.json').read_text()):
  if r['snapshot'] not in {'2019','2024'}:continue
  key=r['repository']+'-'+r['snapshot'];p=correction/(key+'.three-rules.json');assert sha(p)==r['sha256'];observations[key]=json.loads(p.read_text());syntaxes[key]=json.loads((correction/(key+'.syntax.json')).read_text())
 records=[]
 for key,d in sorted(observations.items()):
  rid,year=key.rsplit('-',1);syntax=syntaxes[key];assert syntax['commit']==d['commit'];assert hashlib.sha256(canonical(syntax)).hexdigest()==d['syntax_report_sha256']
  archive=(ROOT/'tmp/maintenance-associations/calendar-frontier-v0.2-sources' if rid=='odoo__odoo' and year in {'2019','2024'} else ROOT/'tmp/multilanguage-evolution/annual-sources')/(key+'.tar')
  assert sha(archive)==d['archive_sha256'];inventory={f['path']:f for f in d['inventory']};sources={}
  with tarfile.open(archive) as tar:
   for path,info in inventory.items():
    value=tar.extractfile(tar.getmember(path)).read();assert hashlib.sha256(value).hexdigest()==info['sha256'];sources[path]=value
  print(key,'sealed source loaded',flush=True)
  if d['language']=='python':
   assert sys.version.split()[0]==d['tool']['runtime']
   complexity={(x['path'],x['span']['line_start']):x['metrics']['cyclomatic_complexity'] for x in syntax['definitions']}
   baseline=original.analyse(sources,complexity);extended=instrumented.analyse(sources,complexity)
  else:
   assert sha(java_exe)==d['tool']['java_executable_sha256']
   original_classes=Path(runtime['java_classes']);fingerprint=hashlib.sha256(canonical([(p.name,sha(p)) for p in sorted(original_classes.glob('SemanticScan*.class'))])).hexdigest();assert fingerprint==d['tool']['compiled_adapter_sha256']
   assert not d['tool']['classpath_configured']
   with tempfile.TemporaryDirectory(prefix='api-inventory-java-') as temp:
    root=Path(temp)/'source';root.mkdir()
    for path,value in sources.items():dest=root/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(value)
    outputs=[]
    for tag,cp in [('original',original_classes),('inventory',classes)]:
     dest=Path(temp)/(tag+'.json');subprocess.run([str(java_exe),'-Xmx2g','-cp',str(cp),'SemanticScan',str(root),str(dest),'',str(d['tool']['compiler_release'])],capture_output=True,check=True,timeout=600);outputs.append(json.loads(dest.read_text()))
    baseline,extended=outputs
   assert baseline['runtime']==d['tool']['runtime']
  references=extended.pop('reference_inventory');assert canonical(baseline)==canonical(extended),'Instrumentation changed original output'
  rule=next(r for r in d['rules'] if r['rule']=='ObsoleteApiUsage');assert rule['status']=='complete'
  assert len(references)==baseline['source_api_references']==rule['eligible_count']==rule['assessed_count']
  identity=lambda r:(r['path'],r['symbol'])
  assert len({identity(r) for r in references})==len(references)
  assert {identity(r) for r in baseline['obsolete']}=={identity(r) for r in rule['findings']}
  oldhits={identity(r):r for r in rule['findings']}
  for r in baseline['obsolete']:
   old=oldhits[identity(r)]
   for k in ['path','line','symbol','declaration_path','deprecation_origin']:assert r[k]==old[k]
  assert len(oldhits)==rule['finding_count'];assert set(oldhits)<={identity(r) for r in references}
  for r in references:
   assert r['path'] in inventory and r['declaration_path'] in inventory
   r['source_location_available']=1<=r['line']<=inventory[r['path']]['physical_lines']
   if not r['source_location_available']:r['reported_line']=r['line'];r['line']=None
   r['declaration_location_available']=1<=r['declaration_line']<=inventory[r['declaration_path']]['physical_lines']
   if not r['declaration_location_available']:r['reported_declaration_line']=r['declaration_line'];r['declaration_line']=None
   r['detector_flagged']=identity(r) in oldhits;r['source_sha256']=inventory[r['path']]['sha256'];r['declaration_source_sha256']=inventory[r['declaration_path']]['sha256']
  references.sort(key=identity)
  result={'schema_version':'maintenance.api-reference-inventory/0.1','admitted':False,'repository':rid,'year':year,'commit':d['commit'],'archive_sha256':d['archive_sha256'],'scope_sha256':d['scope_sha256'],'original_adapter_sha256':d['adapter_sha256'],'original_raw_output_sha256':hashlib.sha256(canonical(baseline)).hexdigest(),'original_output_unchanged':True,'frozen_api_findings_reconciled':True,'eligible_count':len(references),'flagged_count':len(oldhits),'unflagged_count':len(references)-len(oldhits),'references':references,'limitations':['Resolved source APIs only; unresolved and external references are outside this population.','Unflagged is a detector decision, not independently validated absence of deprecation.','One representative reference per source-file/API pair; its line need not be the deprecated occurrence when the same pair is used in multiple contexts.']}
  dest=out/(key+'.json');dest.write_bytes(canonical(result));records.append({k:result[k] for k in ['repository','year','commit','eligible_count','flagged_count','unflagged_count','original_output_unchanged','frozen_api_findings_reconciled']}|{'file':dest.name,'sha256':sha(dest)})
  (out/'manifest.json').write_bytes(canonical(records));print(key,len(references),'resolved pairs;',len(oldhits),'flagged; original output unchanged',flush=True)
 (out/'instrumentation-seals.json').write_bytes(canonical({'original_inputs':{name:sha(EV/name) for name in ['detectors/python/semantic.py','detectors/java/SemanticScan.java']},'instrumented':{p.name:sha(p) for p in generated.iterdir() if p.is_file()},'java_executable_sha256':sha(java_exe),'python':sys.version}))
if __name__=='__main__':main()
