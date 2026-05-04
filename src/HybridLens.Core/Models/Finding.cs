namespace HybridLens.Core.Models;

public sealed record Finding
{
    public required AntiPatternType Type { get; init; }
    public required Severity Severity { get; init; }
    public required string FilePath { get; init; }
    public required string SymbolName { get; init; }
    public required int Line { get; init; }

    /// <summary>Raw code snippet at the finding location.</summary>
    public string? Snippet { get; init; }

    /// <summary>Detector-specific numeric metrics (e.g. method line count, field count).</summary>
    public IReadOnlyDictionary<string, double> Metrics { get; init; } = new Dictionary<string, double>();

    /// <summary>
    /// ISO/IEC 25010 software-quality attributes this anti-pattern is expected to degrade,
    /// per the literature-derived mapping in <see cref="QualityAttributes.QualityAttributeMap"/>.
    /// Used as ground truth for evaluation; never injected into LLM prompts.
    /// </summary>
    public IReadOnlyList<string> ExpectedQualityAttributes { get; init; } = Array.Empty<string>();
}
