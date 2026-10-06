using System.Text.Json;
using HybridLens.DesignQuality;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

internal static class CandidateAudit
{
    public static int Run(string[] args)
    {
        var original = Path.GetFullPath(args[1]);
        var baseline = CorpusCompiler.Load(Directory.GetFiles(Path.GetDirectoryName(original)!, "*.csproj").Single());
        var old = baseline.SyntaxTrees.Single(t => t.FilePath == original);
        var tree = CSharpSyntaxTree.ParseText(File.ReadAllText(args[2]), CorpusCompiler.ParseOptions, original);
        var candidate = baseline.ReplaceSyntaxTree(old, tree);
        var errors = candidate.GetDiagnostics().Where(d => d.Severity == DiagnosticSeverity.Error).Select(d => d.ToString()).ToArray();
        var violations = new HashSet<string>();
        var model = candidate.GetSemanticModel(tree);
        foreach (var node in tree.GetRoot().DescendantNodes())
        {
            if (node is UnsafeStatementSyntax || node is PointerTypeSyntax || node is FunctionPointerTypeSyntax)
                violations.Add("unsafe_code");
            if (node is IdentifierNameSyntax { Identifier.ValueText: "dynamic" }) violations.Add("dynamic_code");
            if (node is IdentifierNameSyntax or MemberAccessExpressionSyntax or ObjectCreationExpressionSyntax or AttributeSyntax)
            {
                var symbol = model.GetSymbolInfo(node).Symbol;
                var ns = symbol?.ContainingNamespace?.ToDisplayString() ?? "";
                var owner = (symbol as INamedTypeSymbol ?? symbol?.ContainingType)?.ToDisplayString() ?? "";
                if (new[] { "System.IO", "System.Net", "System.Reflection", "System.Diagnostics", "System.Threading", "System.Runtime.InteropServices" }
                    .Any(prefix => ns == prefix || ns.StartsWith(prefix + ".", StringComparison.Ordinal)) ||
                    owner is "System.Environment" or "System.AppDomain" or "System.GC" ||
                    owner.StartsWith("System.Runtime.Loader.", StringComparison.Ordinal) ||
                    (owner == "System.Type" && symbol?.Name != "op_Equality") || symbol?.Name == "GetType")
                    violations.Add("forbidden_runtime_access:" + symbol?.ToDisplayString());
            }
        }
        var before = StructuralFacts.Measure(baseline, old);
        var after = StructuralFacts.Measure(candidate, tree);
        var actual = after.ExposedMembers.Select(m => m.Id + "|" + m.Signature + "|" + m.Accessibility).ToHashSet();
        var missing = before.ExposedMembers.Select(m => m.Id + "|" + m.Signature + "|" + m.Accessibility)
            .Where(m => !actual.Contains(m)).Order().ToArray();
        File.WriteAllText(args[3], JsonSerializer.Serialize(new {
            build_passed = errors.Length == 0, diagnostics = errors,
            contract_passed = errors.Length == 0 && missing.Length == 0,
            missing_public_contract = missing,
            static_runtime_guard_passed = errors.Length == 0 && violations.Count == 0,
            runtime_guard_violations = violations.Order().ToArray(),
            guard_scope = "conservative syntax and resolved-symbol checks; process timeout; not an OS sandbox"
        }));
        return 0;
    }
}
