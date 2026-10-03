"""Independent Java 8 AST cross-check; unsupported files are reported, not hidden."""
import argparse,json,sys,tarfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--packages',type=Path,required=True);ap.add_argument('--sources',type=Path,required=True);ap.add_argument('--results',type=Path,required=True);a=ap.parse_args();sys.path.insert(0,str(a.packages.resolve()))
    import javalang
    t=javalang.tree
    boundaries=(t.MethodDeclaration,t.ConstructorDeclaration,t.LambdaExpression,t.ClassDeclaration,t.InterfaceDeclaration,t.EnumDeclaration)
    branches=(t.IfStatement,t.ForStatement,t.WhileStatement,t.DoStatement,t.CatchClause,t.TernaryExpression)
    def count(node):
        if node is None:return 0
        if isinstance(node,(list,tuple)):return sum(count(n) for n in node)
        if not isinstance(node,javalang.ast.Node) or isinstance(node,boundaries):return 0
        value=int(isinstance(node,branches))
        if isinstance(node,t.BinaryOperation) and node.operator in ['&&','||']:value+=1
        if isinstance(node,t.SwitchStatementCase) and node.case:value+=len(node.case)
        return value+sum(count(getattr(node,k)) for k in node.attrs)
    report={'parser':'javalang 0.13.0 (Java 8 grammar)','status':'Independent syntax-measurement comparison, not defect validation','snapshots':[]}
    for repo in ['jenkinsci__jenkins','apache__tomcat']:
        for label in ['earliest-2006','2016','2024']:
            name=repo+'-'+label;d=json.loads((a.results/(name+'-java.json')).read_text());expected={};observed={};failures=[];parsed=set()
            with tarfile.open(a.sources/(name+'.tar')) as tar:
                for item in d['inventory']:
                    path=item['path'];data=tar.extractfile(path).read()
                    try:tree=javalang.parse.parse(data.decode('utf8'))
                    except (javalang.parser.JavaSyntaxError,javalang.tokenizer.LexerError,UnicodeError,TypeError,IndexError) as e:
                        failures.append({'path':path,'kind':type(e).__name__});continue
                    parsed.add(path)
                    for _,node in tree:
                        if isinstance(node,(t.MethodDeclaration,t.ConstructorDeclaration)) and node.body is not None:
                            observed[(path,node.position.line,node.name)]=1+count(node.body)
            for x in d['definitions']:
                if x['path'] in parsed:
                    # Annotation/modifier starts differ between parsers; align by source symbol and declaration line below.
                    expected[(x['path'],x['span']['line_start'],x['symbol'].split('.')[-1])]=x['metrics']['cyclomatic_complexity']
            # Match by file/name and order: handles overloads and parser annotation-start differences.
            def group(values):
                out={}
                for (path,line,name),cc in sorted(values.items()):out.setdefault((path,name),[]).append((line,cc))
                return out
            aa,bb=group(expected),group(observed);mismatches=[];matches=0
            for k in sorted(aa.keys()|bb.keys()):
                left,right=aa.get(k,[]),bb.get(k,[])
                if len(left)!=len(right):mismatches.append({'path':k[0],'name':k[1],'adapter':left,'ast':right,'kind':'enumeration'});continue
                for x,y in zip(left,right):
                    if x[1]!=y[1]:mismatches.append({'path':k[0],'name':k[1],'adapter':x,'ast':y,'kind':'complexity'})
                    else:matches+=1
            row={'repository':repo,'label':label,'eligible_files':len(d['inventory']),'independently_parsed_files':len(parsed),'compared_definitions':len(expected),'matching':matches,'mismatch_count':len(mismatches),'mismatches':mismatches,'unsupported_files':failures}
            report['snapshots'].append(row)
            (HERE/'results/java-ast-validation.json').write_text(json.dumps(report,indent=2)+'\n')
            print(repo,label,len(expected),len(mismatches),len(failures),flush=True)
    (HERE/'results/java-ast-validation.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
