namespace HybridLens.Core.Models;

public sealed record FactorialAttemptOutcome
{
    public required string RunId { get; init; }
    public required string InstanceKey { get; init; }
    public required AntiPatternType AntiPatternType { get; init; }
    public required bool GroundingEnabled { get; init; }
    public required string ControlStructure { get; init; }
    public required bool VisibleTestsEnabled { get; init; }
    public required bool VisibleTestAvailable { get; init; }
    public required bool Materialized { get; init; }
    public required bool BuildPassed { get; init; }
    public required bool MetricResolved { get; init; }
    public bool? PrivateTestPassed { get; init; }
    public required bool StrictSuccess { get; init; }
    public int? InputTokens { get; init; }
    public int? OutputTokens { get; init; }
    public int? TotalTokens { get; init; }
    public int? LlmCalls { get; init; }
    public int? BuildAttempts { get; init; }
    public int? TestAttempts { get; init; }
    public double? TestDurationMs { get; init; }
    public double? RepairDurationMs { get; init; }
    public string? MaterializedSourceRef { get; init; }
}

public sealed record FactorialArmSummary
{
    public required bool GroundingEnabled { get; init; }
    public required string ControlStructure { get; init; }
    public required bool VisibleTestsEnabled { get; init; }
    public required int AssignedAttempts { get; init; }
    public required int MaterializedAttempts { get; init; }
    public required int BuildPassedAttempts { get; init; }
    public required int MetricResolvedAttempts { get; init; }
    public required int PrivatePassedAttempts { get; init; }
    public required int StrictSuccesses { get; init; }
    public required double StrictSuccessRate { get; init; }
    public required double VisibleTestAvailabilityRate { get; init; }
    public int TokenObservedAttempts { get; init; }
    public double? MeanInputTokens { get; init; }
    public double? MeanOutputTokens { get; init; }
    public double? MeanTotalTokens { get; init; }
    public long? TotalTokensConsumed { get; init; }
    public double? MeanLlmCalls { get; init; }
    public double? MeanBuildAttempts { get; init; }
    public double? MeanTestAttempts { get; init; }
    public double? MeanTestDurationMs { get; init; }
    public double? MeanRepairDurationMs { get; init; }
}

public sealed record FactorialAnalysisResult(
    IReadOnlyList<FactorialAttemptOutcome> Attempts,
    IReadOnlyList<FactorialArmSummary> Arms);
