"""Experimental syntax coverage/complexity adapter. Outputs are not thesis-admitted.

No source is executed. Native preprocessing and semantic resolution are not performed.
"""
import argparse, collections, hashlib, importlib, importlib.metadata, json, sys, tarfile
from pathlib import Path, PurePosixPath
from tree_sitter import Language, Parser
EXTENSIONS={'python':{'.py'},'java':{'.java'},'c':{'.c','.h'},'cpp':{'.cpp','.cc','.cxx','.hpp','.hh','.hxx'}}
DEFINITIONS={'python':{'function_definition'},'java':{'method_declaration','constructor_declaration'},'c':{'function_definition'},'cpp':{'function_definition'}}
DECISIONS={'python':{'if_statement','elif_clause','for_statement','while_statement','except_clause','conditional_expression','for_in_clause','if_clause'},'java':{'if_statement','for_statement','enhanced_for_statement','while_statement','do_statement','catch_clause','ternary_expression'},'c':{'if_statement','for_statement','while_statement','do_statement','conditional_expression'},'cpp':{'if_statement','for_statement','for_range_loop','while_statement','do_statement','catch_clause','conditional_expression'}}
BOUNDARIES={'function_definition','method_declaration','constructor_declaration','lambda','lambda_expression','class_definition','class_declaration','interface_declaration','enum_declaration','record_declaration','class_specifier','struct_specifier'}
RULE='experimental.cc.named-definition.v0'
def digest(b):return hashlib.sha256(b).hexdigest()
def canonical(d):return json.dumps(d,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()+b'\n'
def walk(node):
 stack=[node]
 while stack:
  n=stack.pop();yield n;stack.extend(reversed(n.children))
def decisions(body,lang):
 count=1;stack=[body]
 while stack:
  n=stack.pop()
  if n is not body and n.type in BOUNDARIES:continue
  if n.type in DECISIONS[lang]:count+=1
  # Operators are tokens; each short-circuit operation adds one decision.
  if n.type in ({'and','or'} if lang=='python' else {'&&','||'}):count+=1
  if n.type in {'case_statement','switch_label','case_clause'}:
   text=n.text.lstrip()
   if not (text.startswith(b'default') or (lang=='python' and text.startswith(b'case _:'))):count+=1
  stack.extend(reversed(n.children))
 return count
def name_of(n):
 name=n.child_by_field_name('name')
 if name:return name.text.decode('utf-8',errors='replace')
 decl=n.child_by_field_name('declarator')
 if decl:
  while decl.child_by_field_name('declarator'):decl=decl.child_by_field_name('declarator')
  return decl.text.decode('utf-8',errors='replace')
 return '<unnamed>'
def analyse(data,path,lang,parser):
 tree=parser.parse(data);errors=[];definitions=[]
 for n in walk(tree.root_node):
  if n.type=='ERROR' or n.is_missing:
   errors.append({'line':n.start_point.row+1,'byte_start':n.start_byte,'byte_end':n.end_byte,'kind':n.type if not n.is_missing else 'missing:'+n.type})
  if n.type not in DEFINITIONS[lang]:continue
  body=n.child_by_field_name('body')
  if body is None:continue # abstract declarations are not executable definitions
  outer=[];parent=n.parent
  while parent:
   if parent.type in BOUNDARIES and parent.child_by_field_name('name'):outer.append(name_of(parent))
   parent=parent.parent
  symbol='.'.join(list(reversed(outer))+[name_of(n)])
  span={'byte_start':n.start_byte,'byte_end':n.end_byte,'line_start':n.start_point.row+1,'line_end':n.end_point.row+1,'column_start_bytes':n.start_point.column,'column_end_bytes':n.end_point.column}
  cc=decisions(body,lang)
  definitions.append({'id':digest(canonical([path,span['byte_start'],span['byte_end'],lang])),'path':path,'source_sha256':digest(data),'symbol':symbol,'kind':n.type,'span':span,'metrics':{'cyclomatic_complexity':cc,'physical_lines':n.end_point.row-n.start_point.row+1},'snippet_sha256':digest(data[n.start_byte:n.end_byte])})
 return definitions,errors

def run(archive,lang,repository,commit,scope):
 module=importlib.import_module('tree_sitter_'+lang);parser=Parser(Language(module.language()))
 inventory=[];definitions=[];diagnostics=[];excluded=[]
 # Scope profile is explicit and frozen by content hash. Probes may include all tracked source.
 with tarfile.open(archive) as tar:
  for member in sorted(tar.getmembers(),key=lambda m:m.name):
   if not member.isfile():continue
   path=member.name
   if PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts:raise ValueError('Unsafe archive path')
   if Path(path).suffix.lower() not in EXTENSIONS[lang]:continue
   if scope.get('include_prefixes') and not any(path.startswith(p) for p in scope['include_prefixes']):excluded.append({'path':path,'reason':'outside declared prefixes'});continue
   if any(part.lower() in scope.get('exclude_directory_names',[]) for part in PurePosixPath(path).parts[:-1]):excluded.append({'path':path,'reason':'declared directory exclusion'});continue
   if any(path.startswith(p) for p in scope.get('exclude_prefixes',[])):excluded.append({'path':path,'reason':'declared prefix exclusion'});continue
   data=tar.extractfile(member).read()
   if any(marker.encode().lower() in data[:2048].lower() for marker in scope.get('generated_markers',[])):excluded.append({'path':path,'reason':'generated header marker'});continue
   if lang=='python' and scope.get('python_parser') in {'legacy','legacy3'}:
    from legacy_python import analyse as legacy_analyse
    ds,errs=legacy_analyse(data,path,python3_mode=scope.get('python_parser')=='legacy3')
   else:ds,errs=analyse(data,path,lang,parser)
   definitions.extend(ds)
   inventory.append({'path':path,'sha256':digest(data),'bytes':len(data),'physical_lines':len(data.splitlines()),'parse_status':'failed' if errs else 'complete'})
   diagnostics.extend({'path':path,**e} for e in errs)
 findings=[{'rule_id':RULE,'concept':'High cyclomatic complexity','language':lang,'severity':'unspecified','threshold':{'operator':'>','value':10},**d} for d in definitions if d['metrics']['cyclomatic_complexity']>10]
 valid=bool(inventory) and not diagnostics
 grammar_id=importlib.metadata.version('tree-sitter-'+lang)
 adapter_hash=digest(Path(__file__).read_bytes())
 if lang=='python' and scope.get('python_parser') in {'legacy','legacy3'}:
  from lib2to3 import pygram
  grammar_id='lib2to3 / '+sys.version+' / grammar-sha256:'+digest(Path(pygram._GRAMMAR_FILE).read_bytes())
  adapter_hash=digest(Path(__file__).read_bytes()+Path(__file__).with_name('legacy_python.py').read_bytes())
 return {'schema_version':'evolution.findings/0.1','purpose':'feasibility_probe','admitted':False,'repository':repository,'commit':commit,'language':lang,'rule_id':RULE,'archive_sha256':digest(archive.read_bytes()),'scope':scope,'scope_sha256':digest(canonical(scope)),'tool':{'adapter_sha256':adapter_hash,'tree_sitter':importlib.metadata.version('tree-sitter'),'grammar':grammar_id},'status':{'syntax':'complete' if valid else 'partial' if inventory else 'not_applicable','semantic':'not_evaluated','build':'not_evaluated','runtime':'not_evaluated','native_preprocessing':'not_evaluated' if lang in {'c','cpp'} else 'not_applicable'},'inventory':inventory,'excluded':excluded,'diagnostics':diagnostics,'definitions':definitions,'findings':findings,'summary':{'eligible_files':len(inventory),'parsed_files':sum(x['parse_status']=='complete' for x in inventory),'definition_count':len(definitions),'finding_count':len(findings),'prevalence':len(findings)/len(definitions) if valid and definitions else None,'physical_lines':sum(x['physical_lines'] for x in inventory),'sensitivity_counts':{str(t):sum(d['metrics']['cyclomatic_complexity']>t for d in definitions) for t in [10,15,20]}},'limitations':['Experimental rule mapping; requires validation before scientific admission.','Counts from partial parses are diagnostic only.','No semantic resolution; no God Class or deprecation claims.','Native macros/configuration completeness is not established.']}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--archive',type=Path,required=True);ap.add_argument('--language',choices=EXTENSIONS,required=True);ap.add_argument('--repository',required=True);ap.add_argument('--commit',required=True);ap.add_argument('--scope',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 result=run(a.archive,a.language,a.repository,a.commit,json.loads(a.scope.read_text()));a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical(result));print(result['language'],result['status']['syntax'],result['summary']['eligible_files'],result['summary']['parsed_files'])
