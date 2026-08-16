using HybridLens.ContextBuilder;
using HybridLens.Core.Configuration;
using HybridLens.Core.Models;

namespace HybridLens.Tests.Context;

/// <summary>
/// The ladder is the single authority for what a context level means (§4.4.3). These tests protect
/// the two properties that authority exists to provide: that a definition cannot change without its
/// hash changing, and that the rendered prompt actually follows the definition.
///
/// The sealed supplement is the motivating failure. <c>BuildFull</c> promised "other findings in the
/// same file" while its caller passed a single-element list, so the clause was dead, Full collapsed
/// onto Relational, and nothing detected the divergence between the written and executed definition.
/// </summary>
public sealed class ContextLadderTests
{
    private static Finding MakeFinding(string path) => new()
    {
        Type = AntiPatternType.LongMethod,
        Severity = Severity.Warning,
        FilePath = path,
        SymbolName = "Demo.Thing.Run",
        Line = 3,
        Snippet = "public void Run() { }",
        Metrics = new Dictionary<string, double> { ["CyclomaticComplexity"] = 14 }
    };

    private static CrossFileDeclaration Declaration(string relative, string source) => new()
    {
        RelativePath = relative,
        DeclaredTypes = ["NotifyApiV2"],
        Source = source,
        Sha256 = "unchecked-in-render"
    };

    [Fact]
    public void LadderHash_IsStable_AndDistinguishesVersions()
    {
        Assert.Equal(ContextLadder.Sha256(ContextLadder.V1), ContextLadder.Sha256(ContextLadder.V1));
        Assert.NotEqual(ContextLadder.Sha256(ContextLadder.V1), ContextLadder.Sha256(ContextLadder.V2));
        Assert.Equal(ContextLadder.V1, ContextLadder.ForVersion(ContextLadder.V1Version));
        Assert.Equal(ContextLadder.V2, ContextLadder.ForVersion(ContextLadder.V2Version));
        Assert.Throws<ArgumentOutOfRangeException>(() => ContextLadder.ForVersion("ladder-v9.9.9"));
    }

    [Fact]
    public void BothLadders_DefineAllFourLevels()
    {
        foreach (var ladder in new[] { ContextLadder.V1, ContextLadder.V2 })
        {
            foreach (var level in new[]
                     {
                         ContextLevel.Minimal, ContextLevel.Structural,
                         ContextLevel.Relational, ContextLevel.Full
                     })
            {
                Assert.Equal(level, ContextLadder.For(ladder, level).Level);
            }
        }
    }

    [Fact]
    public void V1Full_KeepsProjectMetadata_AndSuppliesNoCrossFileSection()
    {
        var path = Path.GetTempFileName();
        try
        {
            File.WriteAllText(path, "public class Thing { public void Run() { } }");
            var config = new ContextConfig
            {
                Level = ContextLevel.Full,
                Ladder = ContextLadder.V1,
                Metadata = new Dictionary<string, string> { ["Framework"] = ".NET 8" }
            };

            var prompt = new HybridLens.ContextBuilder.ContextBuilder()
                .Build(MakeFinding(path), [MakeFinding(path)], config).UserPrompt;

            Assert.Contains("## Project metadata", prompt);
            Assert.Contains("Framework: .NET 8", prompt);
            Assert.DoesNotContain("## Referenced declarations", prompt);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void V1Full_IgnoresCrossFileDeclarations_SoTheSealedSupplementStaysReproducible()
    {
        var path = Path.GetTempFileName();
        try
        {
            File.WriteAllText(path, "public class Thing { public void Run() { } }");
            var finding = MakeFinding(path);

            string Render(IReadOnlyList<CrossFileDeclaration> declarations) =>
                new HybridLens.ContextBuilder.ContextBuilder().Build(finding, [finding], new ContextConfig
                {
                    Level = ContextLevel.Full,
                    Ladder = ContextLadder.V1,
                    Metadata = new Dictionary<string, string> { ["Framework"] = ".NET 8" },
                    CrossFileDeclarations = declarations
                }).UserPrompt;

            // A payload present on the config must not leak into a ladder whose Full rung does not
            // ask for it; otherwise the sealed campaign could not be reproduced from its manifest.
            Assert.Equal(
                Render([]),
                Render([Declaration("src/Legacy/NotifyApi.cs", "public static class NotifyApiV2 { }")]));
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void V2Full_SuppliesCrossFileDeclarations_InsteadOfProjectMetadata()
    {
        var path = Path.GetTempFileName();
        try
        {
            File.WriteAllText(path, "public class Thing { public void Run() { } }");
            var config = new ContextConfig
            {
                Level = ContextLevel.Full,
                Ladder = ContextLadder.V2,
                Metadata = new Dictionary<string, string> { ["Framework"] = ".NET 8" },
                CrossFileDeclarations =
                [
                    Declaration("src/Scheduling/Legacy/NotifyApi.cs",
                        "public static class NotifyApiV2 { public static bool Send(Notification n) => true; }")
                ]
            };

            var prompt = new HybridLens.ContextBuilder.ContextBuilder()
                .Build(MakeFinding(path), [MakeFinding(path)], config).UserPrompt;

            // This is the information the supplement's applier reported as missing, assignment
            // after assignment, while the replacement sat one file away.
            Assert.Contains("## Referenced declarations", prompt);
            Assert.Contains("src/Scheduling/Legacy/NotifyApi.cs", prompt);
            Assert.Contains("Declares: NotifyApiV2", prompt);
            Assert.Contains("public static class NotifyApiV2", prompt);
            Assert.DoesNotContain("## Project metadata", prompt);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void RenderedLevels_FollowTheirSpecFlags()
    {
        var path = Path.GetTempFileName();
        try
        {
            File.WriteAllText(path, "public class Thing\n{\n    public void Run() { }\n}\n");
            var finding = MakeFinding(path);

            foreach (var ladder in new[] { ContextLadder.V1, ContextLadder.V2 })
            {
                foreach (var level in new[]
                         {
                             ContextLevel.Minimal, ContextLevel.Structural,
                             ContextLevel.Relational, ContextLevel.Full
                         })
                {
                    var spec = ContextLadder.For(ladder, level);
                    var prompt = new HybridLens.ContextBuilder.ContextBuilder()
                        .Build(finding, [finding], new ContextConfig { Level = level, Ladder = ladder })
                        .UserPrompt;

                    Assert.Equal(spec.IncludeMetrics, prompt.Contains("## Metrics"));
                    Assert.Equal(spec.IncludeSurroundingWindow, prompt.Contains("## Surrounding code"));
                }
            }
        }
        finally { File.Delete(path); }
    }
}
