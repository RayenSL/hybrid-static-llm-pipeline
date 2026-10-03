"""Independent CPython AST comparison for all eligible files in fixed modern snapshots.

This verifies the stated syntax metric, not defect classification or clinical precision.
"""
import argparse,ast,json,tarfile,warnings
warnings.filterwarnings("ignore", category=SyntaxWarning)
from pathlib import Path
HERE=Path(__file__).resolve().parent
class Decisions(ast.NodeVisitor):
    def __init__(self):self.value=1
    def generic_visit(self,node):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.Lambda,ast.ClassDef)):return
        if isinstance(node,(ast.If,ast.For,ast.AsyncFor,ast.While,ast.ExceptHandler,ast.IfExp)):self.value+=1
        if isinstance(node,ast.BoolOp):self.value+=len(node.values)-1
        if isinstance(node,ast.comprehension):self.value+=1+len(node.ifs)
        if isinstance(node,ast.match_case):
            if not (isinstance(node.pattern,ast.MatchAs) and node.pattern.pattern is None and node.pattern.name is None and node.guard is None):self.value+=1
            if node.guard is not None:self.value+=1
        super().generic_visit(node)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--sources',type=Path,required=True);ap.add_argument('--results',type=Path,required=True);a=ap.parse_args()
    report={'status':'independent Python AST measurement comparison','snapshots':[]}
    for label in ['2018','2020','2023','endpoint-2026']:
        name='odoo__odoo-'+label
        d=json.loads((a.results/(name+'-python.json')).read_text())
        expected={(x['path'],x['span']['line_start'],x['symbol'].split('.')[-1]):x['metrics']['cyclomatic_complexity'] for x in d['definitions']}
        observed={};failures=[]
        with tarfile.open(a.sources/(name+'.tar')) as tar:
            for item in d['inventory']:
                path=item['path'];data=tar.extractfile(path).read()
                try:tree=ast.parse(data)
                except SyntaxError as e:failures.append({'path':path,'line':e.lineno,'reason':e.msg});continue
                for node in ast.walk(tree):
                    if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                        count=Decisions()
                        for stmt in node.body:count.visit(stmt)
                        observed[(path,node.lineno,node.name)]=count.value
        mismatches=[{'path':k[0],'line':k[1],'name':k[2],'adapter':expected.get(k),'ast':observed.get(k)} for k in sorted(expected.keys()|observed.keys()) if expected.get(k)!=observed.get(k)]
        row={'label':label,'adapter_definitions':len(expected),'ast_definitions':len(observed),'matching':sum(expected.get(k)==v for k,v in observed.items()),'mismatch_count':len(mismatches),'mismatches':mismatches,'parse_failures':failures}
        report['snapshots'].append(row);print(label,len(expected),len(mismatches),len(failures),flush=True)
    (HERE/'results/python-ast-validation.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
