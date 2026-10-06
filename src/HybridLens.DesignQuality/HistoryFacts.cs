using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace HybridLens.DesignQuality;

public sealed record MethodFact(string Symbol, int Complexity, int Lines, int Line);

public sealed record ClassFact(string Symbol, int Wmc, int Line);

public sealed record HistoryFactsResult(IReadOnlyList<MethodFact> Methods, IReadOnlyList<ClassFact> Classes);

/// <summary>
/// Syntax-only facts that reproduce the thesis detector's Long Method rule exactly (cyclomatic complexity per method, named Type.Method)
/// and the WMC part of its God Class rule, so a git history can be scanned without building any commit.
/// </summary>
public static class HistoryFacts
{
    public static HistoryFactsResult Measure(string source)
    {
        var tree = CSharpSyntaxTree.ParseText(source);
        var root = tree.GetRoot();
        var methods = root.DescendantNodes().OfType<MethodDeclarationSyntax>().Select(m =>
        {
            var span = tree.GetLineSpan(m.Span);
            var owner = m.Ancestors().OfType<TypeDeclarationSyntax>().FirstOrDefault()?.Identifier.Text ?? "<unknown>";
            return new MethodFact($"{owner}.{m.Identifier.Text}", FileMetrics.DetectorComplexity(m),
                span.EndLinePosition.Line - span.StartLinePosition.Line + 1, span.StartLinePosition.Line + 1);
        }).ToList();
        var classes = root.DescendantNodes().OfType<ClassDeclarationSyntax>().Select(c =>
        {
            var ns = c.Ancestors().OfType<BaseNamespaceDeclarationSyntax>().FirstOrDefault()?.Name.ToString();
            return new ClassFact(ns is null ? c.Identifier.Text : $"{ns}.{c.Identifier.Text}",
                c.Members.OfType<MethodDeclarationSyntax>().Sum(FileMetrics.DetectorComplexity), tree.GetLineSpan(c.Span).StartLinePosition.Line + 1);
        }).ToList();
        return new HistoryFactsResult(methods, classes);
    }
}
