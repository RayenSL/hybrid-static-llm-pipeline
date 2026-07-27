namespace HybridLens.Core.Models;

/// <summary>Common frozen final production source consumed by later quality and private Layer-3 evaluation.</summary>
public sealed record MaterializedSourceArtifact
{
    public required string ArtifactId { get; init; }
    public required DateTimeOffset Timestamp { get; init; }
    public required string Architecture { get; init; }
    public required bool GroundingEnabled { get; init; }
    public required string ControlStructure { get; init; }
    public required bool VisibleTestsEnabled { get; init; }
    public required bool VisibleTestAvailable { get; init; }
    public required int RunNumber { get; init; }
    public required string RelativeFile { get; init; }
    public required string SourceSha256 { get; init; }
    public required string FinalSource { get; init; }
    public string? VisibleTestArtifactRef { get; init; }
    public string? VisibleTestSha256 { get; init; }
    public bool? BuildPassed { get; init; }
    public bool? VisibleTestPassed { get; init; }
}
