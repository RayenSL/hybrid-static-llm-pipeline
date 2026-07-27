using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;
using HybridLens.Pipeline;

namespace HybridLens.Tests.GeneratedTests;

public sealed class FactorialSingleShotRunnerTests : IDisposable
{
    private readonly List<string> _temp = [];

    [Fact]
    public async Task GroundedTestEnabled_MakesExactlyOneCall_ThenBuildsTestsAndScores()
    {
        var (solution, file, project, instance, artifactDir) = MakeCorpus();
        var adapter = new CountingAdapter(
            """{"edited_file":"namespace Demo; public class Thing { public int Value() => 7; }","findings":[{"anti_pattern":"GodClass","symbol":"Demo.Thing","line":1,"remediation":"split responsibilities"}]}""");
        var visible = LoadedTest(file, project, artifactDir);
        var buildFinished = false;
        var runner = new FactorialSingleShotRunner(
            adapter,
            "gpt-5.4",
            new FakeMeasurer(false),
            solution,
            30,
            build: (_, _, _) =>
            {
                buildFinished = true;
                return Task.FromResult((true, "ok"));
            },
            executeVisibleTest: (test, proj, timeout, ct) =>
            {
                Assert.True(buildFinished);
                return Task.FromResult(new GeneratedTestExecutionResult(true, true, 12, "PASS"));
            });

        var record = await runner.RunAttemptAsync(
            instance, 1, grounded: true, groundingBlock: "## Finding\nSymbol: Demo.Thing",
            visibleTestsEnabled: true, visible, artifactDir, CancellationToken.None);

        Assert.Equal(1, adapter.Calls);
        Assert.Contains("Neutral target declaration", adapter.Requests.Single().UserPrompt);
        Assert.Contains("Demo.Thing", adapter.Requests.Single().UserPrompt);
        Assert.Contains("Static-analysis finding", adapter.Requests.Single().UserPrompt);
        Assert.Equal("single_shot", record.ControlStructure);
        Assert.True(record.GroundingEnabled);
        Assert.True(record.VisibleTestsEnabled);
        Assert.True(record.VisibleTestAvailable);
        Assert.True(record.VisibleTestPassed);
        Assert.Equal(1, record.BuildAttemptCount);
        Assert.Equal(1, record.TestAttemptCount);
        Assert.True(record.VerifiedRepairSuccess);
        Assert.NotNull(record.MaterializedSourceRef);
        Assert.True(File.Exists(record.MaterializedSourceRef));
    }

    [Fact]
    public async Task UngroundedNoTest_RemainsOneCall_AndRecordsNoVisibleExecution()
    {
        var (solution, _, _, instance, artifactDir) = MakeCorpus();
        var adapter = new CountingAdapter(
            """{"edited_file":"namespace Demo; public class Thing { }","findings":[]}""");
        var runner = new FactorialSingleShotRunner(
            adapter, "gpt-5.4", new FakeMeasurer(true), solution, 30,
            build: (_, _, _) => Task.FromResult((true, "ok")));

        var record = await runner.RunAttemptAsync(
            instance, 1, grounded: false, groundingBlock: null,
            visibleTestsEnabled: false, visibleTest: null, artifactDir, CancellationToken.None);

        Assert.Equal(1, adapter.Calls);
        Assert.Contains("Neutral target declaration", adapter.Requests.Single().UserPrompt);
        Assert.Contains("Demo.Thing", adapter.Requests.Single().UserPrompt);
        Assert.DoesNotContain("Static-analysis finding", adapter.Requests.Single().UserPrompt);
        Assert.False(record.GroundingEnabled);
        Assert.False(record.VisibleTestsEnabled);
        Assert.False(record.VisibleTestAvailable);
        Assert.Null(record.VisibleTestPassed);
        Assert.Equal(0, record.TestAttemptCount);
        Assert.False(record.AgenticRecovered);
        Assert.False(record.VerifiedRepairSuccess);
    }

    [Fact]
    public async Task StaleVisibleTest_IsRejectedBeforeSingleShotModelCall()
    {
        var (solution, file, project, instance, artifactDir) = MakeCorpus();
        var adapter = new CountingAdapter(
            """{"edited_file":"namespace Demo; public class Thing { }","findings":[]}""");
        var valid = LoadedTest(file, project, artifactDir);
        var stale = valid with { Artifact = valid.Artifact with { SourceSha256 = "stale" } };
        var runner = new FactorialSingleShotRunner(
            adapter, "gpt-5.4", new FakeMeasurer(true), solution, 30,
            build: (_, _, _) => Task.FromResult((true, "ok")));

        var error = await Assert.ThrowsAsync<InvalidDataException>(() => runner.RunAttemptAsync(
            instance, 1, grounded: false, groundingBlock: null,
            visibleTestsEnabled: true, stale, artifactDir, CancellationToken.None));

        Assert.Contains("different pristine source revision", error.Message);
        Assert.Equal(0, adapter.Calls);
    }

