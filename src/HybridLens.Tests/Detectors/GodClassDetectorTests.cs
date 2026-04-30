using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
using HybridLens.StaticAnalysis.Detectors;
using HybridLens.Tests.Helpers;

namespace HybridLens.Tests.Detectors;

public sealed class GodClassDetectorTests
{
    private static readonly GodClassConfig Config = new()
    {
        MaxMethods     = 2,
        MaxFields      = 2,
        MaxLinesOfCode = 15
    };

    private static GodClassDetector Detector => new(Config);

    // ── Clean ─────────────────────────────────────────────────────────────────

    [Fact]
    public void Detect_ClassWithinAllLimits_ReturnsNoFindings()
    {
        const string code = """
            class C {
                int _a;
                int _b;

                void M1() { }
                void M2() { }
            }
            """;

        var findings = Detector.Detect(CompilationHelper.CreateSyntaxOnly(code)).ToList();

        Assert.Empty(findings);
    }

    // ── Single violation → Warning ────────────────────────────────────────────

    [Fact]
    public void Detect_TooManyMethodsOnly_ReturnsWarning()
    {
        // 3 methods > MaxMethods(2), fields and LOC are fine
        const string code = """
            class C {
                void M1() { }
                void M2() { }
                void M3() { }
            }
            """;

        var findings = Detector.Detect(CompilationHelper.CreateSyntaxOnly(code)).ToList();

        var finding = Assert.Single(findings);
        Assert.Equal(Severity.Warning, finding.Severity);
        Assert.Equal(AntiPatternType.GodClass, finding.Type);
    }

    [Fact]
    public void Detect_TooManyFieldsOnly_ReturnsWarning()
    {
        // 3 fields > MaxFields(2)
        const string code = """
            class C {
                int _a;
                int _b;
                int _c;
            }
            """;

        var findings = Detector.Detect(CompilationHelper.CreateSyntaxOnly(code)).ToList();

        var finding = Assert.Single(findings);
        Assert.Equal(Severity.Warning, finding.Severity);
    }

    [Fact]
    public void Detect_PropertiesCountedTowardFieldLimit()
    {
        // 1 field + 2 properties = 3 > MaxFields(2)
        const string code = """
            class C {
                int _a;
                int PropB { get; set; }
                int PropC { get; set; }
            }
            """;

        var findings = Detector.Detect(CompilationHelper.CreateSyntaxOnly(code)).ToList();

        var finding = Assert.Single(findings);
        Assert.Equal(Severity.Warning, finding.Severity);
    }

    // ── Two violations → Critical ─────────────────────────────────────────────

    [Fact]
    public void Detect_TwoThresholdsExceeded_ReturnsCritical()
    {
        // 3 methods > MaxMethods(2) AND 3 fields > MaxFields(2)
        const string code = """
            class C {
                int _a;
                int _b;
                int _c;

                void M1() { }
                void M2() { }
                void M3() { }
            }
            """;

        var findings = Detector.Detect(CompilationHelper.CreateSyntaxOnly(code)).ToList();

        var finding = Assert.Single(findings);
        Assert.Equal(Severity.Critical, finding.Severity);
    }

    // ── Symbol name ───────────────────────────────────────────────────────────

    [Fact]
    public void Detect_NamespacedClass_IncludesNamespaceInSymbolName()
    {
        const string code = """
            namespace My.App {
                class BigClass {
                    int _a; int _b; int _c;
                    void M1() { } void M2() { } void M3() { }
                }
            }
            """;

        var finding = Detector.Detect(CompilationHelper.CreateSyntaxOnly(code)).Single();

        Assert.Contains("My.App", finding.SymbolName);
        Assert.Contains("BigClass", finding.SymbolName);
    }

    // ── Metrics ───────────────────────────────────────────────────────────────

    [Fact]
    public void Detect_Finding_ExposesMethodFieldAndLocMetrics()
    {
        const string code = """
            class C {
                int _a; int _b; int _c;
                void M1() { } void M2() { } void M3() { }
            }
            """;

        var finding = Detector.Detect(CompilationHelper.CreateSyntaxOnly(code)).Single();

        Assert.True(finding.Metrics.ContainsKey("Methods"));
        Assert.True(finding.Metrics.ContainsKey("Fields"));
        Assert.True(finding.Metrics.ContainsKey("LinesOfCode"));
    }
}
