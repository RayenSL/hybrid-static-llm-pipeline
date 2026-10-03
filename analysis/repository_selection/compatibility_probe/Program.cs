using System.Text.Json;
using HybridLens.Core.Configuration;
using HybridLens.StaticAnalysis.Workspace;
using HybridLens.StaticAnalysis.Detectors;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using System.Diagnostics;
var sw = Stopwatch.StartNew();
using var loader = new WorkspaceLoader(new WorkspaceConfig());
try {
 var compilations = await loader.LoadAsync(args[0]);
 var rows = new List<object>();
 foreach (var c in compilations) {
  var diagnostics = c.GetDiagnostics();
  var errs = diagnostics.Where(d=>d.Severity==DiagnosticSeverity.Error).ToArray();
  var trees = c.SyntaxTrees.ToArray();
  var types = new GodClassDetector(new GodClassConfig()).Detect(c).Count();
  var methods = new LongMethodDetector(new LongMethodConfig()).Detect(c).Count();
  var obsolete = new ObsoleteApiDetector(new ObsoleteApiConfig()).Detect(c).Count();
  rows.Add(new { assembly=c.AssemblyName, syntaxTrees=trees.Length,
   methods=trees.Sum(t=>t.GetRoot().DescendantNodes().OfType<MethodDeclarationSyntax>().Count()),
   classes=trees.Sum(t=>t.GetRoot().DescendantNodes().OfType<ClassDeclarationSyntax>().Count()),
   errorCount=errs.Length, errors=errs.GroupBy(e=>e.Id).Select(g=>new {id=g.Key,count=g.Count(),example=g.First().ToString()}).Take(10),
   findings=new {godClass=types,longMethod=methods,obsoleteApi=obsolete},
   referenceCount=c.References.Count(),files=trees.Select(t=>t.FilePath).ToArray() });
 }
 var result=new { target=args[0],elapsedSeconds=sw.Elapsed.TotalSeconds,projectCount=compilations.Count,warnings=loader.Warnings,projects=rows };
 File.WriteAllText(args[1],JsonSerializer.Serialize(result,new JsonSerializerOptions {WriteIndented=true}));
 Console.WriteLine($"Loaded {compilations.Count} projects; wrote {args[1]} in {sw.Elapsed.TotalSeconds:F1}s");
} catch(Exception e) { File.WriteAllText(args[1],JsonSerializer.Serialize(new {error=e.ToString(),elapsedSeconds=sw.Elapsed.TotalSeconds})); Console.Error.WriteLine(e);return 2; }
return 0;
