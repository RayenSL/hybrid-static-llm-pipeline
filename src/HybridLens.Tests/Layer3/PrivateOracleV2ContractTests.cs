using System.Text.Json;

namespace HybridLens.Tests.Layer3;

public sealed class PrivateOracleV2ContractTests
{
    private static readonly string[] ExpectedCaseIds =
    [
        "P01-happy-flow",
        "P02-empty-or-minimal",
        "P03-invalid-input",
        "P04-below-boundary",
        "P05-at-boundary",
        "P06-above-boundary",
        "P07-alternate-valid-mode",
        "P08-collaborator-outcome",
        "P09-repeat-or-state-transition",
        "P10-compound-ordering",
    ];

    [Fact]
    public void PlanHasTenCasesForEveryEvaluatedTarget()
    {
        var root = FindRepositoryRoot();
        var path = Path.Combine(root, "layer3", "ORACLE_PLAN_V2.json");
        using var plan = JsonDocument.Parse(File.ReadAllText(path));
        var document = plan.RootElement;

        Assert.Equal("2.0.0", document.GetProperty("plan_version").GetString());
        var targets = document.GetProperty("evaluated_targets").EnumerateArray().ToArray();
        Assert.Equal(26, targets.Length);
        Assert.Equal(13, targets.Count(target => target.GetProperty("anti_pattern").GetString() == "GodClass"));
        Assert.Equal(13, targets.Count(target => target.GetProperty("anti_pattern").GetString() == "LongMethod"));

        foreach (var target in targets)
        {
            var cases = target.GetProperty("cases").EnumerateArray().ToArray();
            Assert.Equal(10, cases.Length);
            Assert.Equal(ExpectedCaseIds, cases.Select(item => item.GetProperty("case_id").GetString()));
            Assert.All(cases, item => Assert.False(string.IsNullOrWhiteSpace(item.GetProperty("obligation").GetString())));
        }

        Assert.Equal(260, targets.Sum(target => target.GetProperty("cases").GetArrayLength()));
        Assert.Equal(10, document.GetProperty("obsolete_smoke_cases").GetArrayLength());

        var goldenDirectory = Path.Combine(root, "layer3", "golden");
        var goldenFiles = Directory.EnumerateFiles(goldenDirectory, "*.golden")
            .Select(Path.GetFileName)
            .ToHashSet(StringComparer.Ordinal);
        Assert.Equal(270, goldenFiles.Count);
        foreach (var target in targets)
        foreach (var item in target.GetProperty("cases").EnumerateArray())
            Assert.Contains($"{target.GetProperty("instance_id").GetString()}.{item.GetProperty("case_id").GetString()}.golden", goldenFiles);

        var checksumLines = File.ReadAllLines(Path.Combine(root, "layer3", "GOLDEN_SHA256SUMS.txt"));
        Assert.Equal(270, checksumLines.Length);
    }

    private static string FindRepositoryRoot()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null && !File.Exists(Path.Combine(directory.FullName, "layer3", "PRIVATE_ORACLE_MANIFEST.md")))
            directory = directory.Parent;

        return directory?.FullName ?? throw new DirectoryNotFoundException("Repository root not found.");
    }
}
