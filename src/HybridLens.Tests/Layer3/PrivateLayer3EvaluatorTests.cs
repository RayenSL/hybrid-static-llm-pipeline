using HybridLens.Core.Models;
using HybridLens.Pipeline;

namespace HybridLens.Tests.Layer3;

public sealed class PrivateLayer3EvaluatorTests : IDisposable
{
    private readonly List<string> _temp = [];

    [Fact]
    public async Task EvaluatesOpaqueArtifact_InIsolatedPristineCopy()
    {
        var fixture = MakeFixture();
        var artifactPath = await WriteArtifact(fixture.Artifacts, fixture.RelativeFile, "// repaired", buildPassed: true);
        var calls = 0;
        var evaluator = new PrivateLayer3Evaluator(
            fixture.Solution,
            fixture.Oracle,
            "1.0.0",
            30,
            async (project, golden, _, ct) =>
            {
                calls++;
                Assert.True(File.Exists(project));
                Assert.Equal(Path.GetFullPath(Path.Combine(fixture.Oracle, "golden")), Path.GetFullPath(golden));
                var sourceRoot = Directory.GetParent(Path.GetDirectoryName(project)!)!;
                Assert.Equal("src", sourceRoot.Name, ignoreCase: true);
                var workingRoot = sourceRoot.Parent!.FullName;
                var materialized = Path.Combine(workingRoot, fixture.RelativeFile);
                Assert.Equal("// repaired", await File.ReadAllTextAsync(materialized, ct));
                return (true, "PASS  A\nPASS  B\nALL PASS\n");
            });

        var result = await evaluator.EvaluateOneAsync(artifactPath);

        Assert.Equal(1, calls);
        Assert.True(result.Evaluated);
        Assert.True(result.Passed);
        Assert.Equal(2, result.PassingDrivers);
        Assert.Equal(0, result.FailingDrivers);
        Assert.Equal("1.0.0", result.OracleManifestVersion);
        Assert.Null(result.NotRunReason);
        Assert.DoesNotContain("ground", result.ToString(), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task NonBuildingArtifact_IsRecordedWithoutExecutingOracle()
    {
        var fixture = MakeFixture();
        var artifactPath = await WriteArtifact(fixture.Artifacts, fixture.RelativeFile, "// broken", buildPassed: false);
        var evaluator = new PrivateLayer3Evaluator(
            fixture.Solution,
            fixture.Oracle,
            "1.0.0",
            30,
            (_, _, _, _) => throw new Xunit.Sdk.XunitException("oracle must not execute for a non-building state"));

        var result = await evaluator.EvaluateOneAsync(artifactPath);

        Assert.False(result.Evaluated);
        Assert.Null(result.Passed);
        Assert.Equal("production_build_failed", result.NotRunReason);
    }

    [Fact]
    public async Task RejectsTamperedFinalSource()
    {
        var fixture = MakeFixture();
        var artifactPath = await WriteArtifact(fixture.Artifacts, fixture.RelativeFile, "// original", buildPassed: true);
        var json = await File.ReadAllTextAsync(artifactPath);
        await File.WriteAllTextAsync(artifactPath, json.Replace("// original", "// tampered", StringComparison.Ordinal));
        var evaluator = new PrivateLayer3Evaluator(fixture.Solution, fixture.Oracle, "1.0.0", 30,
            (_, _, _, _) => Task.FromResult((true, "ALL PASS")));

        await Assert.ThrowsAsync<InvalidDataException>(() => evaluator.EvaluateOneAsync(artifactPath));
    }

    [Fact]
    public void CanonicalPrivateOracle_MatchesFrozenManifest()
    {
        var repositoryRoot = FindRepositoryRoot();
        var manifest = Path.Combine(repositoryRoot, "layer3", "PRIVATE_ORACLE_MANIFEST.md");
        Assert.Equal("2.0.0", PrivateOracleManifestVerifier.Verify(manifest));
    }

    [Fact]
    public void ManifestVerifier_ValidatesFilesListedByChecksumIndex()
    {
        var root = NewTemp();
        var layer3 = Path.Combine(root, "layer3");
        var golden = Path.Combine(layer3, "golden");
        Directory.CreateDirectory(golden);
        var valuePath = Path.Combine(golden, "case.golden");
        File.WriteAllText(valuePath, "expected");
        var valueHash = Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(valuePath)));
        var indexPath = Path.Combine(layer3, "GOLDEN_SHA256SUMS.txt");
        File.WriteAllText(indexPath, $"{valueHash}  layer3/golden/case.golden\n");
        var indexHash = Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(indexPath)));
        var manifest = Path.Combine(layer3, "PRIVATE_ORACLE_MANIFEST.md");
        File.WriteAllText(manifest, $"Manifest version: 2.0.0\n{indexHash}  layer3/GOLDEN_SHA256SUMS.txt\n");

        Assert.Equal("2.0.0", PrivateOracleManifestVerifier.Verify(manifest));
        File.WriteAllText(valuePath, "tampered");
        Assert.Throws<InvalidDataException>(() => PrivateOracleManifestVerifier.Verify(manifest));
    }

    private async Task<string> WriteArtifact(
        string directory,
        string relativeFile,
        string source,
        bool buildPassed)
    {
        var artifact = new MaterializedSourceArtifact
        {
            ArtifactId = Guid.NewGuid().ToString("N"),
            Timestamp = DateTimeOffset.UtcNow,
            Architecture = "should_be_ignored",
            GroundingEnabled = true,
            ControlStructure = "should_be_ignored",
            VisibleTestsEnabled = true,
            VisibleTestAvailable = true,
            RunNumber = 1,
            RelativeFile = relativeFile.Replace('\\', '/'),
            SourceSha256 = MaterializedSourceArtifactWriter.Sha256(source),
            FinalSource = source,
            BuildPassed = buildPassed
        };
        return await MaterializedSourceArtifactWriter.WriteAsync(directory, artifact);
    }

    private Fixture MakeFixture()
    {
        var root = NewTemp();
        var corpus = Path.Combine(root, "corpus");
        Directory.CreateDirectory(corpus);
        var solution = Path.Combine(corpus, "Corpus.sln");
        File.WriteAllText(solution, "Microsoft Visual Studio Solution File");
        var relative = Path.Combine("src", "Proj", "Thing.cs");
        Directory.CreateDirectory(Path.Combine(corpus, "src", "Proj"));
        File.WriteAllText(Path.Combine(corpus, relative), "// pristine");

        var oracle = Path.Combine(root, "oracle");
        Directory.CreateDirectory(Path.Combine(oracle, "characterization"));
        Directory.CreateDirectory(Path.Combine(oracle, "golden"));
        File.WriteAllText(Path.Combine(oracle, "characterization", "Characterization.csproj"),
            "<Project Sdk=\"Microsoft.NET.Sdk\" />");
        File.WriteAllText(Path.Combine(oracle, "characterization", "Program.cs"), "return 0;");
        var artifacts = Path.Combine(root, "artifacts");
        Directory.CreateDirectory(artifacts);
        return new Fixture(solution, oracle, artifacts, relative);
    }

    private string NewTemp()
    {
        var path = Path.Combine(Path.GetTempPath(), $"hl-layer3-{Guid.NewGuid():N}");
        Directory.CreateDirectory(path);
        _temp.Add(path);
        return path;
    }

    private static string FindRepositoryRoot()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null && !File.Exists(Path.Combine(directory.FullName, "layer3", "PRIVATE_ORACLE_MANIFEST.md")))
            directory = directory.Parent;
        return directory?.FullName ?? throw new DirectoryNotFoundException("repository root not found");
    }

    public void Dispose()
    {
        foreach (var path in _temp)
            try { if (Directory.Exists(path)) Directory.Delete(path, recursive: true); } catch { }
    }

    private sealed record Fixture(string Solution, string Oracle, string Artifacts, string RelativeFile);
}
