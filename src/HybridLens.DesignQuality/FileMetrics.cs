using System.Text;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace HybridLens.DesignQuality;

public sealed record FileMetricsResult(int Tokens, int DecisionBurden, int? MaxCallableComplexity, int Bytes, IReadOnlyDictionary<string, int> Callables);

/// <summary>Syntax-only per-file measures for replayed branch states, which need no compilation.</summary>
public static class FileMetrics
{
    public static FileMetricsResult Measure(string source)
    {
        var root = CSharpSyntaxTree.ParseText(source).GetRoot();
        var owned = new Dictionary<SyntaxNode, int>();
        var burden = 0;
        foreach (var node in root.DescendantNodes())
        {
            var weight = StructuralFacts.DecisionWeight(node);
            if (weight == 0 || node.Ancestors().FirstOrDefault(StructuralFacts.IsCallable) is not { } owner) continue;
            burden += weight;
            owned[owner] = owned.GetValueOrDefault(owner) + weight;
        }
        var callables = root.DescendantNodes().Where(StructuralFacts.IsCallable).ToList();
        int? max = callables.Count == 0 ? null : 1 + callables.Max(c => owned.GetValueOrDefault(c));
        var tokens = root.DescendantTokens().Count(t => !t.IsKind(SyntaxKind.EndOfFileToken));
        // Keyed like detector symbols (Type.Method); overloads share a key, so the largest one stands for the name.
        var named = callables.OfType<MethodDeclarationSyntax>().Where(m => m.Parent is BaseTypeDeclarationSyntax)
            .GroupBy(m => $"{((BaseTypeDeclarationSyntax)m.Parent!).Identifier.Text}.{m.Identifier.Text}")
            .ToDictionary(g => g.Key, g => g.Max(m => owned.GetValueOrDefault(m)));
        return new FileMetricsResult(tokens, burden, max, Encoding.UTF8.GetByteCount(source), named);
    }
}
