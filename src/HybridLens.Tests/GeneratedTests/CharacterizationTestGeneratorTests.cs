using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;
using HybridLens.Pipeline;

namespace HybridLens.Tests.GeneratedTests;

public sealed class CharacterizationTestGeneratorTests : IDisposable
{
    private readonly List<string> _tempDirs = [];

    [Fact]
    public async Task GenerateAsync_FreezesAdmittedArtifact_WithoutDetectorGrounding()
    {
        var (solution, source, output) = MakeCorpus();
        var adapter = new SingleShotAdapter(
            """{"test_name":"existing result","using_directives":["using Demo;"],"test_body":"var actual = new Calculator().Add(2, 3); Check.Equal(5, actual);"}""");
        var generator = new CharacterizationTestGenerator(
            adapter,
            "gpt-5.4",
            (test, project, runs, timeout, ct) => Task.FromResult(new GeneratedTestAdmissionResult(
                GeneratedTestAdmissionStatus.Admitted, null, true, true, [true, true], "PASS")));

        var result = await generator.GenerateAsync(
            source, solution, output,
            BlindedTargetDescriptor.Create("Demo.Calculator.Add", 1, 1),
            2, 30, CancellationToken.None);

        Assert.True(result.Artifact.Admitted);
        Assert.True(result.Artifact.ParsePassed);
        Assert.Equal("v1.1.0", result.Artifact.PromptVersion);
        Assert.Equal("Demo.Calculator.Add", result.Artifact.TargetSymbolName);
        Assert.Equal(1, result.Artifact.TargetStartLine);
        Assert.Equal(1, result.Artifact.TargetEndLine);
        Assert.Equal([true, true], result.Artifact.BaselineRunsPassed);
        Assert.NotNull(result.Artifact.TestSha256);
        Assert.True(File.Exists(result.ArtifactPath));
        Assert.DoesNotContain("anti-pattern", result.Artifact.RawUserPrompt, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("detector", result.Artifact.RawUserPrompt, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Demo.Calculator.Add", result.Artifact.RawUserPrompt);
        Assert.Contains("Source lines: 1-1", result.Artifact.RawUserPrompt);
        Assert.DoesNotContain("Long Method", result.Artifact.RawUserPrompt, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("WMC", result.Artifact.RawUserPrompt, StringComparison.OrdinalIgnoreCase);
        Assert.Single(adapter.Requests);

        var loaded = await GeneratedTestArtifactLoader.LoadAdmittedAsync(result.ArtifactPath);
        Assert.Equal(result.Artifact.TestSha256, loaded.Artifact.TestSha256);
        GeneratedTestArtifactLoader.VerifyUnchanged(loaded);
    }

    [Fact]
    public async Task GenerateAsync_PersistsParseFailure_WithoutCallingAdmission()
    {
        var (solution, source, output) = MakeCorpus();
        var called = false;
        var generator = new CharacterizationTestGenerator(
            new SingleShotAdapter("not-json"),
            "gpt-5.4",
            (test, project, runs, timeout, ct) =>
            {
                called = true;
                throw new InvalidOperationException();
            });

        var result = await generator.GenerateAsync(
            source, solution, output,
            BlindedTargetDescriptor.Create("Demo.Calculator.Add", 1, 1),
            2, 30, CancellationToken.None);

        Assert.False(called);
        Assert.False(result.Artifact.Admitted);
        Assert.False(result.Artifact.ParsePassed);
        Assert.Equal(GeneratedTestAdmissionStatus.ParseFailed, result.Artifact.AdmissionStatus);
        Assert.True(File.Exists(result.ArtifactPath));
    }

    [Theory]
    [InlineData("Check.True(true);")]
    [InlineData("var x = File.ReadAllText(\"secret\"); Check.NotNull(x);")]
    public void AssertionGate_RejectsVacuousOrExternalStateTests(string body)
    {
        Assert.False(GeneratedTestAdmissionRunner.HasNonVacuousAssertion(body, out var reason));
        Assert.False(string.IsNullOrWhiteSpace(reason));
    }

    [Fact]
    public void Parse_RejectsInvalidUsingDirective()
    {
        var parsed = CharacterizationTestGenerator.Parse(
            """{"test_name":"x","using_directives":["namespace Demo"],"test_body":"Check.True(GetValue());"}""",
            out var reason);

        Assert.Null(parsed);
        Assert.Contains("using_directives", reason);
    }

    [Fact]
    public async Task AdmissionRunner_CompilesAndRunsAgainstPristineProjectTwice()
    {
        var (_, source, _) = MakeCorpus();
        var project = Path.Combine(Path.GetDirectoryName(source)!, "Demo.csproj");
        var generated = new GeneratedTestSource(
            "existing addition result",
            ["using Demo;"],
            "var actual = new Calculator().Add(2, 3); Check.Equal(5, actual);");

        var result = await GeneratedTestAdmissionRunner.RunAsync(
            generated, project, baselineRuns: 2, timeoutSeconds: 60, CancellationToken.None);

        Assert.True(result.Admitted, result.OutputTail);
        Assert.True(result.BuildPassed);
        Assert.Equal([true, true], result.BaselineRunsPassed);
    }

    private (string Solution, string Source, string Output) MakeCorpus()
    {
        var root = Path.Combine(Path.GetTempPath(), $"hl-generated-test-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);
        _tempDirs.Add(root);
        var solution = Path.Combine(root, "Corpus.sln");
        File.WriteAllText(solution, "Microsoft Visual Studio Solution File");
        var projectDir = Path.Combine(root, "Demo");
        Directory.CreateDirectory(projectDir);
        File.WriteAllText(Path.Combine(projectDir, "Demo.csproj"),
            "<Project Sdk=\"Microsoft.NET.Sdk\"><PropertyGroup><TargetFramework>net10.0</TargetFramework></PropertyGroup></Project>");
        var source = Path.Combine(projectDir, "Calculator.cs");
        File.WriteAllText(source,
            "namespace Demo; public sealed class Calculator { public int Add(int a, int b) => a + b; }");
        return (solution, source, Path.Combine(root, "artifacts"));
    }

    public void Dispose()
    {
        foreach (var directory in _tempDirs)
            try { if (Directory.Exists(directory)) Directory.Delete(directory, recursive: true); } catch { }
    }

    private sealed class SingleShotAdapter(string response) : ILlmAdapter
    {
        public List<LlmRequest> Requests { get; } = [];

        public Task<LlmResponse> CompleteAsync(LlmRequest request, CancellationToken cancellationToken = default)
        {
            Requests.Add(request);
            return Task.FromResult(new LlmResponse { Content = response, InputTokens = 17, OutputTokens = 23 });
        }

        public Task<LlmResponse> CompleteAsync(LlmConversation conversation, CancellationToken cancellationToken = default)
            => throw new NotSupportedException("test generation is a stateless single-shot call");
    }
}
