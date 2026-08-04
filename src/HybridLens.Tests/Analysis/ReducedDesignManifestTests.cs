using HybridLens.Core.Models;
using HybridLens.Pipeline;

namespace HybridLens.Tests.Analysis;

/// <summary>
/// A manifest may declare a reduced design so a transfer probe on an arbitrary solution reuses the
/// campaign machinery. Absent that declaration the confirmatory eight-cell factorial is still
/// enforced, which is what every frozen manifest depends on.
/// </summary>
public sealed class ReducedDesignManifestTests
{
    private static FactorialCampaignAssignment Assignment(
        int order, string blockId, bool grounded, string control, bool tests) =>
        new()
        {
            Order = order,
            AssignmentId = $"a{order:D3}",
            BlockId = blockId,
            RunNumber = 1,
            AntiPatternType = AntiPatternType.LongMethod,
            FilePath = @"C:\probe\Target.cs",
            SymbolName = "Target.Method",
            Line = 10,
            TargetEndLine = 40,
            Severity = Severity.Warning,
            Snippet = "public void Method() { }",
            PristineSourceSha256 = new string('a', 64),
            GroundingEnabled = grounded,
            ControlStructure = control,
            VisibleTestsEnabled = tests,
            PromptVersion = ContextBuilder.FactorialSingleShotPrompt.Version,
        };

    private static FactorialCampaignManifest Manifest(
        IReadOnlyList<FactorialCampaignAssignment> assignments,
        IReadOnlyList<string>? signatures) =>
        new()
        {
            Version = FactorialCampaignPlanner.Version,
            CampaignId = "probe-campaign-id",
            CreatedAt = DateTimeOffset.UnixEpoch,
            CodeRevision = "abc1234",
            RandomizationSeed = 20260804,
            ModelName = "gpt-5.6-sol",
            Repetitions = 1,
            IterationBudget = 1,
            BuildTimeoutSeconds = 600,
            MaxInputTokenGuard = 60_000,
            TargetSolution = @"C:\probe\Probe.sln",
            BaselineSource = @"C:\probe\baseline.json",
            BaselineSha256 = new string('b', 64),
            ConditionSignatures = signatures,
            Assignments = assignments,
        };

    private static readonly string[] GroundingOnly =
        ["False|single_shot|False", "True|single_shot|False"];

    [Fact]
    public void ExpectedSignatures_defaults_to_the_eight_cell_factorial()
    {
        var manifest = Manifest([Assignment(1, "b1", false, "single_shot", false)], signatures: null);

        var expected = FactorialCampaignPlanner.ExpectedSignatures(manifest);

        Assert.Equal(8, expected.Count);
        Assert.Contains("True|iterative|True", expected);
    }

    [Fact]
    public void ExpectedSignatures_honours_a_declared_reduced_design()
    {
        var manifest = Manifest([Assignment(1, "b1", false, "single_shot", false)], GroundingOnly);

        Assert.Equal(GroundingOnly, FactorialCampaignPlanner.ExpectedSignatures(manifest));
    }

    [Fact]
    public void Validate_accepts_a_two_condition_block_when_the_design_declares_it()
    {
        var manifest = Manifest(
        [
            Assignment(1, "b1", grounded: false, "single_shot", tests: false),
            Assignment(2, "b1", grounded: true,  "single_shot", tests: false),
        ], GroundingOnly);

        FactorialCampaignPlanner.Validate(manifest, verifyFiles: false);
    }

    [Fact]
    public void Validate_still_rejects_a_two_condition_block_without_a_declared_design()
    {
        var manifest = Manifest(
        [
            Assignment(1, "b1", grounded: false, "single_shot", tests: false),
            Assignment(2, "b1", grounded: true,  "single_shot", tests: false),
        ], signatures: null);

        var ex = Assert.Throws<InvalidDataException>(
            () => FactorialCampaignPlanner.Validate(manifest, verifyFiles: false));
        Assert.Contains("declared design has 8", ex.Message);
    }

    [Fact]
    public void Validate_rejects_a_block_that_misses_a_declared_condition()
    {
        var manifest = Manifest(
        [
            Assignment(1, "b1", grounded: false, "single_shot", tests: false),
            Assignment(2, "b1", grounded: false, "single_shot", tests: false),
        ], GroundingOnly);

        Assert.Throws<InvalidDataException>(
            () => FactorialCampaignPlanner.Validate(manifest, verifyFiles: false));
    }

    [Fact]
    public void ExpectedSignatures_rejects_a_malformed_declaration()
    {
        var manifest = Manifest([Assignment(1, "b1", false, "single_shot", false)],
            ["False|no_such_control|False"]);

        Assert.Throws<InvalidDataException>(() => FactorialCampaignPlanner.ExpectedSignatures(manifest));
    }

    [Fact]
    public void ExpectedSignatures_rejects_duplicates()
    {
        var manifest = Manifest([Assignment(1, "b1", false, "single_shot", false)],
            ["False|single_shot|False", "False|single_shot|False"]);

        Assert.Throws<InvalidDataException>(() => FactorialCampaignPlanner.ExpectedSignatures(manifest));
    }
}
