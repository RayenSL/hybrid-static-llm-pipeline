using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;
using HybridLens.Pipeline;

namespace HybridLens.Tests.Repair;

/// <summary>
/// Drives the four verified-repair ladder outcomes through <see cref="RepairVerifier"/> with a fake
/// applier, a fake re-measurer, and a fake build gate — so the orchestration, working-copy handling,
/// and record fields are tested without a real <c>dotnet build</c> or MSBuild workspace load.
/// </summary>
public sealed class RepairVerifierTests : IDisposable
{
    private const string ApplicableJson =
        """{"applicable":true,"reason_if_not":"","edited_file":"namespace Demo; public class Thing { public void M() { } }"}""";
    private const string UnapplicableJson =
        """{"applicable":false,"reason_if_not":"too vague to apply","edited_file":""}""";

    private readonly List<string> _tempRoots = [];

    [Fact]
    public async Task UnapplicableRepair_LaddersAtUnapplicable_AndDoesNotBuild()
    {
        var record = await RunOneAsync(UnapplicableJson, buildOk: true, stillTriggers: false);

        Assert.Equal(VerifiedRepairOutcome.Unapplicable, record.VerifiedRepairLadder);
        Assert.False(record.RepairApplicable);
        Assert.Null(record.BuildPassed);
        Assert.False(record.VerifiedRepairSuccess);
        Assert.Equal("too vague to apply", record.RepairUnapplicableReason);
        Assert.Equal(ParseStatus.Ok, record.ParseStatus);
    }

    [Fact]
    public async Task AppliedButBuildFails_LaddersAtBuildFails()
    {
        var record = await RunOneAsync(ApplicableJson, buildOk: false, stillTriggers: false);

        Assert.Equal(VerifiedRepairOutcome.BuildFails, record.VerifiedRepairLadder);
        Assert.True(record.RepairApplicable);
        Assert.False(record.BuildPassed);
        Assert.False(record.VerifiedRepairSuccess);
    }

    [Fact]
    public async Task BuildsButMetricStillFires_LaddersAtBuildsUnresolved()
    {
        var record = await RunOneAsync(ApplicableJson, buildOk: true, stillTriggers: true);

        Assert.Equal(VerifiedRepairOutcome.BuildsUnresolved, record.VerifiedRepairLadder);
        Assert.True(record.BuildPassed);
        Assert.False(record.VerifiedRepairSuccess);
        Assert.NotNull(record.RemeasuredMetrics);
    }

    [Fact]
    public async Task AppliesBuildsAndResolves_LaddersAtResolved_AndSucceeds()
    {
        var record = await RunOneAsync(ApplicableJson, buildOk: true, stillTriggers: false);

        Assert.Equal(VerifiedRepairOutcome.Resolved, record.VerifiedRepairLadder);
        Assert.True(record.BuildPassed);
        Assert.True(record.VerifiedRepairSuccess);
        Assert.Null(record.RemeasuredMetrics);
        Assert.Equal("claude-opus-4-8", record.ApplierModel);
        Assert.Equal("v1.0.0", record.ApplierPromptVersion);
        Assert.Equal("src1", record.SourceRunId);
        // Identity is carried from the generation row for grouping.
        Assert.Equal("hybrid", record.Architecture);
        Assert.Equal("gpt-5.4", record.ModelName);
    }

    [Fact]
    public async Task UnparseableApplierOutput_IsUnapplicable_AndFlagsParseFailure()
    {
        var record = await RunOneAsync("not even json", buildOk: true, stillTriggers: false);

        Assert.Equal(VerifiedRepairOutcome.Unapplicable, record.VerifiedRepairLadder);
        Assert.False(record.RepairApplicable);
        Assert.Equal(ParseStatus.Failed, record.ParseStatus);
        Assert.Equal(ErrorStatus.ParseFailure, record.ErrorStatus);
    }

    [Fact]
    public async Task ApplierApiFailure_RecordsApiFailure_WithNoLadder()
    {
        var record = await RunOneAsync(ApplicableJson, buildOk: true, stillTriggers: false, applierThrows: true);

        Assert.Null(record.VerifiedRepairLadder);
        Assert.Equal(ErrorStatus.ApiFailure, record.ErrorStatus);
        Assert.Equal(ParseStatus.NotAttempted, record.ParseStatus);
        Assert.Null(record.VerifiedRepairSuccess);
    }

