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

    /// <summary>
    /// The condition signatures every block must contain, each written
    /// <c>grounding|control_structure|visible_test</c> — for example <c>False|single_shot|False</c>.
    /// Null means the classic eight-cell 2x2x2 factorial, which is what every frozen confirmatory
    /// manifest relies on. Supplying a smaller set is what lets a reduced design, such as a
    /// grounding-only transfer probe, run through the same machinery.
    /// </summary>
    public IReadOnlyList<string>? ConditionSignatures { get; init; }

    /// <summary>
    /// Extra arguments appended to every <c>dotnet build</c> of the build gate. Needed for
    /// solutions that cannot restore in the execution environment, where
    /// <c>--no-restore -p:NuGetAudit=false</c> builds against an already-populated package cache.
    /// Empty or null keeps the default argument list.
    /// </summary>
    public IReadOnlyList<string>? BuildArguments { get; init; }

    /// <summary>
    /// Directories excluded when an assignment's isolated working copy is made, matched on any path
    /// segment. Null keeps the default <c>bin obj .git .vs .idea</c>.
    ///
    /// A solution built with <c>--no-restore</c> must retain <c>obj</c>, because that is where
    /// <c>project.assets.json</c> lives and MSBuild fails with NETSDK1004 without it. Retaining it is
    /// safe: the copied assets file points at the machine-wide package cache, while the compiled
    /// sources and project files are the copy's own, so the repair under test is what gets built.
    /// </summary>
    public IReadOnlyList<string>? WorkingCopySkipDirectories { get; init; }

    /// <summary>
    /// Free-text label for the experiment this manifest belongs to, recorded so a reduced design is
    /// never mistaken for the confirmatory factorial during analysis.
    /// </summary>
    public string? Kind { get; init; }

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
public sealed record FactorialCampaignExecutionRecord : ICampaignExecutionRecord
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