    [Fact]
    public async Task VisibleTestForDifferentTarget_IsRejectedBeforeSingleShotModelCall()
    {
        var (solution, file, project, instance, artifactDir) = MakeCorpus();
        var adapter = new CountingAdapter(
            """{"edited_file":"namespace Demo; public class Thing { }","findings":[]}""");
        var valid = LoadedTest(file, project, artifactDir);
        var wrongTarget = valid with
        {
            Artifact = valid.Artifact with { TargetSymbolName = "Demo.Other" }
        };
        var runner = new FactorialSingleShotRunner(
            adapter, "gpt-5.4", new FakeMeasurer(true), solution, 30,
            build: (_, _, _) => Task.FromResult((true, "ok")));

        var error = await Assert.ThrowsAsync<InvalidDataException>(() => runner.RunAttemptAsync(
            instance, 1, grounded: false, groundingBlock: null,
            visibleTestsEnabled: true, wrongTarget, artifactDir, CancellationToken.None));

        Assert.Contains("different target declaration", error.Message);
        Assert.Equal(0, adapter.Calls);
    }

    private (string Solution, string File, string Project, KnownInstance Instance, string Artifacts) MakeCorpus()
    {
        var root = Path.Combine(Path.GetTempPath(), $"hl-single-shot-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);
        _temp.Add(root);
        var solution = Path.Combine(root, "Corpus.sln");
        File.WriteAllText(solution, "Microsoft Visual Studio Solution File");
        var projectDir = Path.Combine(root, "Demo");
        Directory.CreateDirectory(projectDir);
        var project = Path.Combine(projectDir, "Demo.csproj");
        File.WriteAllText(project, "<Project Sdk=\"Microsoft.NET.Sdk\"><PropertyGroup><TargetFramework>net10.0</TargetFramework></PropertyGroup></Project>");
        var file = Path.Combine(projectDir, "Thing.cs");
        File.WriteAllText(file, "namespace Demo; public class Thing { public int Value() => 7; }");
        var instance = KnownInstance.Create(AntiPatternType.GodClass, file, "Demo.Thing", 1, Severity.Critical, "public class Thing");
        return (solution, file, project, instance, Path.Combine(root, "artifacts"));
    }

    private static LoadedGeneratedTest LoadedTest(string file, string project, string artifactDir)
    {
        var source = new GeneratedTestSource("existing value", ["using Demo;"],
            "var actual = new Thing().Value(); Check.Equal(7, actual);");
        var hash = Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(
            System.Text.Encoding.UTF8.GetBytes("using Demo;\n" + source.TestBody)));
        var artifact = new GeneratedTestArtifact
        {
            ArtifactId = "test",
            ArtifactRef = Path.Combine(artifactDir, "test.json"),
            Timestamp = DateTimeOffset.UtcNow,
            SourceFile = file,
            SourceSha256 = MaterializedSourceArtifactWriter.Sha256(File.ReadAllText(file)),
            TargetSymbolName = "Demo.Thing",
            TargetStartLine = 1,
            TargetEndLine = 1,
            ProjectFile = project,
            ModelName = "gpt-5.4",
            PromptVersion = "v1.1.0",
            RawSystemPrompt = "system",
            RawUserPrompt = "user",
            TestName = source.TestName,
            UsingDirectives = source.UsingDirectives,
            TestBody = source.TestBody,
            TestSha256 = hash,
            AdmissionStatus = GeneratedTestAdmissionStatus.Admitted,
            ParsePassed = true,
            AssertionGatePassed = true,
            BuildPassed = true,
            BaselineRunsPassed = [true, true]
        };
        return new LoadedGeneratedTest(artifact, source);
    }

    public void Dispose()
    {
        foreach (var path in _temp)
            try { if (Directory.Exists(path)) Directory.Delete(path, true); } catch { }
    }

    private sealed class CountingAdapter(string output) : ILlmAdapter
    {
        public int Calls { get; private set; }
        public List<LlmRequest> Requests { get; } = [];
        public Task<LlmResponse> CompleteAsync(LlmRequest request, CancellationToken cancellationToken = default)
        {
            Calls++;
            Requests.Add(request);
            return Task.FromResult(new LlmResponse { Content = output, InputTokens = 10, OutputTokens = 20 });
        }
        public Task<LlmResponse> CompleteAsync(LlmConversation conversation, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();
    }

    private sealed class FakeMeasurer(bool stillTriggers) : IRepairMeasurer
    {
        public Task<RemeasureResult> RemeasureAsync(
            AntiPatternType type, string workingFilePath, string instanceSymbol, CancellationToken cancellationToken = default)
            => Task.FromResult(new RemeasureResult(stillTriggers,
                stillTriggers ? new Dictionary<string, double> { ["WMC"] = 60 } : null));
    }
}
