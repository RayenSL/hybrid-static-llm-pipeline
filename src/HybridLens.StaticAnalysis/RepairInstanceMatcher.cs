using HybridLens.Core.Models;

namespace HybridLens.StaticAnalysis;

/// <summary>
/// Decides whether a re-measured detector finding still refers to a specific seeded instance,
/// tolerating the symbol-format differences across anti-patterns: God Class / Long Method use a
/// (possibly namespaced) type/method name, while Obsolete-API findings use the
/// "caller → Deprecated.Symbol" form where the deprecated callee identifies the instance. Matching
/// is scoped to a single file by the caller, so unqualified-name comparison is sufficient.
/// </summary>
public static class RepairInstanceMatcher
{
    public static bool Matches(AntiPatternType type, string findingSymbol, string instanceSymbol)
    {
        if (type == AntiPatternType.ObsoleteApiUsage)
        {
            // The deprecated callee (right of the arrow) is the stable identity of the instance.
            var fd = SimpleName(AfterArrow(findingSymbol));
            var id = SimpleName(AfterArrow(instanceSymbol));
            return fd.Length > 0 && id.Length > 0
                && (fd.Equals(id, StringComparison.OrdinalIgnoreCase)
                    || fd.Contains(id, StringComparison.OrdinalIgnoreCase)
                    || id.Contains(fd, StringComparison.OrdinalIgnoreCase));
        }

        return SimpleNameOverlap(findingSymbol, instanceSymbol);
    }

    private static string AfterArrow(string s)
    {
        var i = s.IndexOf('→');
        return (i >= 0 ? s[(i + 1)..] : s).Trim();
    }

    private static bool SimpleNameOverlap(string? a, string? b)
    {
        var sa = SimpleName(a);
        var sb = SimpleName(b);
        if (sa.Length == 0 || sb.Length == 0) return false;
        return sa.Contains(sb, StringComparison.OrdinalIgnoreCase)
            || sb.Contains(sa, StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>Unqualified name: drops namespace/type qualifiers, the arrow's right side, and any parameter list.</summary>
    private static string SimpleName(string? symbol)
    {
        if (string.IsNullOrWhiteSpace(symbol)) return string.Empty;
        var s = symbol.Trim();
        var arrow = s.IndexOf('→'); if (arrow >= 0) s = s[..arrow].Trim();
        var paren = s.IndexOf('('); if (paren >= 0) s = s[..paren];
        var dot   = s.LastIndexOf('.'); if (dot >= 0 && dot < s.Length - 1) s = s[(dot + 1)..];
        return s.Trim();
    }
}
