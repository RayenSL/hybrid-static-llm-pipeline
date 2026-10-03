"""Check whether sampled line-alignment differences alter method-body classification."""
import collections,csv,json,os,re,subprocess
from pathlib import Path
from tree_sitter import Language,Parser
import tree_sitter_java
ROOT=Path(__file__).resolve().parents[2]
PARSER=Parser(Language(tree_sitter_java.language()))
BOUNDARIES={'function_definition','method_declaration','constructor_declaration','lambda','lambda_expression','class_definition','class_declaration','interface_declaration','enum_declaration','record_declaration','class_specifier','struct_specifier'}
def walk(root):
 stack=[root]
 while stack:
  n=stack.pop();yield n;stack.extend(reversed(n.children))
def name_of(n):
 name=n.child_by_field_name('name')
 if name:return name.text.decode('utf8','replace')
 decl=n.child_by_field_name('declarator')
 if decl:
  while decl.child_by_field_name('declarator'):decl=decl.child_by_field_name('declarator')
  return decl.text.decode('utf8','replace')
 return '<unnamed>'
def methods(data):
 out=collections.defaultdict(list);tree=PARSER.parse(data)
 for n in walk(tree.root_node):
  if n.type not in ('method_declaration','constructor_declaration'):continue
  body=n.child_by_field_name('body')
  if body is None:continue
  outer=[];p=n.parent
  while p:
   if p.type in BOUNDARIES and p.child_by_field_name('name'):outer.append(name_of(p))
   p=p.parent
  sym='.'.join(list(reversed(outer))+[name_of(n)])
  out[sym].append((body.start_point.row+1,body.end_point.row+1))
 return out
def run(repo,old,new):
 git=['git',f'--git-dir={ROOT / "tmp/maintenance-associations/git" / repo}']
 env=os.environ.copy();env['GIT_NO_LAZY_FETCH']='1'
 oldbytes=subprocess.run(git+['cat-file','blob',old],capture_output=True,check=True,env=env).stdout
 raw=subprocess.run(git+['diff','--no-ext-diff','--no-textconv','--unified=0',old,new],capture_output=True,check=True,env=env).stdout.decode('utf8','replace')
 hunks=[]
 for line in raw.splitlines():
  m=re.match(r'^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@',line)
  if m:hunks.append((int(m[1]),int(m[2] or 1)))
 return methods(oldbytes),hunks
def hit(hunks,span):
 lo,hi=span
 for start,length in hunks:
  if length and start<=hi and start+length-1>=lo:return True
  if not length and lo<=start<hi:return True
 return False
sample=json.load(open(ROOT/'analysis/method_fix_overlap/results/v0.1/diff-audit-sample.json'))
keys={(r['repository'],r['old_blob'],r['new_blob']) for r in sample['rows'] if not r['same_hunks']}
audit=collections.defaultdict(list)
for row in csv.DictReader(open(ROOT/'analysis/method_fix_overlap/results/v0.1/event-audit.csv')):
 key=(row['repository'],row['old_blob'],row['new_blob'])
 if key in keys:audit[key].append(row)
rows=[]
for repo,old,new in sorted(keys):
 parsed,hunks=run(repo,old,new)
 for r in audit[(repo,old,new)]:
  for label in ('flagged','control'):
   if r[label+'_status']!='matched':continue
   options=parsed[r[label+'_symbol']]
   if len(options)!=1:continue
   git_hit=hit(hunks,options[0]);py_hit=r[label+'_body_edit']=='1'
   rows.append({'repository':repo,'old_blob':old,'new_blob':new,'year':int(r['year']),'symbol':r[label+'_symbol'],'label':label,'python_body_edit':py_hit,'git_body_edit':git_hit,'agrees':py_hit==git_hit})
out={'sampled_events':sample['sampled_events'],'events_with_different_line_alignment':len(keys),'compared_method_observations':len(rows),'classification_disagreements':sum(not r['agrees'] for r in rows),'rows':rows}
p=ROOT/'analysis/method_fix_overlap/results/v0.1/diff-classification-sample.json';p.write_text(json.dumps(out,indent=2)+'\n')
print({k:v for k,v in out.items() if k!='rows'})
