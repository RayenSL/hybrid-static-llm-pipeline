using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
using HybridLens.StaticAnalysis.Detectors;
using HybridLens.Tests.Helpers;

namespace HybridLens.Tests.Detectors;

/// <summary>
/// Long Method detection uses cyclomatic complexity as the primary gate; lines-of-code
/// is a secondary signal that only escalates an already-flagged method to Critical.
/// A method that is long but simple (high LOC, low CC) is NOT flagged.
/// </summary>
public sealed class LongMethodDetectorTests
{
    private static readonly LongMethodConfig Config = new()
    {
        MaxCyclomaticComplexity = 3,   // primary gate
        MaxLinesOfCode          = 5    // secondary (severity escalation)
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

    // ── LOC high but CC low → NOT flagged (CC is the gate) ─────────────────────

    [Fact]
    public void Detect_LongButSimpleMethod_NotFlagged()
    {
        // 7 source lines > MaxLinesOfCode(5), but CC = 1 ≤ MaxCC(3) → not flagged
        const string code = """
            class C {
                void LongButSimple() {
                    var a = 1;
                    var b = 2;
                    var c = 3;
                    var d = 4;
                    var e = 5;
                }
            }
            """;

        var findings = Detector.Detect(CompilationHelper.CreateSyntaxOnly(code)).ToList();

        Assert.Empty(findings);
    }

    // ── CC exceeds, LOC within → Warning ───────────────────────────────────────

    [Fact]
    public void Detect_ComplexButShortMethod_ReturnsWarning()
    {
        // CC = 1 + 3 ifs = 4 > MaxCC(3); LOC = 5 (not > 5) → Warning
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

    // ── CC exceeds AND LOC exceeds → Critical ──────────────────────────────────

    [Fact]
    public void Detect_ComplexAndLongMethod_ReturnsCritical()
    {
        // CC = 1 + 4 = 5 > MaxCC(3); LOC = 9 > MaxLOC(5) → Critical
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

    // ── Metrics exposed ─────────────────────────────────────────────────────────

    [Fact]
    public void Detect_Finding_ExposesComplexityAndLocMetrics()
    {
        const string code = """
            class C {
                void Complex(int x) {
                    if (x > 0) { }
                    if (x > 1) { }
                    if (x > 2) { }
                }
            }
            """;

        var finding = Detector.Detect(CompilationHelper.CreateSyntaxOnly(code)).Single();

        Assert.True(finding.Metrics.ContainsKey("CyclomaticComplexity"));
        Assert.True(finding.Metrics.ContainsKey("LinesOfCode"));
        Assert.True(finding.Metrics["CyclomaticComplexity"] > Config.MaxCyclomaticComplexity);
    }

    // ── Multiple methods — only the complex one reported ───────────────────────

    [Fact]
    public void Detect_MultipleMethods_OnlyComplexOnesReported()
    {
        const string code = """
            class C {
                void Clean() { var x = 1; }

                void Complex(int x) {
                    if (x > 0) { }
                    if (x > 1) { }
                    if (x > 2) { }
                }
            }
            """;

        var findings = Detector.Detect(CompilationHelper.CreateSyntaxOnly(code)).ToList();

        Assert.Single(findings);
        Assert.Contains("Complex", findings[0].SymbolName);
    }
}
