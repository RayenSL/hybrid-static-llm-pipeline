using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

/// <summary>Location-only matching; a reported anti-pattern type only breaks ties.</summary>
internal static class AgenticFindingMatcher
{
    public static KnownInstance? Match(ParsedAgenticFinding f, List<KnownInstance> known)
    {
        var reportedType = NormaliseType(f.AntiPattern);   // may be null (missing/garbled label)
        KnownInstance? locationMatch = null;

        foreach (var k in known)
        {
            var lineInRange   = f.Line >= k.Line && f.Line <= k.EndLine;
            var symbolOverlap = SimpleNameOverlap(f.Symbol, k.SymbolName);
            if (!lineInRange && !symbolOverlap) continue;  // location overlap is the match rule

            if (reportedType is not null && k.Type == reportedType)
                return k;                                  // best: location overlap AND same reported type
            locationMatch ??= k;                           // fallback: location overlap regardless of type
        }
        return locationMatch;
    }

    private static bool SimpleNameOverlap(string? a, string? b)
    {
        var sa = SimpleName(a);
        var sb = SimpleName(b);
        if (sa.Length == 0 || sb.Length == 0) return false;
        return sa.Contains(sb, StringComparison.OrdinalIgnoreCase)
            || sb.Contains(sa, StringComparison.OrdinalIgnoreCase);
    }

    private static string SimpleName(string? symbol)
    {
        if (string.IsNullOrWhiteSpace(symbol)) return string.Empty;
        var s = symbol.Trim();
        var paren = s.IndexOf('(');
        if (paren >= 0) s = s[..paren];
        var dot = s.LastIndexOf('.');
        if (dot >= 0 && dot < s.Length - 1) s = s[(dot + 1)..];
        var arrow = s.IndexOf('→');
        if (arrow >= 0) s = s[(arrow + 1)..].Trim();
        return s;
    }

    public static AntiPatternType? NormaliseType(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return null;
        var t = raw.Replace(" ", "").Replace("_", "").Replace("-", "").ToLowerInvariant();
        return t switch
        {
            "godclass"                          => AntiPatternType.GodClass,
            "longmethod"                        => AntiPatternType.LongMethod,
            "obsoleteapiusage" or "obsoleteapi" => AntiPatternType.ObsoleteApiUsage,
            _                                   => null
        };
    }

}
