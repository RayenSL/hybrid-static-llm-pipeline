using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.Core.Models;
using HybridLens.Pipeline;

namespace HybridLens.Tests.Layer3;

/// <summary>
/// The post-seal oracle is three-valued on purpose. A harness that no longer compiles against a
/// repaired tree is a public-contract change, not a behavioural regression: Extract Class may move
/// members while preserving behaviour, leaving the frozen oracle unable to bind (thesis 4.5.5).
/// </summary>
public sealed class ExternalOracleEvaluatorTests : IDisposable
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) }
    };

    private readonly string _root = Path.Combine(
        Path.GetTempPath(), $"external-oracle-tests-{Guid.NewGuid():N}");

    private readonly string _product;
    private readonly string _solution;
    private readonly string _harness;
    private readonly string _golden;
    private readonly string _artifacts;

    public ExternalOracleEvaluatorTests()
    {
        _product = Path.Combine(_root, "product");
        _artifacts = Path.Combine(_root, "artifacts");
        _golden = Path.Combine(_root, "golden");
        Directory.CreateDirectory(Path.Combine(_product, "src"));
        Directory.CreateDirectory(_artifacts);
        Directory.CreateDirectory(_golden);

        _solution = Path.Combine(_product, "Product.sln");
        File.WriteAllText(_solution, "solution");
        File.WriteAllText(Path.Combine(_product, "src", "Target.cs"), "pristine");

        _harness = Path.Combine(_root, "Harness.csproj");
        File.WriteAllText(_harness, "<Project />");
    }

    private string WriteArtifact(bool? buildPassed)
    {
        const string finalSource = "repaired";
        var artifact = new MaterializedSourceArtifact
        {
            ArtifactId = Guid.NewGuid().ToString("N"),
            Timestamp = DateTimeOffset.UnixEpoch,
            Architecture = "ungrounded_single_shot",
            GroundingEnabled = false,
            ControlStructure = "single_shot",
            VisibleTestsEnabled = false,
            VisibleTestAvailable = false,
            RunNumber = 1,
            RelativeFile = Path.Combine("src", "Target.cs").Replace('\\', '/'),
            FinalSource = finalSource,
            SourceSha256 = MaterializedSourceArtifactWriter.Sha256(finalSource),
            BuildPassed = buildPassed
        };
        var path = Path.Combine(_artifacts, $"{artifact.ArtifactId}.json");
        File.WriteAllText(path, JsonSerializer.Serialize(artifact, JsonOptions), new UTF8Encoding(false));
        return path;
    }

    private ExternalOracleEvaluator Evaluator(
        bool harnessBuilds, bool checkPasses, string checkOutput = "",
        List<string>? capturedProperties = null) =>
        new(
            _solution, _harness, _golden,
            harnessProperties: [$"-p:ProductRoot={ExternalOracleEvaluator.WorkingRootToken}"],
            buildArguments: ["--no-restore"],
            timeoutSeconds: 30,
            buildHarness: (_, properties, _, _) =>
            {
                capturedProperties?.AddRange(properties);
                return Task.FromResult((harnessBuilds, harnessBuilds ? "" : "CS0117 missing member"));
            },
            runHarness: (_, _, _, _) => Task.FromResult((checkPasses, checkOutput)));

    [Fact]
    public async Task Preserved_behaviour_is_reported_with_driver_counts()
    {
        var artifact = WriteArtifact(buildPassed: true);
        var evaluator = Evaluator(harnessBuilds: true, checkPasses: true,
            checkOutput: "PASS  A\nPASS  B\nALL PASS\n");

        var result = await evaluator.EvaluateOneAsync(artifact);

        Assert.Equal("behaviour_preserved", result.Outcome);
        Assert.True(result.Passed);
        Assert.Equal(2, result.PassingDrivers);
        Assert.Equal(0, result.FailingDrivers);
    }

    [Fact]
    public async Task A_differing_driver_is_a_behavioural_change()
    {
        var artifact = WriteArtifact(buildPassed: true);
        var evaluator = Evaluator(harnessBuilds: true, checkPasses: false,
            checkOutput: "PASS  A\nREGRESSION  B\n1 REGRESSION(S)\n");

        var result = await evaluator.EvaluateOneAsync(artifact);

        Assert.Equal("behavioural_change", result.Outcome);
        Assert.False(result.Passed);
        Assert.Equal(1, result.PassingDrivers);
        Assert.Equal(1, result.FailingDrivers);
    }

    [Fact]
    public async Task A_harness_that_no_longer_compiles_is_a_public_contract_change()
    {
        var artifact = WriteArtifact(buildPassed: true);
        var evaluator = Evaluator(harnessBuilds: false, checkPasses: true);

        var result = await evaluator.EvaluateOneAsync(artifact);

        Assert.Equal("public_contract_change", result.Outcome);
        Assert.Null(result.Passed);
        Assert.Contains("CS0117", result.OutputTail);
    }

    [Fact]
    public async Task A_repair_that_never_built_is_not_evaluated()
    {
        var artifact = WriteArtifact(buildPassed: false);
        var evaluator = Evaluator(harnessBuilds: true, checkPasses: true);

        var result = await evaluator.EvaluateOneAsync(artifact);

        Assert.Equal("production_build_failed", result.Outcome);
        Assert.Null(result.Passed);
    }

    [Fact]
    public async Task The_working_root_token_is_substituted_so_the_harness_sees_the_repair()
    {
        var artifact = WriteArtifact(buildPassed: true);
        var captured = new List<string>();
        var evaluator = Evaluator(harnessBuilds: true, checkPasses: true,
            checkOutput: "ALL PASS\n", capturedProperties: captured);

        await evaluator.EvaluateOneAsync(artifact);

        var property = Assert.Single(captured, p => p.StartsWith("-p:ProductRoot=", StringComparison.Ordinal));
        Assert.DoesNotContain(ExternalOracleEvaluator.WorkingRootToken, property);
        Assert.DoesNotContain(Path.GetFullPath(_product), property);
        Assert.Contains("--no-restore", captured);
    }

    [Fact]
    public async Task A_tampered_artefact_is_rejected_before_any_build()
    {
        var path = WriteArtifact(buildPassed: true);
        var text = await File.ReadAllTextAsync(path);
        await File.WriteAllTextAsync(path, text.Replace("repaired", "tampered"));

        await Assert.ThrowsAsync<InvalidDataException>(
            () => Evaluator(harnessBuilds: true, checkPasses: true).EvaluateOneAsync(path));
    }

    public void Dispose()
    {
        try { if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true); }
        catch { /* best effort */ }
    }
}
