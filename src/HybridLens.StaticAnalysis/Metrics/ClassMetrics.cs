using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace HybridLens.StaticAnalysis.Metrics;

/// <summary>
/// The three Lanza &amp; Marinescu (2006) God Class metrics, computed from a class
/// declaration via Roslyn's semantic model.
///
/// <list type="bullet">
///   <item><b>ATFD</b> — Access To Foreign Data: the number of distinct attributes
///   (fields/properties) belonging to <i>other project-defined classes</i> that this
///   class accesses. Own and inherited attributes are excluded; framework/library
///   attributes (e.g. <c>string.Length</c>) are excluded because only types defined
///   in source are counted.</item>
///   <item><b>WMC</b> — Weighted Method Count: the sum of the cyclomatic complexities
///   of the class's declared methods.</item>
///   <item><b>TCC</b> — Tight Class Cohesion: the fraction of public-method pairs that
///   access at least one common instance attribute of this class. Range [0,1].
///   Undefined for fewer than two public methods → reported as 1.0 (maximally cohesive,
///   so the God Class cohesion criterion is not met).</item>
/// </list>
/// </summary>
public sealed record ClassMetricsResult(int Atfd, int Wmc, double Tcc, int PublicMethodCount);

public static class ClassMetrics
{
    public static ClassMetricsResult Compute(ClassDeclarationSyntax classDecl, SemanticModel model)
    {
        if (model.GetDeclaredSymbol(classDecl) is not INamedTypeSymbol classSymbol)
            return new ClassMetricsResult(0, 0, 1.0, 0);

        var atfd = ComputeAtfd(classDecl, classSymbol, model);
        var wmc  = ComputeWmc(classDecl);
        var (tcc, publicMethods) = ComputeTcc(classDecl, classSymbol, model);

        return new ClassMetricsResult(atfd, wmc, tcc, publicMethods);
    }

    // ── ATFD ──────────────────────────────────────────────────────────────────

    private static int ComputeAtfd(ClassDeclarationSyntax classDecl, INamedTypeSymbol classSymbol, SemanticModel model)
    {
        var foreign = new HashSet<ISymbol>(SymbolEqualityComparer.Default);

        foreach (var attr in AccessedAttributes(classDecl, model))
        {
            if (IsForeign(attr, classSymbol) && IsProjectDefined(attr))
                foreign.Add(attr.OriginalDefinition);
        }

        return foreign.Count;
    }

    /// <summary>An attribute is foreign if it belongs to neither this class nor any of its base types.</summary>
    private static bool IsForeign(ISymbol attr, INamedTypeSymbol classSymbol)
    {
        var owner = attr.ContainingType;
        if (owner is null) return false;

        for (INamedTypeSymbol? t = classSymbol; t is not null; t = t.BaseType)
            if (SymbolEqualityComparer.Default.Equals(t.OriginalDefinition, owner.OriginalDefinition))
                return false;

        return true;
    }

    /// <summary>Only attributes whose owning type is defined in source count — excludes framework/library types.</summary>
    private static bool IsProjectDefined(ISymbol attr)
        => attr.ContainingType?.Locations.Any(l => l.IsInSource) ?? false;

    // ── WMC ───────────────────────────────────────────────────────────────────

    private static int ComputeWmc(ClassDeclarationSyntax classDecl)
        => classDecl.Members
            .OfType<MethodDeclarationSyntax>()
            .Sum(CyclomaticComplexity.Of);

    // ── TCC ───────────────────────────────────────────────────────────────────

    private static (double Tcc, int PublicMethods) ComputeTcc(
        ClassDeclarationSyntax classDecl, INamedTypeSymbol classSymbol, SemanticModel model)
    {
        var publicMethods = classDecl.Members
            .OfType<MethodDeclarationSyntax>()
            .Where(m => m.Modifiers.Any(mod => mod.IsKind(Microsoft.CodeAnalysis.CSharp.SyntaxKind.PublicKeyword)))
            .ToList();

        var n = publicMethods.Count;
        if (n < 2)
            return (1.0, n); // no pairs → maximally cohesive by convention

        // Per-method set of own instance attributes accessed.
        var fieldSets = publicMethods
            .Select(m => AccessedAttributes(m, model)
                .Where(a => IsOwnInstanceAttribute(a, classSymbol))
                .Select(a => a.OriginalDefinition)
                .ToHashSet(SymbolEqualityComparer.Default))
            .ToList();

        var connected = 0;
        var total = 0;
        for (var i = 0; i < n; i++)
        for (var j = i + 1; j < n; j++)
        {
            total++;
            if (fieldSets[i].Overlaps(fieldSets[j]))
                connected++;
        }

        return (total == 0 ? 1.0 : (double)connected / total, n);
    }

    private static bool IsOwnInstanceAttribute(ISymbol attr, INamedTypeSymbol classSymbol)
    {
        var (isStatic, owner) = attr switch
        {
            IFieldSymbol f    => (f.IsStatic, f.ContainingType),
            IPropertySymbol p => (p.IsStatic, p.ContainingType),
            _                 => (false, null)
        };
        return owner is not null
            && !isStatic
            && SymbolEqualityComparer.Default.Equals(owner.OriginalDefinition, classSymbol.OriginalDefinition);
    }

    // ── Shared attribute-access walk ────────────────────────────────────────────

    /// <summary>
    /// Yields the field/property symbol for every member access or bare identifier in
    /// <paramref name="scope"/> that resolves to a field or property. Callers de-duplicate
    /// via a <see cref="HashSet{T}"/>, so the same attribute appearing under both
    /// <c>this.x</c> and <c>x</c> is harmless.
    /// </summary>
    private static IEnumerable<ISymbol> AccessedAttributes(SyntaxNode scope, SemanticModel model)
    {
        foreach (var node in scope.DescendantNodes())
        {
            if (node is not (IdentifierNameSyntax or MemberAccessExpressionSyntax))
                continue;

            var sym = model.GetSymbolInfo(node).Symbol;
            if (sym is IFieldSymbol or IPropertySymbol)
                yield return sym;
        }
    }
}
