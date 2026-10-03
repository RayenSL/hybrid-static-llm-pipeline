import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.io.*;
import javax.tools.*;
import javax.lang.model.element.*;
import javax.lang.model.type.*;
import com.sun.source.tree.*;
import com.sun.source.util.*;

/** Compiler-backed evidence extractor. No annotation processors or target execution. */
public class SemanticScan {
  static Trees trees; static JavacTask task; static Path root;
  static Map<String,Object> obj(Object... pairs) {var m=new LinkedHashMap<String,Object>();for(int i=0;i<pairs.length;i+=2)m.put((String)pairs[i],pairs[i+1]);return m;}
  static String json(Object x) {
    if(x==null)return "null";
    if(x instanceof String s)return "\""+s.replace("\\","\\\\").replace("\"","\\\"").replace("\n","\\n").replace("\r","\\r").replace("\t","\\t")+"\"";
    if(x instanceof Map<?,?> m){var a=new ArrayList<String>();m.forEach((k,v)->a.add(json(k.toString())+":"+json(v)));return "{"+String.join(",",a)+"}";}
    if(x instanceof Collection<?> c){var a=new ArrayList<String>();c.forEach(v->a.add(json(v)));return "["+String.join(",",a)+"]";}
    return x.toString();
  }
  static String path(CompilationUnitTree u){return root.relativize(Path.of(u.getSourceFile().toUri()).toAbsolutePath()).toString().replace('\\','/');}
  static long line(CompilationUnitTree u,Tree n){return u.getLineMap().getLineNumber(trees.getSourcePositions().getStartPosition(u,n));}
  static String symbol(Element e){return e.getEnclosingElement()+"#"+e;}
  static int complexity(Tree body) {
    if(body==null)return 1;
    return 1+new TreeScanner<Integer,Void>() {
      public Integer reduce(Integer a,Integer b){return (a==null?0:a)+(b==null?0:b);}
      public Integer scan(Tree t,Void v){if(t==null)return 0;int add=switch(t.getKind()){
        case IF,FOR_LOOP,ENHANCED_FOR_LOOP,WHILE_LOOP,DO_WHILE_LOOP,CATCH,CONDITIONAL_EXPRESSION,CONDITIONAL_AND,CONDITIONAL_OR -> 1;default->0;};
        if(t instanceof CaseTree c){add=(int)c.getLabels().stream().filter(l->l.getKind()!=Tree.Kind.DEFAULT_CASE_LABEL).count();if(c.getGuard()!=null)add++;}
        return add+Optional.ofNullable(super.scan(t,v)).orElse(0);}
      public Integer visitClass(ClassTree t,Void v){return 0;}
      public Integer visitMethod(MethodTree t,Void v){return 0;}
      public Integer visitLambdaExpression(LambdaExpressionTree t,Void v){return 0;}
    }.scan(body,null);
  }
  static boolean incompleteHierarchy(TypeMirror type, Set<String> seen) {
    if(type.getKind()==TypeKind.ERROR)return true;
    if(!seen.add(type.toString()))return false;
    for(var parent:task.getTypes().directSupertypes(type))if(incompleteHierarchy(parent,seen))return true;
    return false;
  }
  static int unresolved(TreePath p) {
    final int[] count={0};new TreePathScanner<Void,Void>() {
      void check(){var t=trees.getTypeMirror(getCurrentPath());if(trees.getElement(getCurrentPath())==null || (t!=null&&t.getKind()==TypeKind.ERROR))count[0]++;}
      public Void visitIdentifier(IdentifierTree n,Void v){check();return super.visitIdentifier(n,v);}
      public Void visitMemberSelect(MemberSelectTree n,Void v){check();return super.visitMemberSelect(n,v);}
    }.scan(p,null);return count[0];
  }
  static Set<Element> fields(TreePath p){var result=new HashSet<Element>();new TreePathScanner<Void,Void>(){
    void collect(){Element e=trees.getElement(getCurrentPath());if(e!=null && e.getKind()==ElementKind.FIELD)result.add(e);}
    public Void visitIdentifier(IdentifierTree n,Void v){collect();return super.visitIdentifier(n,v);}
    public Void visitMemberSelect(MemberSelectTree n,Void v){collect();return super.visitMemberSelect(n,v);}
  }.scan(p,null);return result;}
  public static void main(String[] args)throws Exception {
    root=Path.of(args[0]).toAbsolutePath();var out=Path.of(args[1]);String cp=args.length>2?args[2]:"";String release=args.length>3?args[3]:"21";
    var compiler=ToolProvider.getSystemJavaCompiler();if(compiler==null)throw new IllegalStateException("JDK compiler required");
    var diagnostics=new DiagnosticCollector<JavaFileObject>();var fm=compiler.getStandardFileManager(diagnostics,Locale.ROOT,StandardCharsets.UTF_8);
    List<File> files;try(var walk=Files.walk(root)){files=walk.filter(p->p.toString().endsWith(".java")).sorted().map(Path::toFile).toList();}
    if(files.isEmpty()){Files.writeString(out,json(obj("classes",List.of(),"methods",List.of(),"obsolete",List.of(),"diagnostics",List.of(),"parse_errors",0,"semantic_errors",0,"runtime",System.getProperty("java.version"),"compiler_release",release)));return;}
    var options=new ArrayList<>(List.of("--release",release,"-proc:none","-implicit:none","-Xlint:none","-Xmaxerrs","100000","-classpath",cp,"-sourcepath",root.toString()));
    task=(JavacTask)compiler.getTask(new StringWriter(),fm,diagnostics,options,null,fm.getJavaFileObjectsFromFiles(files));
    var units=new ArrayList<CompilationUnitTree>();task.parse().forEach(units::add);trees=Trees.instance(task);
    long parseErrors=diagnostics.getDiagnostics().stream().filter(d->d.getKind()==Diagnostic.Kind.ERROR).count();
    // Collect source trees before attribution introduces implicit constructors.
    var classPaths=new ArrayList<TreePath>();var methodPaths=new ArrayList<TreePath>();
    for(var u:units)new TreePathScanner<Void,Void>(){
      public Void visitClass(ClassTree c,Void v){if(c.getKind()==Tree.Kind.CLASS && !c.getSimpleName().toString().isEmpty())classPaths.add(getCurrentPath());return super.visitClass(c,v);}
      public Void visitMethod(MethodTree m,Void v){if(m.getBody()!=null && trees.getSourcePositions().getEndPosition(u,m)>=0)methodPaths.add(getCurrentPath());return super.visitMethod(m,v);}
    }.scan(u,null);
    task.analyze();long errors=diagnostics.getDiagnostics().stream().filter(d->d.getKind()==Diagnostic.Kind.ERROR).count();
    var errorsBySource=new HashMap<String,Integer>();for(var d:diagnostics.getDiagnostics())if(d.getKind()==Diagnostic.Kind.ERROR && d.getSource()!=null)
      errorsBySource.merge(d.getSource().toUri().toString(),1,Integer::sum);
    var methods=new ArrayList<Object>();var classes=new ArrayList<Object>();var obsolete=new TreeMap<String,Object>();var sourceApiReferences=new TreeSet<String>();
    for(var p:methodPaths){var m=(MethodTree)p.getLeaf();var u=p.getCompilationUnit();long start=line(u,m),end=u.getLineMap().getLineNumber(trees.getSourcePositions().getEndPosition(u,m));
      Element e=trees.getElement(p);methods.add(obj("path",path(u),"line",start,"symbol",e==null?m.getName().toString():symbol(e),"cc",complexity(m.getBody()),"physical_lines",end-start+1,"constructor",m.getReturnType()==null));}
    for(var p:classPaths){var c=(ClassTree)p.getLeaf();Element e=trees.getElement(p);if(!(e instanceof TypeElement type))continue;
      var publicFields=new ArrayList<Set<Element>>();int wmc=0;
      for(var member:c.getMembers())if(member instanceof MethodTree m && m.getReturnType()!=null){wmc+=complexity(m.getBody());if(m.getModifiers().getFlags().contains(Modifier.PUBLIC)){
        var own=new HashSet<Element>();for(var field:fields(new TreePath(p,m)))if(field.getEnclosingElement().equals(type)&&!field.getModifiers().contains(Modifier.STATIC))own.add(field);publicFields.add(own);}}
      var foreign=new HashSet<Element>();for(var field:fields(p)){Element owner=field.getEnclosingElement();if(owner instanceof TypeElement ot && trees.getPath(ot)!=null && !task.getTypes().isSubtype(task.getTypes().erasure(type.asType()),task.getTypes().erasure(ot.asType())))foreign.add(field);}
      int connected=0,total=0;for(int i=0;i<publicFields.size();i++)for(int j=i+1;j<publicFields.size();j++){total++;if(!Collections.disjoint(publicFields.get(i),publicFields.get(j)))connected++;}
      classes.add(obj("path",path(p.getCompilationUnit()),"line",line(p.getCompilationUnit(),c),"symbol",type.getQualifiedName().toString(),"wmc",wmc,"unresolved_count",unresolved(p)+(incompleteHierarchy(type.asType(),new HashSet<>())?1:0)+errorsBySource.getOrDefault(p.getCompilationUnit().getSourceFile().toUri().toString(),0),"atfd",foreign.size(),"tcc",total==0?1.0:(double)connected/total,"public_methods",publicFields.size(),"foreign_attributes",foreign.stream().map(SemanticScan::symbol).sorted().toList()));}
    for(var u:units)new TreePathScanner<Void,Void>(){
      void reference(Tree n){Element e=trees.getElement(getCurrentPath());if(e==null || !(e.getKind().isClass()||e.getKind().isInterface()||e.getKind()==ElementKind.METHOD||e.getKind()==ElementKind.CONSTRUCTOR||e.getKind()==ElementKind.FIELD))return;
        Element owner=e instanceof TypeElement?e:e.getEnclosingElement();if(trees.getPath(owner)==null)return; // source APIs only: never project today's JDK deprecations backwards
        sourceApiReferences.add(path(u)+"|"+symbol(e));
        boolean own=task.getElements().isDeprecated(e), inherited=task.getElements().isDeprecated(owner);if(!own&&!inherited)return;
        if(!own&&inherited){for(TreePath q=getCurrentPath();q!=null;q=q.getParentPath())if(q.getLeaf() instanceof ClassTree && owner.equals(trees.getElement(q)))return;}
        String key=path(u)+"|"+symbol(e);obsolete.putIfAbsent(key,obj("path",path(u),"line",line(u,n),"symbol",symbol(e),"declaration_path",path(trees.getPath(owner).getCompilationUnit()),"deprecation_origin",own?"referenced_symbol":"containing_type"));}
      public Void visitIdentifier(IdentifierTree n,Void v){reference(n);return super.visitIdentifier(n,v);}
      public Void visitMemberSelect(MemberSelectTree n,Void v){reference(n);return super.visitMemberSelect(n,v);}
      public Void visitNewClass(NewClassTree n,Void v){reference(n);return super.visitNewClass(n,v);}
    }.scan(u,null);
    var ds=new ArrayList<Object>();for(var d:diagnostics.getDiagnostics())if(d.getKind()==Diagnostic.Kind.ERROR)ds.add(obj("code",d.getCode(),"path",d.getSource()==null?null:root.relativize(Path.of(d.getSource().toUri())).toString().replace('\\','/'),"line",d.getLineNumber()));
    Files.writeString(out,json(obj("classes",classes,"methods",methods,"obsolete",obsolete.values(),"source_api_references",sourceApiReferences.size(),"diagnostics",ds,"parse_errors",parseErrors,"semantic_errors",errors,"runtime",System.getProperty("java.version"),"compiler_release",release)),StandardCharsets.UTF_8);fm.close();
  }
}
