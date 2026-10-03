using HybridLens.ContextBuilder;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;
using HybridLens.Pipeline;

namespace HybridLens.Tests.Campaigns;

public sealed class CampaignRunnerTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), $"campaign-runner-{Guid.NewGuid():N}");
    private readonly CountingAdapter _adapter = new();
    private readonly IContextBuilder _context = new HybridLens.ContextBuilder.ContextBuilder();
    private readonly IRepairMeasurer _measurer = new UnexpectedMeasurer();

    public CampaignRunnerTests() => Directory.CreateDirectory(_root);

    [Fact]
    public async Task Factorial_SealsProviderFailureAndDoesNotRepeatCommittedCalls()
    {
        var manifest = FactorialManifest();
        var runner = new FactorialCampaignRunner(_adapter, _context, _measurer);
        var output = Path.Combine(_root, "campaign");
        Assert.Equal(CampaignRunOutcome.Completed, await runner.RunAsync(manifest, output,
            new Dictionary<string, LoadedGeneratedTest>(), TextWriter.Null));
        Assert.Equal(1, _adapter.Calls);
        Assert.Equal(CampaignRunOutcome.Completed, await runner.RunAsync(manifest, output,
            new Dictionary<string, LoadedGeneratedTest>(), TextWriter.Null));
        Assert.Equal(1, _adapter.Calls);
        var ledger = new CampaignLedger<FactorialCampaignExecutionRecord>(
            Path.Combine(output, "execution-ledger.jsonl"), manifest.CampaignId);
        Assert.Single(ledger.LoadCompleted());
    }

    [Fact]
    public async Task Factorial_RefusesOrphanTraceBeforeAnyModelCall()
    {
        var manifest = FactorialManifest();
        var output = Path.Combine(_root, "campaign");
        Directory.CreateDirectory(Path.Combine(output, "traces"));
        var assignment = manifest.Assignments[0];
        File.WriteAllText(Path.Combine(output, "traces", $"{assignment.Order:D4}-{assignment.AssignmentId}.jsonl"), "partial");
        var result = await new FactorialCampaignRunner(_adapter, _context, _measurer).RunAsync(
            manifest, output, new Dictionary<string, LoadedGeneratedTest>(), TextWriter.Null);
        Assert.Equal(CampaignRunOutcome.InvalidResumeState, result);
        Assert.Equal(0, _adapter.Calls);
    }

    [Fact]
    public async Task Factorial_InvalidLedgerReturnsResumeFailureBeforeAnyModelCall()
    {
        var manifest = FactorialManifest();
        var output = Path.Combine(_root, "campaign");
        Directory.CreateDirectory(output);
        File.WriteAllText(Path.Combine(output, "execution-ledger.jsonl"), "partial");
        var result = await new FactorialCampaignRunner(_adapter, _context, _measurer).RunAsync(
            manifest, output, new Dictionary<string, LoadedGeneratedTest>(), TextWriter.Null);
        Assert.Equal(CampaignRunOutcome.InvalidResumeState, result);
        Assert.Equal(0, _adapter.Calls);
    }

    [Fact]
    public async Task Factorial_CancellationDoesNotBecomeACommittedFailure()
    {
        var manifest = FactorialManifest();
        var output = Path.Combine(_root, "campaign");
        using var cancelled = new CancellationTokenSource();
        cancelled.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
            new FactorialCampaignRunner(_adapter, _context, _measurer).RunAsync(manifest, output,
                new Dictionary<string, LoadedGeneratedTest>(), TextWriter.Null, cancelled.Token));
        Assert.Equal(0, _adapter.Calls);
        Assert.False(File.Exists(Path.Combine(output, "execution-ledger.jsonl")));
    }

    [Fact]
    public async Task ContextLadder_StopsAndResumesWithoutPoolingLevelsOrEnablingTests()
    {
        var manifest = LadderManifest();
        var output = Path.Combine(_root, "ladder");
        var runner = new ContextLadderCampaignRunner(_adapter, _context, _measurer);
        Assert.Equal(CampaignRunOutcome.Completed,
            await runner.RunAsync(manifest, output, 1, TextWriter.Null));
        Assert.Equal(1, _adapter.Calls);
        Assert.Equal(CampaignRunOutcome.Completed,
            await runner.RunAsync(manifest, output, 0, TextWriter.Null));
        Assert.Equal(4, _adapter.Calls);
        var completed = new CampaignLedger<LadderExecutionRecord>(
            Path.Combine(output, "execution-ledger.jsonl"), manifest.CampaignId)
            .LoadCompleted(row => row.TraceSha256);
        Assert.Equal(4, completed.Count);
        Assert.Equal(4, completed.Values.Select(row => row.ContextLevel).Distinct().Count());
        foreach (var row in completed.Values)
        {
            using var trace = System.Text.Json.JsonDocument.Parse(File.ReadAllText(row.TraceFile));
            Assert.False(trace.RootElement.GetProperty("visible_tests_enabled").GetBoolean());
            Assert.Equal(1, row.EvaluatedModelCalls);
        }
        Assert.Equal(CampaignRunOutcome.Completed,
            await runner.RunAsync(manifest, output, 0, TextWriter.Null));
        Assert.Equal(4, _adapter.Calls);
    }

    [Fact]
    public async Task ContextLadder_RejectsChangedCompletedTraceBeforeNewModelCalls()
    {
        var manifest = LadderManifest();
        var output = Path.Combine(_root, "ladder");
        var runner = new ContextLadderCampaignRunner(_adapter, _context, _measurer);
        await runner.RunAsync(manifest, output, 1, TextWriter.Null);
        var trace = Directory.GetFiles(Path.Combine(output, "traces")).Single();
        File.AppendAllText(trace, "tampered");
        Assert.Equal(CampaignRunOutcome.InvalidResumeState,
            await runner.RunAsync(manifest, output, 0, TextWriter.Null));
        Assert.Equal(1, _adapter.Calls);
    }

    [Fact]
    public void ContextManifest_RejectsLadderAndSourceDrift()
    {
        var manifest = LadderManifest();
        var path = Path.Combine(_root, "manifest.json");
        var json = new System.Text.Json.JsonSerializerOptions
        {
            PropertyNamingPolicy = System.Text.Json.JsonNamingPolicy.SnakeCaseLower,
            Converters = { new System.Text.Json.Serialization.JsonStringEnumConverter(System.Text.Json.JsonNamingPolicy.SnakeCaseLower) }
        };
        File.WriteAllText(path, System.Text.Json.JsonSerializer.Serialize(manifest, json));
        Assert.Equal(4, ContextLadderManifestStore.LoadAndValidate(path).Assignments.Count);
        File.WriteAllText(path, System.Text.Json.JsonSerializer.Serialize(manifest with { LadderSha256 = "changed" }, json));
        Assert.Contains("definition drift", Assert.Throws<InvalidDataException>(() =>
            ContextLadderManifestStore.LoadAndValidate(path)).Message);
        File.WriteAllText(path, System.Text.Json.JsonSerializer.Serialize(manifest, json));
        File.AppendAllText(manifest.Assignments[0].FilePath, "changed");
        Assert.Contains("pristine source", Assert.Throws<InvalidDataException>(() =>
            ContextLadderManifestStore.LoadAndValidate(path)).Message);
    }

    private FactorialCampaignManifest FactorialManifest()
    {
        var input = Path.Combine(_root, "input");
        Directory.CreateDirectory(input);
        var solution = Path.Combine(input, "Corpus.sln");
        var source = Path.Combine(input, "Thing.cs");
        var baseline = Path.Combine(input, "baseline.jsonl");
        File.WriteAllText(solution, "Microsoft Visual Studio Solution File");
        File.WriteAllText(source, "namespace Demo; public class Thing { }");
        File.WriteAllText(baseline, "{}");
        var known = KnownInstance.Create(AntiPatternType.GodClass, source, "Demo.Thing", 1, Severity.Warning, "class Thing") with { EndLine = 1 };
        var finding = new Finding
        {
            Type = known.Type, Severity = known.Severity, FilePath = source,
            SymbolName = known.SymbolName, Line = 1, Metrics = new Dictionary<string, double>()
        };
        var manifest = FactorialCampaignPlanner.Create([new FactorialCampaignSeed(known, finding)],
            new Dictionary<string, LoadedGeneratedTest>(), solution, baseline, "fake", "revision", 1, 6, 30, 120000, 7);
        var assignment = manifest.Assignments.First(a => !a.GroundingEnabled && !a.VisibleTestsEnabled && a.ControlStructure == "single_shot");
        return manifest with { Assignments = [assignment with { Order = 1 }] };
    }

    private ContextLadderManifest LadderManifest()
    {
        var factorial = FactorialManifest();
        var target = factorial.Assignments[0];
        return new ContextLadderManifest
        {
            SchemaVersion = "2.0.0", CampaignId = "ladder", ModelName = "fake",
            TargetSolution = factorial.TargetSolution, BaselineSource = factorial.BaselineSource,
            BaselineSha256 = factorial.BaselineSha256, CodeRevision = "revision",
            PromptVersion = ContextLadderPrompt.Version, LadderVersion = ContextLadder.V2Version,
            LadderSha256 = ContextLadder.Sha256(ContextLadder.ForVersion(ContextLadder.V2Version)),
            Repetitions = 1, RandomizationSeed = 7, BuildTimeoutSeconds = 30,
            Assignments = new[] { ContextLevel.Minimal, ContextLevel.Structural, ContextLevel.Relational, ContextLevel.Full }
                .Select((level, index) => new LadderAssignment
                {
                    Order = index + 1, AssignmentId = $"level-{index}", BlockId = "target-1", RunNumber = 1,
                    ContextLevel = level, AntiPatternType = target.AntiPatternType, Severity = target.Severity,
                    FilePath = target.FilePath, SymbolName = target.SymbolName, Line = target.Line,
                    TargetEndLine = target.TargetEndLine, Metrics = new Dictionary<string, double>(),
                    ExpectedQualityAttributes = [], PristineSourceSha256 = target.PristineSourceSha256,
                    ProjectMetadata = new Dictionary<string, string>()
                }).ToList()
        };
    }

    private sealed class CountingAdapter : ILlmAdapter
    {
        public int Calls { get; private set; }
        public Task<LlmResponse> CompleteAsync(LlmRequest request, CancellationToken cancellationToken = default)
        {
            Calls++;
            throw new InvalidOperationException("simulated provider failure");
        }
        public Task<LlmResponse> CompleteAsync(LlmConversation conversation, CancellationToken cancellationToken = default)
            => throw new InvalidOperationException("these assignments must be single-shot");
    }

    private sealed class UnexpectedMeasurer : IRepairMeasurer
    {
        public Task<RemeasureResult> RemeasureAsync(AntiPatternType type, string workingFilePath,
            string instanceSymbol, CancellationToken cancellationToken = default)
            => throw new InvalidOperationException("provider failure must not trigger remeasurement");
    }

    public void Dispose() => WorkingCopy.TryDelete(_root);
}
