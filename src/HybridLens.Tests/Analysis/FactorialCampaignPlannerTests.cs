using System.Security.Cryptography;
using System.Text;
using HybridLens.Core.Models;
using HybridLens.Pipeline;

namespace HybridLens.Tests.Analysis;

public sealed class FactorialCampaignPlannerTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), $"hl-campaign-{Guid.NewGuid():N}");

    [Fact]
    public async Task Create_FreezesEightConditionsPerBlock_AndRoundTrips()
    {
        var fixture = MakeFixture();
        var visible = MakeVisible(fixture.Source, fixture.Project, fixture.VisibleArtifact);
        var visibleByFile = new Dictionary<string, LoadedGeneratedTest>(StringComparer.OrdinalIgnoreCase)
        {
            [Path.GetFullPath(fixture.Source)] = visible
        };

        var manifest = FactorialCampaignPlanner.Create(
            [fixture.Seed], visibleByFile, fixture.Solution, fixture.Baseline,
            "frozen-model", "commit-abc", repetitions: 2, iterationBudget: 6,
            buildTimeoutSeconds: 180, maxInputTokenGuard: 120_000, randomizationSeed: 1729);

        Assert.Equal(16, manifest.Assignments.Count);
        Assert.Equal(2, manifest.Assignments.Select(a => a.BlockId).Distinct().Count());
        Assert.All(manifest.Assignments.GroupBy(a => a.BlockId), block => Assert.Equal(8, block.Count()));
        Assert.All(manifest.Assignments, assignment =>
        {
            Assert.Equal("Demo.Thing", assignment.SymbolName);
            Assert.Equal(1, assignment.Line);
            Assert.Equal(1, assignment.TargetEndLine);
        });
        Assert.Equal(Enumerable.Range(1, 16), manifest.Assignments.Select(a => a.Order));
        Assert.All(manifest.Assignments.Where(a => a.VisibleTestsEnabled),
            assignment => Assert.Equal(Path.GetFullPath(fixture.VisibleArtifact), assignment.VisibleTestArtifactRef));
        Assert.All(manifest.Assignments.Where(a => !a.VisibleTestsEnabled),
            assignment => Assert.Null(assignment.VisibleTestArtifactRef));
        Assert.Contains(manifest.Assignments,
            a => a.ControlStructure == "iterative" && a.VisibleTestsEnabled && a.PromptVersion == "v2.1.2");
        Assert.Contains(manifest.Assignments,
            a => a.ControlStructure == "iterative" && !a.VisibleTestsEnabled && a.PromptVersion == "v2.0.2");

        var second = FactorialCampaignPlanner.Create(
            [fixture.Seed], visibleByFile, fixture.Solution, fixture.Baseline,
            "frozen-model", "commit-abc", 2, 6, 180, 120_000, 1729);
        Assert.Equal(
            manifest.Assignments.Select(a => (a.AssignmentId, a.BlockId, a.GroundingEnabled, a.ControlStructure, a.VisibleTestsEnabled)),
            second.Assignments.Select(a => (a.AssignmentId, a.BlockId, a.GroundingEnabled, a.ControlStructure, a.VisibleTestsEnabled)));

        var manifestPath = Path.Combine(_root, "campaign.json");
        await FactorialCampaignManifestStore.SaveAsync(manifestPath, manifest);
        var loaded = await FactorialCampaignManifestStore.LoadAsync(manifestPath);
        Assert.Equal(manifest.CampaignId, loaded.CampaignId);
        Assert.Equal(16, loaded.Assignments.Count);
    }

    [Fact]
    public void Create_RejectsMultipleIncludedInstancesInOneFile()
    {
        var fixture = MakeFixture();
        var secondKnown = KnownInstance.Create(
            AntiPatternType.LongMethod, fixture.Source, "Demo.Thing.Other", 2,
            Severity.Warning, "void Other()");
        var secondFinding = new Finding
        {
            Type = AntiPatternType.LongMethod,
            Severity = Severity.Warning,
            FilePath = fixture.Source,
            SymbolName = "Demo.Thing.Other",
            Line = 2,
            Metrics = new Dictionary<string, double> { ["CC"] = 12 }
        };

        var error = Assert.Throws<InvalidDataException>(() => FactorialCampaignPlanner.Create(
            [fixture.Seed, new FactorialCampaignSeed(secondKnown, secondFinding)],
            new Dictionary<string, LoadedGeneratedTest>(StringComparer.OrdinalIgnoreCase),
            fixture.Solution, fixture.Baseline, "frozen-model", "commit-abc",
            1, 6, 180, 120_000, 7));

        Assert.Contains("one included instance per source file", error.Message);
    }

    [Fact]
    public void Validate_StopsWhenPristineSourceChangesAfterFreeze()
    {
        var fixture = MakeFixture();
        var manifest = FactorialCampaignPlanner.Create(
            [fixture.Seed], new Dictionary<string, LoadedGeneratedTest>(StringComparer.OrdinalIgnoreCase),
            fixture.Solution, fixture.Baseline, "frozen-model", "commit-abc",
            1, 6, 180, 120_000, 7);

        File.AppendAllText(fixture.Source, " // changed");

        var error = Assert.Throws<InvalidDataException>(() =>
            FactorialCampaignPlanner.Validate(manifest, verifyFiles: true));
        Assert.Contains("pristine source changed", error.Message);
    }

    private Fixture MakeFixture()
    {
        Directory.CreateDirectory(_root);
        var solution = Path.Combine(_root, "Corpus.sln");
        var baseline = Path.Combine(_root, "baseline.jsonl");
        var project = Path.Combine(_root, "Demo.csproj");
        var source = Path.Combine(_root, "Thing.cs");
        var visibleArtifact = Path.Combine(_root, "visible.json");
        File.WriteAllText(solution, "Microsoft Visual Studio Solution File");
        File.WriteAllText(baseline, """{"frozen":true}""" + Environment.NewLine);
        File.WriteAllText(project, """<Project Sdk="Microsoft.NET.Sdk" />""");
        File.WriteAllText(source, "namespace Demo; public class Thing { public int Value() => 7; }");
        var known = KnownInstance.Create(
            AntiPatternType.GodClass, source, "Demo.Thing", 1, Severity.Critical, "public class Thing");
        var finding = new Finding
        {
            Type = AntiPatternType.GodClass,
            Severity = Severity.Critical,
            FilePath = source,
            SymbolName = "Demo.Thing",
            Line = 1,
            Snippet = "public class Thing",
            Metrics = new Dictionary<string, double> { ["WMC"] = 60 }
        };
        return new Fixture(solution, baseline, project, source, visibleArtifact,
            new FactorialCampaignSeed(known, finding));
    }

    private static LoadedGeneratedTest MakeVisible(string sourceFile, string projectFile, string artifactRef)
    {
        var source = new GeneratedTestSource(
            "PreservesValue", ["using Demo;"], "Check.Equal(7, new Thing().Value());");
        var testHash = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(
            string.Join("\n", source.UsingDirectives) + "\n" + source.TestBody)));
        var artifact = new GeneratedTestArtifact
        {
            ArtifactId = "visible",
            ArtifactRef = artifactRef,
            Timestamp = DateTimeOffset.UtcNow,
            SourceFile = sourceFile,
            SourceSha256 = FactorialCampaignPlanner.SourceSha256(sourceFile),
            TargetSymbolName = "Demo.Thing",
            TargetStartLine = 1,
            TargetEndLine = 1,
            ProjectFile = projectFile,
            ModelName = "author-model",
            PromptVersion = "v1.1.0",
            RawSystemPrompt = "system",
            RawUserPrompt = "user",
            TestName = source.TestName,
            UsingDirectives = source.UsingDirectives,
            TestBody = source.TestBody,
            TestSha256 = testHash,
            AdmissionStatus = GeneratedTestAdmissionStatus.Admitted,
            ParsePassed = true,
            AssertionGatePassed = true,
            BuildPassed = true,
            BaselineRunsPassed = [true, true]
        };
        var jsonOptions = new System.Text.Json.JsonSerializerOptions
        {
            PropertyNamingPolicy = System.Text.Json.JsonNamingPolicy.SnakeCaseLower,
            Converters = { new System.Text.Json.Serialization.JsonStringEnumConverter(System.Text.Json.JsonNamingPolicy.SnakeCaseLower) },
            WriteIndented = true
        };
        File.WriteAllText(artifactRef, System.Text.Json.JsonSerializer.Serialize(artifact, jsonOptions));
        return new LoadedGeneratedTest(artifact, source);
    }

    public void Dispose()
    {
        try { if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true); } catch { }
    }

    private sealed record Fixture(
        string Solution,
        string Baseline,
        string Project,
        string Source,
        string VisibleArtifact,
        FactorialCampaignSeed Seed);
}
