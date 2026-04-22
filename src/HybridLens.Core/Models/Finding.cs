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
}
