using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;
using HybridLens.ContextBuilder;
using HybridLens.Pipeline;

namespace HybridLens.Tests.GeneratedTests;

public sealed class CharacterizationTestGeneratorTests : IDisposable
{
    private readonly List<string> _tempDirs = [];

    [Fact]
    public void Prompt_RequiresOneHappyPathAndFourFixedEdgeCaseObligations()
    {
        Assert.Contains("exactly five", CharacterizationTestPrompt.SystemPrompt, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("H1", CharacterizationTestPrompt.SystemPrompt);
        Assert.Contains("E1", CharacterizationTestPrompt.SystemPrompt);
        Assert.Contains("B1", CharacterizationTestPrompt.SystemPrompt);
        Assert.Contains("A1", CharacterizationTestPrompt.SystemPrompt);
        Assert.Contains("D1", CharacterizationTestPrompt.SystemPrompt);
        Assert.Contains("below", CharacterizationTestPrompt.SystemPrompt, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("at", CharacterizationTestPrompt.SystemPrompt, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("above", CharacterizationTestPrompt.SystemPrompt, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Parse_AcceptsOnlyTheFixedFiveCaseSuite()
    {
        var parsed = CharacterizationTestGenerator.Parse(FiveCaseSuiteJson(), out var reason);

        Assert.NotNull(parsed);
        Assert.Null(reason);
        Assert.Contains("happy", parsed.TestBody);
        Assert.Contains("boundary", parsed.TestBody);

        var missingCase = FiveCaseSuiteJson().Replace(
            ",{\"case_id\":\"D1\",\"category\":\"dependency_or_state\",\"test_name\":\"dependency\",\"test_body\":\"var actual = new Calculator().Add(6, 1); Check.Equal(7, actual);\"}",
            string.Empty,
            StringComparison.Ordinal);
        Assert.Null(CharacterizationTestGenerator.Parse(missingCase, out var missingReason));
        Assert.Contains("exactly five", missingReason, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task GenerateAsync_UsesPlanThenImplementation_AndIncludesNeutralDependencies()
    {
        var (solution, source, output) = MakeCorpus(includeDependency: true);
        var adapter = new QueuedAdapter(ValidPlanJson(), FiveCaseSuiteJson());
        var generator = new CharacterizationTestGenerator(
            adapter,
            "gpt-5.4",
            (test, project, runs, timeout, ct) => Task.FromResult(new GeneratedTestAdmissionResult(
                GeneratedTestAdmissionStatus.Admitted, null, true, true, [true, true, true], "PASS")));

        var result = await generator.GenerateAsync(
            source, solution, output,
            BlindedTargetDescriptor.Create("Demo.Calculator.Add", 1, 1),
            3, 30, CancellationToken.None);

        Assert.True(result.Artifact.Admitted, result.Artifact.AdmissionReason);
        Assert.Equal(2, adapter.Requests.Count);
        Assert.Contains("plan", adapter.Requests[0].PromptVersion, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("implementation", adapter.Requests[1].PromptVersion, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("IMathPolicy", adapter.Requests[0].UserPrompt);
        Assert.DoesNotContain("UnrelatedService", adapter.Requests[0].UserPrompt);
        Assert.Contains("H1", adapter.Requests[1].UserPrompt);
        Assert.Contains("B1", adapter.Requests[1].UserPrompt);
    }

    [Fact]
    public async Task GenerateAsync_AllowsOneCompileOnlyCorrection_WithoutRuntimeFeedback()
    {
        var (solution, source, output) = MakeCorpus();
        var adapter = new QueuedAdapter(ValidPlanJson(), FiveCaseSuiteJson(), FiveCaseSuiteJson());
        var admissions = 0;
        var generator = new CharacterizationTestGenerator(
            adapter,
            "gpt-5.4",
            (test, project, runs, timeout, ct) => Task.FromResult(++admissions == 1
                ? new GeneratedTestAdmissionResult(
                    GeneratedTestAdmissionStatus.BuildFailed, "does not compile", true, false, [], "CS0246: Missing type")
                : new GeneratedTestAdmissionResult(
                    GeneratedTestAdmissionStatus.Admitted, null, true, true, [true, true, true], "PASS")));

        var result = await generator.GenerateAsync(
            source, solution, output,
            BlindedTargetDescriptor.Create("Demo.Calculator.Add", 1, 1),
            3, 30, CancellationToken.None);

        Assert.True(result.Artifact.Admitted, result.Artifact.AdmissionReason);
        Assert.Equal(3, adapter.Requests.Count);
        Assert.Equal(2, admissions);
        Assert.Equal(3, result.Artifact.GenerationCallCount);
        Assert.Equal(17, result.Artifact.CorrectionInputTokens);
        Assert.Equal(23, result.Artifact.CorrectionOutputTokens);
        Assert.Contains("CS0246", adapter.Requests[2].UserPrompt);
        Assert.DoesNotContain("PASS", adapter.Requests[2].UserPrompt);
        Assert.Contains("compile", adapter.Requests[2].PromptVersion, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task GenerateAsync_RejectsACompileCorrectionThatChangesACaseBody()
    {
        var (solution, source, output) = MakeCorpus();
        var changed = FiveCaseSuiteJson().Replace("Check.Equal(7, actual);", "Check.Equal(8, actual);", StringComparison.Ordinal);
        var adapter = new QueuedAdapter(ValidPlanJson(), FiveCaseSuiteJson(), changed);
        var admissions = 0;
        var generator = new CharacterizationTestGenerator(
            adapter,
            "gpt-5.4",
            (test, project, runs, timeout, ct) =>
            {
                admissions++;
                return Task.FromResult(new GeneratedTestAdmissionResult(
                    GeneratedTestAdmissionStatus.BuildFailed, "does not compile", true, false, [], "CS0246"));
            });

        var result = await generator.GenerateAsync(
            source, solution, output,
            BlindedTargetDescriptor.Create("Demo.Calculator.Add", 1, 1),
            3, 30, CancellationToken.None);

        Assert.False(result.Artifact.Admitted);
        Assert.Equal(GeneratedTestAdmissionStatus.ParseFailed, result.Artifact.AdmissionStatus);
        Assert.Contains("changed a frozen test case", result.Artifact.AdmissionReason);
        Assert.Equal(3, adapter.Requests.Count);
        Assert.Equal(1, admissions);
    }

    [Fact]
    public async Task GenerateAsync_DoesNotCorrectARuntimeFailure()
    {
        var (solution, source, output) = MakeCorpus();
        var adapter = new QueuedAdapter(ValidPlanJson(), FiveCaseSuiteJson());
        var generator = new CharacterizationTestGenerator(
            adapter,
            "gpt-5.4",
            (test, project, runs, timeout, ct) => Task.FromResult(new GeneratedTestAdmissionResult(
                GeneratedTestAdmissionStatus.BaselineFailed, "assertion failed", true, true, [false, false, false], "FAIL")));

        var result = await generator.GenerateAsync(
            source, solution, output,
            BlindedTargetDescriptor.Create("Demo.Calculator.Add", 1, 1),
            3, 30, CancellationToken.None);

        Assert.Equal(GeneratedTestAdmissionStatus.BaselineFailed, result.Artifact.AdmissionStatus);
        Assert.Equal(2, adapter.Requests.Count);
    }

    [Fact]
    public async Task GenerateAsync_FreezesAdmittedArtifact_WithoutDetectorGrounding()
    {
        var (solution, source, output) = MakeCorpus();
        var adapter = new QueuedAdapter(ValidPlanJson(), FiveCaseSuiteJson());
        var generator = new CharacterizationTestGenerator(
            adapter,
            "gpt-5.4",
            (test, project, runs, timeout, ct) => Task.FromResult(new GeneratedTestAdmissionResult(
                GeneratedTestAdmissionStatus.Admitted, null, true, true, [true, true, true], "PASS")));

        var result = await generator.GenerateAsync(
            source, solution, output,
            BlindedTargetDescriptor.Create("Demo.Calculator.Add", 1, 1),
            3, 30, CancellationToken.None);

        Assert.True(result.Artifact.Admitted);
        Assert.True(result.Artifact.ParsePassed);
        Assert.Equal("v2.0.0", result.Artifact.PromptVersion);
        Assert.Equal("Demo.Calculator.Add", result.Artifact.TargetSymbolName);
        Assert.Equal(1, result.Artifact.TargetStartLine);
        Assert.Equal(1, result.Artifact.TargetEndLine);
        Assert.Equal([true, true, true], result.Artifact.BaselineRunsPassed);
        Assert.Equal(2, result.Artifact.GenerationCallCount);
        Assert.Equal(17, result.Artifact.PlanInputTokens);
        Assert.Equal(23, result.Artifact.PlanOutputTokens);
        Assert.Equal(17, result.Artifact.ImplementationInputTokens);
        Assert.Equal(23, result.Artifact.ImplementationOutputTokens);
        Assert.False(string.IsNullOrWhiteSpace(result.Artifact.DependencyContextSha256));
        Assert.NotNull(result.Artifact.TestSha256);
        Assert.True(File.Exists(result.ArtifactPath));
        Assert.DoesNotContain("anti-pattern", result.Artifact.RawUserPrompt, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("detector", result.Artifact.RawUserPrompt, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Demo.Calculator.Add", result.Artifact.RawUserPrompt);
        Assert.Contains("Source lines: 1-1", result.Artifact.RawUserPrompt);
        Assert.DoesNotContain("Long Method", result.Artifact.RawUserPrompt, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("WMC", result.Artifact.RawUserPrompt, StringComparison.OrdinalIgnoreCase);
        Assert.Equal(2, adapter.Requests.Count);

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
    public void ParsePlan_RejectsABoundaryCaseWithoutThreeStimuli()
    {
        var invalid = ValidPlanJson().Replace(
            "\"inputs\":[\"-1\",\"0\",\"1\"]",
            "\"inputs\":[\"0\"]",
            StringComparison.Ordinal);

        Assert.Null(CharacterizationTestGenerator.ParsePlan(invalid, out var reason));
        Assert.Contains("below, at and above", reason, StringComparison.OrdinalIgnoreCase);
    }

    [Theory]
    [InlineData("[]")]
    [InlineData("null")]
    [InlineData("\"text\"")]
    public void StructuredParsers_RejectNonObjectRoots(string json)
    {
        Assert.Null(CharacterizationTestGenerator.ParsePlan(json, out var planReason));
        Assert.Contains("object", planReason, StringComparison.OrdinalIgnoreCase);
        Assert.Null(CharacterizationTestGenerator.Parse(json, out var suiteReason));
        Assert.Contains("object", suiteReason, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task AdmissionRunner_RejectsTheWholeSuite_WhenOneCaseIsVacuous()
    {
        var (_, source, _) = MakeCorpus();
        var project = Path.Combine(Path.GetDirectoryName(source)!, "Demo.csproj");
        var raw = FiveCaseSuiteJson().Replace(
            "var actual = new Calculator().Add(6, 1); Check.Equal(7, actual);",
            "var actual = new Calculator().Add(6, 1); Check.True(true);",
            StringComparison.Ordinal);
        var generated = CharacterizationTestGenerator.Parse(raw, out var parseReason);

        Assert.NotNull(generated);
        Assert.Null(parseReason);
        var result = await GeneratedTestAdmissionRunner.RunAsync(
            generated, project, baselineRuns: 2, timeoutSeconds: 60, CancellationToken.None);

        Assert.Equal(GeneratedTestAdmissionStatus.AssertionGateFailed, result.Status);
        Assert.Contains("D1", result.Reason);
    }

    [Fact]
    public async Task AdmissionRunner_CompilesAndRunsStructuredSuiteThreeTimes()
    {
        var (_, source, _) = MakeCorpus();
        var project = Path.Combine(Path.GetDirectoryName(source)!, "Demo.csproj");
        var generated = CharacterizationTestGenerator.Parse(FiveCaseSuiteJson(), out var parseReason);

        Assert.NotNull(generated);
        Assert.Null(parseReason);

        var result = await GeneratedTestAdmissionRunner.RunAsync(
            generated, project, baselineRuns: 2, timeoutSeconds: 60, CancellationToken.None);

        Assert.True(result.Admitted, result.OutputTail);
        Assert.True(result.BuildPassed);
        Assert.Equal([true, true, true], result.BaselineRunsPassed);
    }

    [Fact]
    public async Task AdmissionRunner_AllowsDeterministicInMemoryFakeTypes()
    {
        var (_, source, _) = MakeCorpus(includeDependency: true);
        var project = Path.Combine(Path.GetDirectoryName(source)!, "Demo.csproj");
        var raw = FiveCaseSuiteJson()
            .Replace("\"helper_code\":\"\"",
                "\"helper_code\":\"private sealed class FixedPolicy : IMathPolicy { public int Combine(int a, int b) => 13; }\"",
                StringComparison.Ordinal)
            .Replace("var actual = new Calculator().Add(6, 1); Check.Equal(7, actual);",
                "var actual = new Calculator().Add(6, 1, new FixedPolicy()); Check.Equal(13, actual);",
                StringComparison.Ordinal);
        var generated = CharacterizationTestGenerator.Parse(raw, out var parseReason);

        Assert.NotNull(generated);
        Assert.Null(parseReason);
        var result = await GeneratedTestAdmissionRunner.RunAsync(
            generated, project, baselineRuns: 3, timeoutSeconds: 60, CancellationToken.None);

        Assert.True(result.Admitted, result.OutputTail);
    }

    private (string Solution, string Source, string Output) MakeCorpus(bool includeDependency = false)
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
        File.WriteAllText(source, includeDependency
            ? "namespace Demo; public sealed class Calculator { public int Add(int a, int b, IMathPolicy? policy = null) => policy?.Combine(a, b) ?? a + b; }"
            : "namespace Demo; public sealed class Calculator { public int Add(int a, int b) => a + b; }");
        if (includeDependency)
        {
            File.WriteAllText(Path.Combine(projectDir, "IMathPolicy.cs"),
                "namespace Demo; public interface IMathPolicy { int Combine(int a, int b); } public sealed class DefaultMathPolicy : IMathPolicy { public int Combine(int a, int b) => a + b; }");
            File.WriteAllText(Path.Combine(projectDir, "UnrelatedService.cs"),
                "namespace Demo; public sealed class UnrelatedService { public int Value() => 42; }");
        }
        return (solution, source, Path.Combine(root, "artifacts"));
    }

    private static string ValidPlanJson() =>
        """{"suite_name":"calculator behaviour","cases":[{"case_id":"H1","category":"happy_path","source_evidence":"public Add operation","input_partition":"representative valid operands","inputs":["2 and 3"],"expected_observation":"returns their sum"},{"case_id":"E1","category":"empty_or_invalid","source_evidence":"zero is accepted","input_partition":"minimal operands","inputs":["0 and 0"],"expected_observation":"returns zero"},{"case_id":"B1","category":"boundary_values","source_evidence":"integer inputs","input_partition":"adjacent values around zero","inputs":["-1","0","1"],"expected_observation":"preserves addition"},{"case_id":"A1","category":"alternative_path","source_evidence":"negative operands are accepted","input_partition":"alternative valid sign","inputs":["-2 and 3"],"expected_observation":"returns one"},{"case_id":"D1","category":"dependency_or_state","source_evidence":"optional policy collaborator","input_partition":"explicit deterministic dependency","inputs":["fake policy"],"expected_observation":"uses dependency result"}]}""";

    private static string FiveCaseSuiteJson() =>
        """{"suite_name":"calculator behaviour","using_directives":["using Demo;"],"helper_code":"","cases":[{"case_id":"H1","category":"happy_path","test_name":"happy","test_body":"var actual = new Calculator().Add(2, 3); Check.Equal(5, actual);"},{"case_id":"E1","category":"empty_or_invalid","test_name":"minimal","test_body":"var actual = new Calculator().Add(0, 0); Check.Equal(0, actual);"},{"case_id":"B1","category":"boundary_values","test_name":"boundary","test_body":"var sut = new Calculator(); Check.Equal(-1, sut.Add(-1, 0)); Check.Equal(0, sut.Add(0, 0)); Check.Equal(1, sut.Add(1, 0));"},{"case_id":"A1","category":"alternative_path","test_name":"alternative","test_body":"var actual = new Calculator().Add(-2, 3); Check.Equal(1, actual);"},{"case_id":"D1","category":"dependency_or_state","test_name":"dependency","test_body":"var actual = new Calculator().Add(6, 1); Check.Equal(7, actual);"}]}""";

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

    private sealed class QueuedAdapter(params string[] responses) : ILlmAdapter
    {
        private readonly Queue<string> _responses = new(responses);
        public List<LlmRequest> Requests { get; } = [];

        public Task<LlmResponse> CompleteAsync(LlmRequest request, CancellationToken cancellationToken = default)
        {
            Requests.Add(request);
            return Task.FromResult(new LlmResponse
            {
                Content = _responses.Dequeue(),
                InputTokens = 17,
                OutputTokens = 23
            });
        }

        public Task<LlmResponse> CompleteAsync(LlmConversation conversation, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();
    }
}
