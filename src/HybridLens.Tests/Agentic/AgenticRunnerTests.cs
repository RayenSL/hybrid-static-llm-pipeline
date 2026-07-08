using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;
using HybridLens.Pipeline;

namespace HybridLens.Tests.Agentic;

/// <summary>
/// The iterative arms (§4.4.1, Appendix E v2.0.0) run an autonomous edit→build loop. The ungrounded
/// agentic arm writes detection finding rows (recall/precision) plus, per known instance, TWO verified-
/// repair rows — a "final" snapshot and a "first_build" snapshot (the single-pass cell of the 2×2). The
/// grounded-iterative arm seeds the opening prompt with the analyser's finding block, writes no detection
/// rows, and emits the same two verified snapshots. These tests drive the loop with a scripted adapter, a
/// fake compiler, and a fake/ content-sensitive re-measurer so no real build runs.
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

        var verified = store.Records.Single(r => r.VerifiedRepairLadder is not null && r.AgenticSnapshot == "final");
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

        var verified = store.Records.Single(r => r.VerifiedRepairLadder is not null && r.AgenticSnapshot == "final");
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

        var verified = store.Records.Single(r => r.VerifiedRepairLadder is not null && r.AgenticSnapshot == "final");
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

        var verified = store.Records.Single(r => r.VerifiedRepairLadder is not null && r.AgenticSnapshot == "final");
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

        var verified = store.Records.Single(r => r.VerifiedRepairLadder is not null && r.AgenticSnapshot == "final");
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

        var verified = store.Records.Single(r => r.VerifiedRepairLadder is not null && r.AgenticSnapshot == "final");
        Assert.Equal(ErrorStatus.Unknown, verified.ErrorStatus);
        Assert.False(verified.AgenticBudgetExhausted);
    }

    [Fact]
    public async Task FirstBuildSnapshot_IsScoredIndependentlyOfFinal()
    {
        // §4.4.1 2×2 single-pass cell: the first-build state is re-scored separately from the final state,
        // and the two can disagree (iteration is two-directional). Here the agent's first build is still
        // smelly but builds; a second edit resolves it. The first_build row must be unresolved, final resolved.
        var (sln, instanceFile, known) = MakeCorpus("Demo.Thing", 1);

        const string firstEditStillSmelly =
            """{"action":"edit_and_build","edited_file":"// STILL_SMELLY edit","findings":[{"anti_pattern":"GodClass","location":{"symbol":"Demo.Thing","line":1},"explanation":"e","quality_impact":"","remediation":"r"}]}""";
        const string secondEditClean =
            """{"action":"edit_and_build","edited_file":"// resolved now","findings":[{"anti_pattern":"GodClass","location":{"symbol":"Demo.Thing","line":1},"explanation":"e","quality_impact":"","remediation":"r"}]}""";

        var store  = new CollectingRunStore();
        var runner = new AgenticRunner(
            new ScriptedAdapter(firstEditStillSmelly, secondEditClean, CompleteWithGodClass("Demo.Thing", 1)),
            "gpt-5.4",
            new ContentSensitiveMeasurer(triggerMarker: "STILL_SMELLY"),   // re-measures the actual file content
            sln, iterationBudget: 6, buildTimeoutSeconds: 30,
            build: (_, _, _) => Task.FromResult((true, "ok")));

        await runner.RunAsync(known, runs: 1, store, 120_000, TrajDir(), TextWriter.Null, CancellationToken.None,
            sweepFiles: [instanceFile]);

        var final = store.Records.Single(r => r.AgenticSnapshot == "final");
        var first = store.Records.Single(r => r.AgenticSnapshot == "first_build");

        Assert.Equal(VerifiedRepairOutcome.Resolved,         final.VerifiedRepairLadder);   // second edit cleaned it
        Assert.Equal(VerifiedRepairOutcome.BuildsUnresolved, first.VerifiedRepairLadder);   // first build still smelly
        Assert.Equal(2, final.AgenticIterations);
        Assert.Equal(2, first.AgenticIterations);
        Assert.Equal("agentic", first.Architecture);
    }

    [Fact]
    public async Task GroundedIterative_SeedsFindingBlock_AndWritesNoDetectionRows()
    {
        // The grounded-iterative arm (§4.4.1, §5.1.5): the opening prompt carries the analyser's finding
        // block, it is relieved of detection (no finding rows), and it still emits both verified snapshots.
        var (sln, instanceFile, known) = MakeCorpus("Demo.Thing", 1);

        var grounding = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            [Path.GetFullPath(instanceFile)] = "## Finding\nAnti-pattern : GodClass\nSymbol : Demo.Thing\n\n## Metrics\n  WMC: 60"
        };

        var store  = new CollectingRunStore();
        var runner = new AgenticRunner(
            new ScriptedAdapter(CompleteWithGodClass("Demo.Thing", 1)),
            "gpt-5.4",
            new FakeMeasurer(stillTriggers: false),
            sln, iterationBudget: 6, buildTimeoutSeconds: 30,
            build: (_, _, _) => Task.FromResult((true, "ok")),
            architecture: "grounded_iterative");

        await runner.RunAsync(known, runs: 1, store, 120_000, TrajDir(), TextWriter.Null, CancellationToken.None,
            sweepFiles: [instanceFile], groundingByFile: grounding);

        // Relieved of detection: every row is a verified-repair row; none is a detection finding row.
        Assert.NotEmpty(store.Records);
        Assert.All(store.Records, r => Assert.NotNull(r.VerifiedRepairLadder));
        Assert.All(store.Records, r => Assert.Equal("grounded_iterative", r.Architecture));
        Assert.All(store.Records, r => Assert.True(r.AgenticRecovered));            // recovered by construction

        // Both snapshots emitted, and the opening prompt carried the Structural finding block.
        Assert.Contains(store.Records, r => r.AgenticSnapshot == "final");
        Assert.Contains(store.Records, r => r.AgenticSnapshot == "first_build");
        var any = store.Records.First();
        Assert.Contains("Static-analysis findings", any.RawUserPrompt);
        Assert.Contains("WMC: 60", any.RawUserPrompt);
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

    /// <summary>
    /// Re-measures the ACTUAL file content at the path it is given, reporting "still triggers" iff the
    /// content contains <paramref name="triggerMarker"/>. Lets a test distinguish the first-build snapshot
    /// from the final one, since each is written to the working file before its re-measure.
    /// </summary>
    private sealed class ContentSensitiveMeasurer(string triggerMarker) : IRepairMeasurer
    {
        public Task<RemeasureResult> RemeasureAsync(
            AntiPatternType type, string workingFilePath, string instanceSymbol, CancellationToken cancellationToken = default)
        {
            var content = File.Exists(workingFilePath) ? File.ReadAllText(workingFilePath) : string.Empty;
            var stillTriggers = content.Contains(triggerMarker, StringComparison.Ordinal);
            return Task.FromResult(new RemeasureResult(stillTriggers,
                stillTriggers ? new Dictionary<string, double> { ["WMC"] = 60 } : null));
        }
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
