using System.Text.Json;
using HybridLens.DesignQuality;
using HybridLens.StaticAnalysis.Metrics;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

internal static class ExpandedFacts
{
    private static readonly JsonSerializerOptions Options = new() { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
    // --facts original candidate output; measures the complete edited file and every tree in its project.
    public static int Run(string[] args)
    {
        var original = Path.GetFullPath(args[1]);
        var project = Directory.GetFiles(Path.GetDirectoryName(original)!, "*.csproj").Single();
        var baseline = CorpusCompiler.Load(project);
        var old = baseline.SyntaxTrees.Single(t => t.FilePath == original);
        var tree = CSharpSyntaxTree.ParseText(File.ReadAllText(args[2]), CorpusCompiler.ParseOptions, original);
        var compilation = baseline.ReplaceSyntaxTree(old, tree);
        var facts = StructuralFacts.Measure(compilation, tree);
        var findings = new List<object>();
        if (facts.Status == "measured")
        foreach (var source in compilation.SyntaxTrees.Where(t => t.FilePath != "__ImplicitUsings.g.cs"))
        {
            var model = compilation.GetSemanticModel(source);
            var file = Path.GetRelativePath(Path.GetDirectoryName(project)!, source.FilePath).Replace('\\', '/');
            foreach (var method in source.GetRoot().DescendantNodes().OfType<MethodDeclarationSyntax>())
            {
                var complexity = CyclomaticComplexity.Of(method);
                if (complexity > 10)
                    findings.Add(new { type = "LongMethod", file, symbol = StructuralFacts.SymbolId(model.GetDeclaredSymbol(method)!),
                        line = method.GetLocation().GetLineSpan().StartLinePosition.Line + 1, complexity });
            }
            foreach (var cls in source.GetRoot().DescendantNodes().OfType<ClassDeclarationSyntax>())
            {
                var metrics = ClassMetrics.Compute(cls, model);
                if (metrics.Atfd > 4 && metrics.Wmc >= 47 && metrics.Tcc < 1.0 / 3.0)
                    findings.Add(new { type = "GodClass", file, symbol = StructuralFacts.SymbolId(model.GetDeclaredSymbol(cls)!),
                        line = cls.GetLocation().GetLineSpan().StartLinePosition.Line + 1, metrics });
            }
        }
        File.WriteAllText(args[3], JsonSerializer.Serialize(new {
            schema_version = "maintenance-structure/0.1", scope = "complete edited file and one independent corpus project",
            file = Path.GetFileName(original), facts, project_findings = facts.Status == "measured" ? findings.ToArray() : null,
            project_tree_count = compilation.SyntaxTrees.Count(t => t.FilePath != "__ImplicitUsings.g.cs"),
            diagnostics = compilation.GetDiagnostics().Where(d => d.Severity is DiagnosticSeverity.Warning or DiagnosticSeverity.Error)
                .Select(d => new { id = d.Id, severity = d.Severity.ToString(), message = d.GetMessage(),
                    file = d.Location.SourceTree is null ? null : Path.GetRelativePath(Path.GetDirectoryName(project)!, d.Location.SourceTree.FilePath).Replace('\\', '/'),
                    line = d.Location.GetLineSpan().StartLinePosition.Line + 1 }).ToArray()
        }, Options));
        return 0;
    }

    // Verify that the registered prompt context alone compiles both source versions.
    public static int Context(string[] args)
    {
        using var paths = JsonDocument.Parse(File.ReadAllText(args[1]));
        var trees = paths.RootElement.EnumerateArray().Select(p => {
            var path = p.GetString()!;
            return CSharpSyntaxTree.ParseText(File.ReadAllText(path), CorpusCompiler.ParseOptions, path);
        });
        var diagnostics = CorpusCompiler.FromSources(trees).GetDiagnostics()
            .Where(d => d.Severity == DiagnosticSeverity.Error).Select(d => d.ToString()).ToArray();
        File.WriteAllText(args[2], JsonSerializer.Serialize(new { build_passed = diagnostics.Length == 0, diagnostics }));
        return 0;
    }
}
