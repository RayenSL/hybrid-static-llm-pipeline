using System.Text.RegularExpressions;
using HybridLens.Core.Models;
using HybridLens.Core.QualityAttributes;

namespace HybridLens.Pipeline;

/// <summary>
/// Lexical extraction of ISO/IEC 25010 quality attributes from LLM output, plus the
/// 0/1/null alignment metric. Shared by the hybrid pipeline and the LLM-only runner so
/// both score attribute mentions identically.
/// </summary>
public static class QualityAttributeExtraction
{
    /// <summary>Synonym map per thesis §B.7.3 — canonical attribute → accepted phrasings.</summary>
    private static readonly IReadOnlyDictionary<string, string[]> Synonyms =
        new Dictionary<string, string[]>(StringComparer.Ordinal)
        {
            [QualityAttributeMap.Maintainability] = new[]
                { "Maintainability", "maintenance burden", "maintenance cost", "easy to maintain", "hard to maintain", "difficult to maintain" },
            [QualityAttributeMap.Modifiability] = new[]
                { "Modifiability", "changeability", "easy to change", "hard to change", "impact of changes" },
            [QualityAttributeMap.Analysability] = new[]
                { "Analysability", "Analyzability", "understandability", "readability", "comprehensibility", "cognitive complexity" },
            [QualityAttributeMap.Testability] = new[]
                { "Testability", "easy to test", "hard to test", "unit test coverage difficulty", "testing difficulty" },
            [QualityAttributeMap.Modularity] = new[]
                { "Modularity", "separation of concerns", "coupling", "cohesion" },
            [QualityAttributeMap.Security] = new[]
                { "Security", "vulnerability", "attack surface", "security risk" },
            [QualityAttributeMap.Reliability] = new[]
                { "Reliability", "stability", "fault tolerance", "robustness" },
            [QualityAttributeMap.Compatibility] = new[]
                { "Compatibility", "interoperability", "deprecation", "version compatibility" }
        };

    /// <summary>Canonical (British) attribute names mentioned anywhere in <paramref name="text"/>, alphabetical.</summary>
    public static IReadOnlyList<string> ExtractMentioned(string? text)
    {
        if (string.IsNullOrWhiteSpace(text))
            return Array.Empty<string>();

        var found = new HashSet<string>(StringComparer.Ordinal);
        foreach (var (canonical, terms) in Synonyms)
            foreach (var term in terms)
                if (Regex.IsMatch(text, $@"\b{Regex.Escape(term)}\b", RegexOptions.IgnoreCase))
                {
                    found.Add(canonical);
                    break;
                }

        return found.OrderBy(s => s, StringComparer.Ordinal).ToList();
    }

    /// <summary>1 = ≥1 expected attribute mentioned; 0 = none; null = no usable output or unknown type.</summary>
    public static int? ComputeAlignment(
        bool parsedOk, IReadOnlyList<string> expected, IReadOnlyList<string> mentioned)
    {
        if (!parsedOk)          return null;
        if (expected.Count == 0) return null;
        return expected.Any(e => mentioned.Contains(e, StringComparer.OrdinalIgnoreCase)) ? 1 : 0;
    }
}
