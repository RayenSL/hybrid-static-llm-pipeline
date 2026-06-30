using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;
using HybridLens.Pipeline;

namespace HybridLens.Tests.Agentic;

/// <summary>
/// The agentic arm (§4.4.1, Appendix E v2.0.0) runs an autonomous edit→build loop and writes two row
/// types per (file × run): detection finding rows (recall/precision) and verified-repair rows scoring
/// the FINAL edited solution directly (build gate → re-measure; no separate applier). These tests drive
/// the loop with a scripted adapter, a fake compiler, and a fake re-measurer so no real build runs.
/// </summary>
public sealed class AgenticRunnerTests : IDisposable
{
    private readonly List<string> _tempDirs = [];

    private static string EditWithGodClass(string symbol, int line) =>
        $$"""
        {"action":"edit_and_build","edited_file":"// edited source","findings":[
          {"anti_pattern":"GodClass","location":{"symbol":"{{symbol}}","line":{{line}}},
           "explanation":"too many responsibilities","quality_impact":"Quality impact:\n- Maintainability: low","remediation":"extract class"}]}
        """;

    // A completion turn that restates its final findings (the protocol asks the agent to do this).
    private static string CompleteWithGodClass(string symbol, int line) =>
        $$"""
        {"action":"complete","edited_file":"","findings":[
          {"anti_pattern":"GodClass","location":{"symbol":"{{symbol}}","line":{{line}}},
           "explanation":"too many responsibilities","quality_impact":"Quality impact:\n- Maintainability: low","remediation":"extract class"}]}
        """;

    // Correct location but WRONG type label (LongMethod reported for a GodClass instance).
    private static string CompleteWithWrongType(string symbol, int line) =>
        $$"""
        {"action":"complete","edited_file":"","findings":[
          {"anti_pattern":"LongMethod","location":{"symbol":"{{symbol}}","line":{{line}}},
           "explanation":"e","quality_impact":"","remediation":"r"}]}
        """;

    [Fact]
    public async Task Completes_EmitsMatchedFinding_AndResolvedVerifiedRepair()
    {
        var (sln, instanceFile, known) = MakeCorpus("Demo.Thing", 1);

        var store  = new CollectingRunStore();
        var runner = new AgenticRunner(
            new ScriptedAdapter(EditWithGodClass("Demo.Thing", 1), CompleteWithGodClass("Demo.Thing", 1)),
            "gpt-5.4",
            new FakeMeasurer(stillTriggers: false),                 // repair resolved the metric
            sln, iterationBudget: 6, buildTimeoutSeconds: 30,
            build: (_, _, _) => Task.FromResult((true, "Build succeeded")));

        await runner.RunAsync(known, runs: 1, store, 120_000, TrajDir(), TextWriter.Null, CancellationToken.None,
            sweepFiles: [instanceFile]);

        var finding = store.Records.Single(r => r.VerifiedRepairLadder is null);
        Assert.Equal("agentic", finding.Architecture);
        Assert.Equal("v2.0.0", finding.PromptVersion);
        Assert.False(finding.IsSpurious);
        Assert.NotNull(finding.MatchedInstanceId);
        Assert.Equal(1, finding.AgenticIterations);
        Assert.False(finding.AgenticBudgetExhausted);
        Assert.NotNull(finding.AgenticTrajectoryRef);

        var verified = store.Records.Single(r => r.VerifiedRepairLadder is not null);
        Assert.Equal(VerifiedRepairOutcome.Resolved, verified.VerifiedRepairLadder);
        Assert.True(verified.VerifiedRepairSuccess);
        Assert.True(verified.BuildPassed);
        Assert.True(verified.AgenticRecovered);
        Assert.Null(verified.ApplierModel);                          // agent is its own applier (§4.7.1)
    }

    [Fact]
    public async Task BudgetExhausted_StopsAfterBudgetBuilds()
    {
        var (sln, instanceFile, known) = MakeCorpus("Demo.Thing", 1);

        var store  = new CollectingRunStore();
        var runner = new AgenticRunner(
            new ScriptedAdapter(EditWithGodClass("Demo.Thing", 1)),  // never declares completion
            "gpt-5.4",
            new FakeMeasurer(stillTriggers: true),                   // still triggers → unresolved
            sln, iterationBudget: 2, buildTimeoutSeconds: 30,
            build: (_, _, _) => Task.FromResult((true, "Build succeeded")));

        await runner.RunAsync(known, runs: 1, store, 120_000, TrajDir(), TextWriter.Null, CancellationToken.None,
            sweepFiles: [instanceFile]);

        var verified = store.Records.Single(r => r.VerifiedRepairLadder is not null);
        Assert.Equal(2, verified.AgenticIterations);                 // exactly the budget
        Assert.True(verified.AgenticBudgetExhausted);
        Assert.Equal(VerifiedRepairOutcome.BuildsUnresolved, verified.VerifiedRepairLadder);
        Assert.False(verified.VerifiedRepairSuccess);
    }