    [Fact]
    public async Task FrozenCorpus_OriginalFileIsNeverModified()
    {
        var (sln, file, _) = MakeCorpus();
        var before = await File.ReadAllTextAsync(file);

        var verifier = new RepairVerifier(
            new RepairApplier(new FakeAdapter(ApplicableJson), "claude-opus-4-8"),
            new FakeMeasurer(stillTriggers: false),
            sln, buildTimeoutSeconds: 60,
            build: (_, _, _) => Task.FromResult((true, "ok")));

        var store = new CollectingRunStore();
        await verifier.RunAsync([Candidate(file)], store, TextWriter.Null, CancellationToken.None);

        Assert.Equal(before, await File.ReadAllTextAsync(file));   // edit went to the working copy, not the corpus
    }

    // ── Harness ────────────────────────────────────────────────────────────────

    private async Task<RunRecord> RunOneAsync(
        string applierContent, bool buildOk, bool stillTriggers, bool applierThrows = false)
    {
        var (sln, file, _) = MakeCorpus();
        var verifier = new RepairVerifier(
            new RepairApplier(new FakeAdapter(applierContent, applierThrows), "claude-opus-4-8"),
            new FakeMeasurer(stillTriggers),
            sln, buildTimeoutSeconds: 60,
            build: (_, _, _) => Task.FromResult((buildOk, "build output")));

        var store = new CollectingRunStore();
        await verifier.RunAsync([Candidate(file)], store, TextWriter.Null, CancellationToken.None);
        return Assert.Single(store.Records);
    }

    private (string Sln, string File, string Root) MakeCorpus()
    {
        var root = Path.Combine(Path.GetTempPath(), $"hl-verify-test-{Guid.NewGuid():N}");
        Directory.CreateDirectory(Path.Combine(root, "src", "Demo"));
        _tempRoots.Add(root);

        var sln  = Path.Combine(root, "Corpus.sln");
        File.WriteAllText(sln, "// fake solution");
        var file = Path.Combine(root, "src", "Demo", "Thing.cs");
        File.WriteAllText(file, "namespace Demo; public class Thing { }");
        return (sln, file, root);
    }

    private static RepairCandidate Candidate(string file) => new()
    {
        SourceRunId   = "src1",
        Type          = AntiPatternType.GodClass,
        FilePath      = file,
        SymbolName    = "Demo.Thing",
        Line          = 1,
        Severity      = Severity.Critical,
        ContextLevel  = ContextLevel.Minimal,
        ModelName     = "gpt-5.4",
        PromptVersion = "v1.1.0",
        Architecture  = "hybrid",
        RunNumber     = 1,
        RepairText    = "Extract a RefundService class."
    };

    public void Dispose()
    {
        foreach (var root in _tempRoots)
            try { if (Directory.Exists(root)) Directory.Delete(root, recursive: true); } catch { /* best effort */ }
    }

    // ── Fakes ──────────────────────────────────────────────────────────────────

    private sealed class FakeAdapter(string content, bool throws = false) : ILlmAdapter
    {
        public Task<LlmResponse> CompleteAsync(LlmRequest request, CancellationToken cancellationToken = default)
            => throws
                ? throw new InvalidOperationException("applier API unavailable")
                : Task.FromResult(new LlmResponse { Content = content, InputTokens = 10, OutputTokens = 20 });
    }

    private sealed class FakeMeasurer(bool stillTriggers) : IRepairMeasurer
    {
        public Task<RemeasureResult> RemeasureAsync(
            AntiPatternType type, string workingFilePath, string instanceSymbol, CancellationToken cancellationToken = default)
            => Task.FromResult(new RemeasureResult(
                stillTriggers,
                stillTriggers ? new Dictionary<string, double> { ["WMC"] = 60, ["ATFD"] = 8, ["TCC"] = 0.1 } : null));
    }

    private sealed class CollectingRunStore : IRunStore
    {
        public List<RunRecord> Records { get; } = [];
        public Task AppendAsync(RunRecord record, CancellationToken cancellationToken = default)
        {
            Records.Add(record);
            return Task.CompletedTask;
        }
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
