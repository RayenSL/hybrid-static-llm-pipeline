using HybridLens.Core.Models;

namespace HybridLens.Core.QualityAttributes;

/// <summary>
/// Static, literature-derived mapping from anti-pattern types to the ISO/IEC 25010
/// software-quality attributes they are commonly associated with degrading.
///
/// <para>
/// <b>Thesis role:</b> this mapping is treated as <i>ground truth for evaluation</i>.
/// It is intentionally not discovered, learned, or injected into LLM prompts.
/// The pipeline records the expected attributes on each <see cref="Finding"/> so
/// that, after the LLM responds, we can measure whether the LLM independently
/// inferred those same attributes.
/// </para>
///
/// <para>
/// <b>Sources:</b>
/// <list type="bullet">
///   <item>Fowler, M. (1999). <i>Refactoring</i>.</item>
///   <item>Lanza, M. &amp; Marinescu, R. (2006). <i>Object-Oriented Metrics in Practice</i>.</item>
///   <item>Tufano, M. et al. (2017). <i>When and Why Your Code Starts to Smell Bad</i>.</item>
/// </list>
/// </para>
///
/// <para>
/// <b>ISO/IEC 25010 attribute names</b> are kept as <see cref="string"/> constants so
/// they appear identically wherever the pipeline writes them — both for direct
/// matching against LLM output and for stable JSONL/CSV columns.
/// </para>
/// </summary>
public static class QualityAttributeMap
{
    // ── Canonical attribute names (British spelling for "analysability"). ────
    public const string Maintainability = "Maintainability";
    public const string Modularity      = "Modularity";
    public const string Analysability   = "Analysability";
    public const string Modifiability   = "Modifiability";
    public const string Testability     = "Testability";
    public const string Security        = "Security";
    public const string Reliability     = "Reliability";
    public const string Compatibility   = "Compatibility";

    /// <summary>All canonical attribute names recognised by the alignment scorer.</summary>
    public static readonly IReadOnlyList<string> KnownAttributes = new[]
    {
        Maintainability, Modularity, Analysability, Modifiability,
        Testability, Security, Reliability, Compatibility
    };

    /// <summary>Ground-truth map: which attributes each anti-pattern is expected to degrade.</summary>
    public static readonly IReadOnlyDictionary<AntiPatternType, IReadOnlyList<string>> Map =
        new Dictionary<AntiPatternType, IReadOnlyList<string>>
        {
            [AntiPatternType.GodClass]         = new[] { Maintainability, Modularity, Analysability, Modifiability },
            [AntiPatternType.LongMethod]       = new[] { Maintainability, Analysability, Testability, Modifiability },
            [AntiPatternType.ObsoleteApiUsage] = new[] { Maintainability, Security, Reliability, Compatibility }
        };

    /// <summary>Convenience lookup; returns an empty list for unknown anti-pattern types.</summary>
    public static IReadOnlyList<string> ForType(AntiPatternType type)
        => Map.TryGetValue(type, out var attrs) ? attrs : Array.Empty<string>();
}
