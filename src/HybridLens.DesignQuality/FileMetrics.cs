using System.Text;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;

namespace HybridLens.DesignQuality;

public sealed record FileMetricsResult(int Tokens, int DecisionBurden, int? MaxCallableComplexity, int Bytes);

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
        return new FileMetricsResult(tokens, burden, max, Encoding.UTF8.GetByteCount(source));
    }
}
