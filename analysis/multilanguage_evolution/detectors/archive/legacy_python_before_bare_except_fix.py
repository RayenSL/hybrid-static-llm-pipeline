"""Python 2/early-3 CST adapter using pinned CPython 3.12 lib2to3 grammar.

This module parses only. It never executes or refactors target source.
"""
import hashlib,io,json,tokenize,warnings
warnings.filterwarnings('ignore',category=DeprecationWarning,module=__name__)
from lib2to3 import pygram,pytree
from lib2to3.pgen2 import driver,token
SYM=pygram.python_symbols
PARSER=driver.Driver(pygram.python_grammar,convert=pytree.convert)
PARSER3=driver.Driver(pygram.python_grammar_no_print_and_exec_statement,convert=pytree.convert)
BOUNDARIES={SYM.funcdef,SYM.classdef,SYM.lambdef}
COUNTS={getattr(SYM,s) for s in ['if_stmt','for_stmt','while_stmt','except_clause','comp_for','comp_if'] if hasattr(SYM,s)}
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()+b'\n'
def sha(x):return hashlib.sha256(x).hexdigest()
def name(n):
 return next((c.value for c in n.children if isinstance(c,pytree.Leaf) and c.type==token.NAME and c.value not in {'def','class'}),'<unnamed>')
def complexity(body):
 value=1;stack=[body]
 while stack:
  n=stack.pop()
  if n is not body and n.type in BOUNDARIES:continue
  if n.type in COUNTS:value+=1
  if isinstance(n,pytree.Leaf) and n.type==token.NAME and n.value in {'and','or','elif'}:value+=1
  if n.type==SYM.test and any(isinstance(c,pytree.Leaf) and c.value=='if' for c in n.children):value+=1
  stack.extend(reversed(n.children))
 return value
def analyse(data,path,python3_mode=False):
 try:
  encoding,_=tokenize.detect_encoding(io.BytesIO(data).readline);text=data.decode(encoding);tree=(PARSER3 if python3_mode else PARSER).parse_string(text if text.endswith('\n') else text+'\n')
 except Exception as e:
  return [],[{'line':getattr(e,'lineno',1) or 1,'byte_start':0,'byte_end':0,'kind':'legacy_parse:'+type(e).__name__}]
 lines=text.splitlines(keepends=True);raw=data.splitlines(keepends=True);offsets=[];total=0
 for line in raw:offsets.append(total);total+=len(line)
 codec='utf-8' if encoding=='utf-8-sig' else encoding
 def offset(row,col):
  if row>len(lines):return len(data)
  return offsets[row-1]+len(lines[row-1][:col].encode(codec))+(3 if encoding=='utf-8-sig' and row==1 else 0)
 result=[]
 for n in tree.pre_order():
  if n.type!=SYM.funcdef:continue
  leaves=[x for x in n.leaves() if x.type not in {token.INDENT,token.DEDENT,token.NEWLINE,token.ENDMARKER} and x.value]
  first,last=leaves[0],leaves[-1];pieces=last.value.split('\n');endrow=last.lineno+len(pieces)-1;endcol=len(pieces[-1]) if len(pieces)>1 else last.column+len(last.value)
  start,end=offset(first.lineno,first.column),offset(endrow,endcol);span={'byte_start':start,'byte_end':end,'line_start':first.lineno,'line_end':endrow,'column_start_bytes':start-offsets[first.lineno-1],'column_end_bytes':end-offsets[endrow-1]}
  parent=n.parent;outer=[]
  while parent:
   if parent.type in {SYM.classdef,SYM.funcdef}:outer.append(name(parent))
   parent=parent.parent
  body=n.children[-1];cc=complexity(body)
  result.append({'id':sha(canonical([path,start,end,'python'])),'path':path,'source_sha256':sha(data),'symbol':'.'.join(list(reversed(outer))+[name(n)]),'kind':'function_definition','span':span,'metrics':{'cyclomatic_complexity':cc,'physical_lines':endrow-first.lineno+1},'snippet_sha256':sha(data[start:end])})
 return result,[]