    [Fact]
    public async Task SpuriousFindingOnCleanFile_EmitsNoVerifiedRow()
    {
        // A file with no seeded instance: any detection on it is a precision failure (§4.5.1).
        var dir = NewTempDir();
        var sln = Path.Combine(dir, "Corpus.sln");
        File.WriteAllText(sln, "Microsoft Visual Studio Solution File");
        var cleanFile = Path.Combine(dir, "Other.cs");
        File.WriteAllText(cleanFile, "namespace Demo; public class Other { }");

        var store  = new CollectingRunStore();
        var runner = new AgenticRunner(
            new ScriptedAdapter("""{"action":"complete","edited_file":"","findings":[{"anti_pattern":"GodClass","location":{"symbol":"Demo.Other","line":1},"explanation":"e","quality_impact":"","remediation":"r"}]}"""),
            "gpt-5.4",
            new FakeMeasurer(stillTriggers: false),
            sln, iterationBudget: 6, buildTimeoutSeconds: 30,
            build: (_, _, _) => Task.FromResult((true, "ok")));

        await runner.RunAsync(knownInstances: [], runs: 1, store, 120_000, TrajDir(), TextWriter.Null,
            CancellationToken.None, sweepFiles: [cleanFile]);

        var rec = Assert.Single(store.Records);                      // only the finding row; no verified row
        Assert.True(rec.IsSpurious);
        Assert.Null(rec.MatchedInstanceId);
        Assert.Null(rec.VerifiedRepairLadder);
        Assert.Equal(0, rec.AgenticIterations);                      // declared complete without editing
    }

    [Fact]
    public async Task FinalBuildFails_LaddersToBuildFails()
    {
        var (sln, instanceFile, known) = MakeCorpus("Demo.Thing", 1);

        var store  = new CollectingRunStore();
        var runner = new AgenticRunner(
            new ScriptedAdapter(EditWithGodClass("Demo.Thing", 1), CompleteWithGodClass("Demo.Thing", 1)),
            "gpt-5.4",
            new FakeMeasurer(stillTriggers: false),                  // should be ignored — build failed
            sln, iterationBudget: 6, buildTimeoutSeconds: 30,
            build: (_, _, _) => Task.FromResult((false, "error CS1002: ; expected")));

        await runner.RunAsync(known, runs: 1, store, 120_000, TrajDir(), TextWriter.Null, CancellationToken.None,
            sweepFiles: [instanceFile]);

        var verified = store.Records.Single(r => r.VerifiedRepairLadder is not null);
        Assert.Equal(VerifiedRepairOutcome.BuildFails, verified.VerifiedRepairLadder);
        Assert.False(verified.BuildPassed);
        Assert.False(verified.VerifiedRepairSuccess);
    }

    [Fact]
    public async Task WrongTypeButCorrectLocation_StillMatches()
    {
        // §4.5.1 match rule is LOCATION-only: a correctly-localised finding mislabelled by type must
        // match (not be scored as a miss + a spurious false positive).
        var (sln, instanceFile, known) = MakeCorpus("Demo.Thing", 1);  // a GodClass instance

        var store  = new CollectingRunStore();
        var runner = new AgenticRunner(
            new ScriptedAdapter(CompleteWithWrongType("Demo.Thing", 1)),  // agent labels it LongMethod
            "gpt-5.4",
            new FakeMeasurer(stillTriggers: false),
            sln, iterationBudget: 6, buildTimeoutSeconds: 30,
            build: (_, _, _) => Task.FromResult((true, "ok")));

        await runner.RunAsync(known, runs: 1, store, 120_000, TrajDir(), TextWriter.Null, CancellationToken.None,
            sweepFiles: [instanceFile]);

        var finding = store.Records.Single(r => r.VerifiedRepairLadder is null);
        Assert.False(finding.IsSpurious);                                // matched on location despite wrong type
        Assert.NotNull(finding.MatchedInstanceId);
        Assert.Equal(AntiPatternType.GodClass, finding.AntiPatternType); // recorded as the instance's true type
        Assert.Equal("LongMethod", finding.LlmReportedAntiPattern);      // the agent's raw label kept for analysis

        var verified = store.Records.Single(r => r.VerifiedRepairLadder is not null);
        Assert.True(verified.AgenticRecovered);                          // the instance counts as recovered
    }

