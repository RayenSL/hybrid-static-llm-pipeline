using HybridLens.Core.Models;
using HybridLens.Pipeline;

namespace HybridLens.Tests.Analysis;

public sealed class FactorialResultAnalyzerTests
{
    [Fact]
    public void UsesAllAssignedAttempts_ExcludesFirstBuildAndObsolete_AndTracksTokens()
    {
        var artifactA = Path.GetFullPath(Path.Combine(Path.GetTempPath(), "artifact-a.json"));
        var artifactB = Path.GetFullPath(Path.Combine(Path.GetTempPath(), "artifact-b.json"));
        var records = new List<RunRecord>
        {
            Record("single-ok", AntiPatternType.GodClass, grounded: true, control: "single_shot", tests: true,
                artifactA, build: true, resolved: true, input: 10, output: 5, calls: 1),
            Record("single-parse-fail", AntiPatternType.GodClass, grounded: true, control: "single_shot", tests: true,
                artifact: null, build: false, resolved: false, input: null, output: null, calls: 1),
            Record("iter-final", AntiPatternType.LongMethod, grounded: false, control: "iterative", tests: false,
                artifactB, build: true, resolved: true, input: 30, output: 20, calls: 3, snapshot: "final"),
            Record("iter-first", AntiPatternType.LongMethod, grounded: false, control: "iterative", tests: false,
                artifactB, build: true, resolved: false, input: 30, output: 20, calls: 3, snapshot: "first_build"),
            Record("obsolete", AntiPatternType.ObsoleteApiUsage, grounded: true, control: "single_shot", tests: true,
                artifactA, build: true, resolved: true, input: 999, output: 999, calls: 1)
        };
        var privateResults = new[]
        {
            Private(artifactA, passed: true),
            Private(artifactB, passed: false)
        };

        var result = FactorialResultAnalyzer.Analyze(records, privateResults);

        Assert.Equal(3, result.Attempts.Count); // includes unmaterialized ITT failure
        Assert.DoesNotContain(result.Attempts, a => a.RunId is "iter-first" or "obsolete");
        var grounded = result.Arms.Single(a => a.GroundingEnabled && a.VisibleTestsEnabled);
        Assert.Equal(2, grounded.AssignedAttempts);
        Assert.Equal(1, grounded.StrictSuccesses);
        Assert.Equal(0.5, grounded.StrictSuccessRate);
        Assert.Equal(1, grounded.TokenObservedAttempts);
        Assert.Equal(15, grounded.MeanTotalTokens);
        Assert.Equal(15, grounded.TotalTokensConsumed);
        Assert.Equal(1, grounded.MeanLlmCalls); // call attempts survive even when tokens are missing

        var iterative = result.Attempts.Single(a => a.RunId == "iter-final");
        Assert.False(iterative.PrivateTestPassed);
        Assert.False(iterative.StrictSuccess);
    }

    [Fact]
    public void MissingPrivateOutcomeForMaterializedAttempt_FailsIntegrityCheck()
    {
        var artifact = Path.GetFullPath(Path.Combine(Path.GetTempPath(), "missing-private.json"));
        var record = Record("run", AntiPatternType.GodClass, true, "single_shot", false,
            artifact, true, true, 1, 1, 1);

        var error = Assert.Throws<InvalidDataException>(() => FactorialResultAnalyzer.Analyze([record], []));
        Assert.Contains("missing private Layer-3 outcome", error.Message);
    }

    private static RunRecord Record(
        string id,
        AntiPatternType type,
        bool grounded,
        string control,
        bool tests,
        string? artifact,
        bool build,
        bool resolved,
        int? input,
        int? output,
        int calls,
        string? snapshot = null) => new()
    {
        RunId = id,
        Timestamp = DateTimeOffset.UtcNow,
        RunNumber = 1,
        AntiPatternType = type,
        FilePath = "Proj/Thing.cs",
        SymbolName = "Demo.Thing",
        Line = 1,
        Severity = Severity.Warning,
        ContextLevel = grounded ? ContextLevel.Structural : ContextLevel.Minimal,
        ModelName = "model",
        PromptVersion = "prompt",
        Architecture = grounded ? "grounded" : "ungrounded",
        GroundingEnabled = grounded,
        ControlStructure = control,
        VisibleTestsEnabled = tests,
        VisibleTestAvailable = tests,
        MaterializedSourceRef = artifact,
        MaterializedSourceSha256 = artifact is null ? null : "hash",
        InputTokens = input,
        OutputTokens = output,
        LlmCallCount = calls,
        BuildAttemptCount = 1,
        TestAttemptCount = tests ? 1 : 0,
        RawSystemPrompt = "system",
        RawUserPrompt = "user",
        BuildPassed = build,
        VerifiedRepairLadder = build
            ? resolved ? VerifiedRepairOutcome.Resolved : VerifiedRepairOutcome.BuildsUnresolved
            : null,
        VerifiedRepairSuccess = resolved,
        AgenticSnapshot = snapshot,
        ParseStatus = artifact is null ? ParseStatus.Failed : ParseStatus.Ok
    };

    private static PrivateLayer3Result Private(string artifact, bool passed) => new()
    {
        EvaluationId = Guid.NewGuid().ToString("N"),
        Timestamp = DateTimeOffset.UtcNow,
        ArtifactId = Guid.NewGuid().ToString("N"),
        ArtifactRef = artifact,
        SourceSha256 = "hash",
        OracleManifestVersion = "1.0.0",
        Evaluated = true,
        Passed = passed,
        PassingDrivers = passed ? 30 : 29,
        FailingDrivers = passed ? 0 : 1,
        DurationMs = 1
    };
}
