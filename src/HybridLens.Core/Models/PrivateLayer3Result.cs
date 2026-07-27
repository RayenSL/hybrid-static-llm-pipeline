namespace HybridLens.Core.Models;

/// <summary>
/// Blinded private-oracle outcome keyed only to the opaque common source artefact. Experimental
/// factors are joined later and are deliberately absent from this evaluator output.
/// </summary>
public sealed record PrivateLayer3Result
{
    public required string EvaluationId { get; init; }
    public required DateTimeOffset Timestamp { get; init; }
    public required string ArtifactId { get; init; }
    public required string ArtifactRef { get; init; }
    public required string SourceSha256 { get; init; }
    public required string OracleManifestVersion { get; init; }
    public required bool Evaluated { get; init; }
    public bool? Passed { get; init; }
    public int? PassingDrivers { get; init; }
    public int? FailingDrivers { get; init; }
    public double DurationMs { get; init; }
    public string? NotRunReason { get; init; }
    public string? OutputTail { get; init; }
}
