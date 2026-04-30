using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
using HybridLens.StaticAnalysis.Detectors;
using HybridLens.Tests.Helpers;

namespace HybridLens.Tests.Detectors;

public sealed class LongMethodDetectorTests
{
    // Tight thresholds so tests stay short
    private static readonly LongMethodConfig Config = new()
    {
        MaxLinesOfCode          = 5,
        MaxCyclomaticComplexity = 3
    };

    private static LongMethodDetector Detector => new(Config);

    // ── Clean ─────────────────────────────────────────────────────────────────

    [Fact]
    public void Detect_MethodWithinBothLimits_ReturnsNoFindings()
    {
        const string code = """
            class C {
                void Clean() {
                    var x = 1;
                    var y = 2;
                }
            }
            """;

        var findings = Detector.Detect(CompilationHelper.CreateSyntaxOnly(code)).ToList();

        Assert.Empty(findings);
    }

    // ── LOC only ──────────────────────────────────────────────────────────────

    [Fact]
    public void Detect_MethodExceedingLocOnly_ReturnsWarning()
    {
        // 7 source lines > MaxLinesOfCode(5), CC = 1
        const string code = """
            class C {
                void Long() {
                    var a = 1;
                    var b = 2;
                    var c = 3;
                    var d = 4;
                    var e = 5;
                }
            }
            """;

        var findings = Detector.Detect(CompilationHelper.CreateSyntaxOnly(code)).ToList();

        var finding = Assert.Single(findings);
        Assert.Equal(Severity.Warning, finding.Severity);
        Assert.Equal(AntiPatternType.LongMethod, finding.Type);
        Assert.Contains("Long", finding.SymbolName);
    }

    // ── CC only ───────────────────────────────────────────────────────────────

    [Fact]
    public void Detect_MethodExceedingComplexityOnly_ReturnsWarning()
    {
        // 4 lines, but CC = 1 + 3 if-statements = 4 > MaxCC(3)
        const string code = """
            class C {
                void Complex(int x) {
                    if (x > 0) { }
                    if (x > 1) { }
                    if (x > 2) { }
                }
            }
            """;

        var findings = Detector.Detect(CompilationHelper.CreateSyntaxOnly(code)).ToList();

        var finding = Assert.Single(findings);
        Assert.Equal(Severity.Warning, finding.Severity);
        Assert.Equal(AntiPatternType.LongMethod, finding.Type);
    }

    // ── Both ──────────────────────────────────────────────────────────────────

    [Fact]
    public void Detect_MethodExceedingBothLimits_ReturnsCritical()
    {
        // 9 lines > LOC(5), CC = 1 + 4 branches = 5 > CC(3)
        const string code = """
            class C {
                void Both(int x) {
                    if (x > 0) { }
                    if (x > 1) { }
                    if (x > 2) { }
                    if (x > 3) { }
                    var a = 1;
                    var b = 2;
                    var c = 3;
                }
            }
            """;

        var findings = Detector.Detect(CompilationHelper.CreateSyntaxOnly(code)).ToList();

        var finding = Assert.Single(findings);
        Assert.Equal(Severity.Critical, finding.Severity);
    }

    // ── Metrics ───────────────────────────────────────────────────────────────

    [Fact]
    public void Detect_Finding_ExposesLinesOfCodeAndComplexityMetrics()
    {
        const string code = """
            class C {
                void Long() {
                    var a = 1;
                    var b = 2;
                    var c = 3;
                    var d = 4;
                    var e = 5;
                }
            }
            """;

        var finding = Detector.Detect(CompilationHelper.CreateSyntaxOnly(code)).Single();

        Assert.True(finding.Metrics.ContainsKey("LinesOfCode"));
        Assert.True(finding.Metrics.ContainsKey("CyclomaticComplexity"));
        Assert.True(finding.Metrics["LinesOfCode"] > Config.MaxLinesOfCode);
    }

    // ── Multiple methods ──────────────────────────────────────────────────────

    [Fact]
    public void Detect_MultipleMethodsOnlyViolatingOnesReported()
    {
        const string code = """
            class C {
                void Clean() { var x = 1; }

                void Long() {
                    var a = 1;
                    var b = 2;
                    var c = 3;
                    var d = 4;
                    var e = 5;
                }
            }
            """;

        var findings = Detector.Detect(CompilationHelper.CreateSyntaxOnly(code)).ToList();

        Assert.Single(findings);
        Assert.Contains("Long", findings[0].SymbolName);
    }
}
