namespace HybridLens.Core.Models;

public sealed record AnalysisResult
{
    public required string ProjectPath { get; init; }
    public required IReadOnlyList<Finding> Findings { get; init; }
    public DateTimeOffset AnalysedAt { get; init; } = DateTimeOffset.UtcNow;
}
