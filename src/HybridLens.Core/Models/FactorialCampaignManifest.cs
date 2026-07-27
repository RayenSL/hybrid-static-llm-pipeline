namespace HybridLens.Core.Models;

/// <summary>A frozen, randomized 2 x 2 x 2 execution schedule for the repair experiment.</summary>
public sealed record FactorialCampaignManifest
{
    public required string Version { get; init; }
    public required string CampaignId { get; init; }
    public required DateTimeOffset CreatedAt { get; init; }
    public required string CodeRevision { get; init; }
    public required int RandomizationSeed { get; init; }
    public required string ModelName { get; init; }
    public required int Repetitions { get; init; }
    public required int IterationBudget { get; init; }
    public required int BuildTimeoutSeconds { get; init; }
    public required int MaxInputTokenGuard { get; init; }
    public required string TargetSolution { get; init; }
    public required string BaselineSource { get; init; }
    public required string BaselineSha256 { get; init; }
    public required IReadOnlyList<FactorialCampaignAssignment> Assignments { get; init; }
}

/// <summary>One independently executed treatment assignment in a frozen campaign.</summary>
public sealed record FactorialCampaignAssignment
{
    public required int Order { get; init; }
    public required string AssignmentId { get; init; }
    public required string BlockId { get; init; }
    public required int RunNumber { get; init; }
    public required AntiPatternType AntiPatternType { get; init; }
    public required string FilePath { get; init; }
    public required string SymbolName { get; init; }
    public required int Line { get; init; }
    public required int TargetEndLine { get; init; }
    public required Severity Severity { get; init; }
    public string? Snippet { get; init; }
    public IReadOnlyDictionary<string, double> Metrics { get; init; } = new Dictionary<string, double>();
    public required string PristineSourceSha256 { get; init; }
    public required bool GroundingEnabled { get; init; }
    public required string ControlStructure { get; init; }
    public required bool VisibleTestsEnabled { get; init; }
    public string? VisibleTestArtifactRef { get; init; }
    public string? VisibleTestSha256 { get; init; }
    public required string PromptVersion { get; init; }
}

/// <summary>Crash-safe ledger row written after one frozen assignment succeeds or fails.</summary>
public sealed record FactorialCampaignExecutionRecord
{
    public required string CampaignId { get; init; }
    public required string AssignmentId { get; init; }
    public required int Order { get; init; }
    public required DateTimeOffset Timestamp { get; init; }
    public required bool Completed { get; init; }
    public required string TraceFile { get; init; }
    public IReadOnlyList<string> RunIds { get; init; } = [];
    public string? Error { get; init; }
}
