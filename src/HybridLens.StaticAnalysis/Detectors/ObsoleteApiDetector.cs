using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
using HybridLens.Core.QualityAttributes;
using HybridLens.StaticAnalysis.Abstractions;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace HybridLens.StaticAnalysis.Detectors;

/// <summary>
/// Detects Obsolete API usage via a semantic node-walk: every referenced symbol is
/// resolved through the semantic model and flagged when the symbol — or its containing
/// type — carries the <c>[Obsolete]</c> attribute (§4.2.1). This best-effort per-node
/// resolution is robust to partially-compiling workspaces (large legacy solutions rarely
/// compile cleanly under MSBuildWorkspace), unlike whole-compilation diagnostics which
/// the compiler suppresses inside error-laden method bodies.
///
/// Severity follows the attribute's <c>isError</c> flag: <c>[Obsolete(msg, true)]</c>
/// (compile-error deprecation) → Critical; otherwise → Warning.
///
/// A supplementary namespace-prefix check is available via configuration
/// (<see cref="ObsoleteApiConfig.DeprecatedNamespacePrefixes"/>).
/// </summary>
public sealed class ObsoleteApiDetector(ObsoleteApiConfig config) : IDetector
{
    private const string ObsoleteAttributeName = "System.ObsoleteAttribute";

    public AntiPatternType Type => AntiPatternType.ObsoleteApiUsage;

    public IEnumerable<Finding> Detect(Compilation compilation)
    {
        foreach (var tree in compilation.SyntaxTrees)
        {
            var model = compilation.GetSemanticModel(tree);
            var root  = tree.GetRoot();

            // Any node where a symbol is referenced.
            var candidates = root.DescendantNodes().Where(n =>
                n is IdentifierNameSyntax
                or MemberAccessExpressionSyntax
                or ObjectCreationExpressionSyntax
                or InvocationExpressionSyntax);

            var reported = new HashSet<string>();

            foreach (var node in candidates)
            {
                // In partially-compiling workspaces a call can bind ambiguously, leaving
                // Symbol null but CandidateSymbols populated — fall back to those.
                var info   = model.GetSymbolInfo(node);
                var symbol = info.Symbol ?? info.CandidateSymbols.FirstOrDefault();
                if (symbol is null)
                    continue;

                // Only genuine API surface counts as "obsolete API usage" — never locals,
                // parameters, range variables, labels, etc.
                if (symbol.Kind is not (SymbolKind.Method or SymbolKind.Property
                    or SymbolKind.Field or SymbolKind.Event or SymbolKind.NamedType))
                    continue;

                var selfObsolete = FindObsolete(symbol);
                var typeObsolete = FindObsolete(symbol.ContainingType);
                var obsoleteAttr = selfObsolete ?? typeObsolete;
                var deprecatedNs = GetDeprecatedNamespaceMatch(symbol);

                if (obsoleteAttr is null && deprecatedNs is null)
                    continue;

                // When obsolescence comes only from the containing type, exempt self-use
                // from inside that same type — the C# compiler does not flag intra-type usage.
                if (selfObsolete is null && typeObsolete is not null && symbol.ContainingType is not null)
                {
                    var enclosingType = node.Ancestors().OfType<TypeDeclarationSyntax>().FirstOrDefault();
                    if (enclosingType is not null &&
                        model.GetDeclaredSymbol(enclosingType) is { } enclosing &&
                        SymbolEqualityComparer.Default.Equals(enclosing, symbol.ContainingType))
                        continue;
                }

                // Dedup per distinct obsolete symbol (not per call site): an Obsolete API
                // Usage instance is a deprecated API that is used, reported at a representative
                // usage. This matches the per-API stratification in §4.3 and avoids hundreds of
                // near-identical findings for a heavily-called deprecated helper.
                var key = symbol.ToDisplayString();
                if (!reported.Add(key))
                    continue;

                var lineSpan   = tree.GetLineSpan(node.Span);
                var callerName = GetCallerName(node);

                yield return new Finding
                {
                    Type       = AntiPatternType.ObsoleteApiUsage,
                    Severity   = obsoleteAttr is not null && IsError(obsoleteAttr)
                                    ? Severity.Critical
                                    : Severity.Warning,
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

    /// <summary>
    /// Matches the [Obsolete] attribute by simple name as well as fully-resolved metadata
    /// name. The name fallback is essential because large legacy solutions frequently load
    /// under MSBuildWorkspace WITHOUT framework reference assemblies (the private NuGet feed
    /// / design-time build fails), so <c>System.ObsoleteAttribute</c> does not resolve and
    /// <c>AttributeClass.ToDisplayString()</c> returns an error-type name. The attribute is
    /// still listed on the (project-defined, resolvable) member, so its written name is reliable.
    /// </summary>
    private static AttributeData? FindObsolete(ISymbol? symbol)
        => symbol?.GetAttributes().FirstOrDefault(a =>
            a.AttributeClass?.ToDisplayString() == ObsoleteAttributeName ||
            a.AttributeClass?.Name is "ObsoleteAttribute" or "Obsolete");

    /// <summary>The second [Obsolete] constructor argument is the isError flag.</summary>
    private static bool IsError(AttributeData attr)
    {
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
        {
            var type = node.Ancestors().OfType<TypeDeclarationSyntax>().FirstOrDefault();
            return type?.Identifier.Text ?? "<unknown>";
        }

        var typeName = method.Ancestors()
            .OfType<TypeDeclarationSyntax>()
            .FirstOrDefault()
            ?.Identifier.Text ?? "<unknown>";

        return $"{typeName}.{method.Identifier.Text}";
    }
}
