using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
using HybridLens.Core.QualityAttributes;
using HybridLens.StaticAnalysis.Abstractions;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace HybridLens.StaticAnalysis.Detectors;

public sealed class ObsoleteApiDetector(ObsoleteApiConfig config) : IDetector
{
    public AntiPatternType Type => AntiPatternType.ObsoleteApiUsage;

    public IEnumerable<Finding> Detect(Compilation compilation)
    {
        foreach (var tree in compilation.SyntaxTrees)
        {
            var semanticModel = compilation.GetSemanticModel(tree);
            var root = tree.GetRoot();

            // Candidate nodes: any place a symbol is referenced
            var candidates = root.DescendantNodes().Where(n =>
                n is IdentifierNameSyntax
                or MemberAccessExpressionSyntax
                or ObjectCreationExpressionSyntax
                or InvocationExpressionSyntax);

            // Deduplicate by symbol + location to avoid double-reporting
            var reported = new HashSet<string>();

            foreach (var node in candidates)
            {
                var symbol = semanticModel.GetSymbolInfo(node).Symbol;
                if (symbol is null)
                    continue;

                var key = $"{symbol.ToDisplayString()}@{node.GetLocation().GetLineSpan().StartLinePosition}";
                if (!reported.Add(key))
                    continue;

                var obsoleteAttr = GetObsoleteAttribute(symbol);
                var deprecatedNs = GetDeprecatedNamespaceMatch(symbol);

                if (obsoleteAttr is null && deprecatedNs is null)
                    continue;

                var lineSpan = tree.GetLineSpan(node.Span);
                var callerName = GetCallerName(node);
                var message = obsoleteAttr ?? $"Namespace matches deprecated prefix '{deprecatedNs}'";

                yield return new Finding
                {
                    Type       = AntiPatternType.ObsoleteApiUsage,
                    Severity   = IsObsoleteError(symbol) ? Severity.Critical : Severity.Warning,
                    FilePath   = tree.FilePath,
                    SymbolName = $"{callerName} → {symbol.ToDisplayString()}",
                    Line       = lineSpan.StartLinePosition.Line + 1,
                    Snippet    = node.ToFullString().Trim(),
                    ExpectedQualityAttributes = QualityAttributeMap.ForType(AntiPatternType.ObsoleteApiUsage),
                    Metrics    = new Dictionary<string, double>()
                };
            }
        }
    }

    private string? GetObsoleteAttribute(ISymbol symbol)
    {
        var attr = symbol.GetAttributes()
            .FirstOrDefault(a => a.AttributeClass?.ToDisplayString()
                is "System.ObsoleteAttribute");

        if (attr is null)
            return null;

        // First constructor arg is the message (optional)
        var message = attr.ConstructorArguments.FirstOrDefault().Value?.ToString();
        return message is not null ? $"[Obsolete] {message}" : "[Obsolete]";
    }

    private static bool IsObsoleteError(ISymbol symbol)
    {
        var attr = symbol.GetAttributes()
            .FirstOrDefault(a => a.AttributeClass?.ToDisplayString()
                is "System.ObsoleteAttribute");

        if (attr is null) return false;

        // Second constructor arg is isError (bool)
        var args = attr.ConstructorArguments;
        return args.Length >= 2 && args[1].Value is true;
    }

    private string? GetDeprecatedNamespaceMatch(ISymbol symbol)
    {
        if (config.DeprecatedNamespacePrefixes.Count == 0)
            return null;

        var ns = symbol.ContainingNamespace?.ToDisplayString() ?? string.Empty;

        return config.DeprecatedNamespacePrefixes
            .FirstOrDefault(prefix => ns.StartsWith(prefix, StringComparison.OrdinalIgnoreCase));
    }

    private static string GetCallerName(SyntaxNode node)
    {
        var method = node.Ancestors().OfType<MethodDeclarationSyntax>().FirstOrDefault();
        if (method is null)
            return "<unknown>";

        var typeName = method.Ancestors()
            .OfType<TypeDeclarationSyntax>()
            .FirstOrDefault()
            ?.Identifier.Text ?? "<unknown>";

        return $"{typeName}.{method.Identifier.Text}";
    }
}