    [Fact]
    public async Task ApiError_IsNotMarkedBudgetExhausted()
    {
        var (sln, instanceFile, known) = MakeCorpus("Demo.Thing", 1);

        var store  = new CollectingRunStore();
        var runner = new AgenticRunner(
            new ThrowingAdapter(),                                       // first turn throws
            "gpt-5.4",
            new FakeMeasurer(stillTriggers: true),
            sln, iterationBudget: 6, buildTimeoutSeconds: 30,
            build: (_, _, _) => Task.FromResult((true, "ok")));

        await runner.RunAsync(known, runs: 1, store, 120_000, TrajDir(), TextWriter.Null, CancellationToken.None,
            sweepFiles: [instanceFile]);

        var verified = store.Records.Single(r => r.VerifiedRepairLadder is not null);
        Assert.False(verified.AgenticBudgetExhausted);                   // an API failure is NOT budget exhaustion (§4.8.1)
        Assert.Equal(ErrorStatus.ApiFailure, verified.ErrorStatus);
        Assert.Equal(0, verified.AgenticIterations);
    }

    [Fact]
    public async Task BuildThrows_IsRecordedAsError_AndDoesNotCrashTheRun()
    {
        var (sln, instanceFile, known) = MakeCorpus("Demo.Thing", 1);

        var store  = new CollectingRunStore();
        var runner = new AgenticRunner(
            new ScriptedAdapter(EditWithGodClass("Demo.Thing", 1)),      // requests a build
            "gpt-5.4",
            new FakeMeasurer(stillTriggers: false),
            sln, iterationBudget: 6, buildTimeoutSeconds: 30,
            build: (_, _, _) => throw new InvalidOperationException("dotnet not found"));

        // Must not throw out of RunAsync.
        await runner.RunAsync(known, runs: 1, store, 120_000, TrajDir(), TextWriter.Null, CancellationToken.None,
            sweepFiles: [instanceFile]);

        var verified = store.Records.Single(r => r.VerifiedRepairLadder is not null);
        Assert.Equal(ErrorStatus.Unknown, verified.ErrorStatus);
        Assert.False(verified.AgenticBudgetExhausted);
    }

    // ── Helpers ─────────────────────────────────────────────────────────────────

    private (string Sln, string InstanceFile, KnownInstance[] Known) MakeCorpus(string symbol, int line)
    {
        var dir = NewTempDir();
        var sln = Path.Combine(dir, "Corpus.sln");
        File.WriteAllText(sln, "Microsoft Visual Studio Solution File");

        var projDir = Path.Combine(dir, "Proj");
        Directory.CreateDirectory(projDir);
        var instanceFile = Path.Combine(projDir, "Thing.cs");
        File.WriteAllText(instanceFile, "namespace Demo; public class Thing { }");

        var known = new[]
        {
            KnownInstance.Create(AntiPatternType.GodClass, instanceFile, symbol, line, Severity.Critical, "public class Thing { }")
        };
        return (sln, instanceFile, known);
    }

    private string NewTempDir()
    {
        var dir = Path.Combine(Path.GetTempPath(), $"hl-agentic-{Guid.NewGuid():N}");
        Directory.CreateDirectory(dir);
        _tempDirs.Add(dir);
        return dir;
    }

    private string TrajDir()
    {
        var dir = Path.Combine(NewTempDir(), "traj");
        Directory.CreateDirectory(dir);
        return dir;
    }

    public void Dispose()
    {
        foreach (var d in _tempDirs)
            try { if (Directory.Exists(d)) Directory.Delete(d, recursive: true); } catch { /* best effort */ }
    }

    /// <summary>Returns scripted turn JSON in order; repeats the last one once the script is exhausted.</summary>
    private sealed class ScriptedAdapter(params string[] responses) : ILlmAdapter
    {
        private int _i;

        public Task<LlmResponse> CompleteAsync(LlmRequest request, CancellationToken cancellationToken = default)
            => throw new NotSupportedException("agentic uses the conversation overload");

        public Task<LlmResponse> CompleteAsync(LlmConversation conversation, CancellationToken cancellationToken = default)
        {
            var content = responses[Math.Min(_i, responses.Length - 1)];
            _i++;
            return Task.FromResult(new LlmResponse { Content = content, InputTokens = 7, OutputTokens = 11 });
        }
    }

    private sealed class ThrowingAdapter : ILlmAdapter
    {
        public Task<LlmResponse> CompleteAsync(LlmRequest request, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public Task<LlmResponse> CompleteAsync(LlmConversation conversation, CancellationToken cancellationToken = default)
            => throw new InvalidOperationException("simulated API failure");
    }

    private sealed class FakeMeasurer(bool stillTriggers) : IRepairMeasurer
    {
        public Task<RemeasureResult> RemeasureAsync(
            AntiPatternType type, string workingFilePath, string instanceSymbol, CancellationToken cancellationToken = default)
            => Task.FromResult(new RemeasureResult(stillTriggers,
                stillTriggers ? new Dictionary<string, double> { ["WMC"] = 60 } : null));
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
