using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
using HybridLens.StaticAnalysis.Detectors;
using HybridLens.Tests.Helpers;

namespace HybridLens.Tests.Detectors;

/// <summary>
/// God Class detection follows the Lanza &amp; Marinescu composite strategy:
/// flag iff (ATFD &gt; FEW) ∧ (WMC ≥ VERY_HIGH) ∧ (TCC &lt; 1/3), all simultaneously.
/// The production thresholds (FEW=4, VERY_HIGH=47) require large classes, so these
/// tests use deliberately small thresholds to exercise the composite LOGIC on compact
/// fixtures. The exact metric computations are pinned separately in ClassMetricsTests.
/// Requires the semantic model → CreateWithReferences.
/// </summary>
public sealed class GodClassDetectorTests
{
    private static readonly GodClassConfig Config = new()
    {
        AtfdFew      = 1,    // ATFD must be > 1  (i.e. ≥ 2)
        WmcVeryHigh  = 4,    // WMC must be ≥ 4
        TccThreshold = 0.5   // TCC must be < 0.5
    };

    private static GodClassDetector Detector => new(Config);

    // A foreign class providing distinct attributes to drive ATFD.
    private const string ForeignDecl = "class Foreign { public int A; public int B; public int C; }";

    // ── All three conditions hold → flagged Critical ───────────────────────────

    [Fact]
    public void Detect_AllThreeConditionsMet_ReturnsCritical()
    {
        // ATFD = 3 (A,B,C) > 1 ; WMC = 6 (3 methods × CC 2) ≥ 4 ;
        // TCC = 1/3 (M1&M2 share _x; M3 isolated) < 0.5
        var code = $$"""
            {{ForeignDecl}}
            class God {
                private int _x;
                private int _y;
                public void M1(Foreign f) { if (f.A > 0) { _x = f.A; } }
                public void M2(Foreign f) { if (f.B > 0) { _x = f.B; } }
                public void M3(Foreign f) { if (f.C > 0) { _y = f.C; } }
            }
            """;

        var findings = Detector.Detect(CompilationHelper.CreateWithReferences(code)).ToList();

        var finding = Assert.Single(findings, f => f.SymbolName.Contains("God"));
        Assert.Equal(Severity.Critical, finding.Severity);
        Assert.Equal(AntiPatternType.GodClass, finding.Type);
    }

    // ── Low ATFD blocks detection ───────────────────────────────────────────────

    [Fact]
    public void Detect_HighWmcLowCohesionButNoForeignData_NotFlagged()
    {
        // ATFD = 0 (no foreign access) → fails, despite WMC=6 and TCC=1/3
        const string code = """
            class SelfContained {
                private int _x;
                private int _y;
                public void M1() { if (_x > 0) { _x = 1; } }
                public void M2() { if (_x > 1) { _x = 2; } }
                public void M3() { if (_y > 0) { _y = 1; } }
            }
            """;

        var findings = Detector.Detect(CompilationHelper.CreateWithReferences(code)).ToList();

        Assert.Empty(findings);
    }

    // ── Low WMC blocks detection ────────────────────────────────────────────────

    [Fact]
    public void Detect_HighAtfdLowCohesionButLowComplexity_NotFlagged()
    {
        // ATFD = 3, TCC = 1/3, but WMC = 3 (3 methods × CC 1) < 4 → not flagged
        var code = $$"""
            {{ForeignDecl}}
            class Simple {
                private int _x;
                private int _y;
                public void M1(Foreign f) { _x = f.A; }
                public void M2(Foreign f) { _x = f.B; }
                public void M3(Foreign f) { _y = f.C; }
            }
            """;

        var findings = Detector.Detect(CompilationHelper.CreateWithReferences(code)).ToList();

        Assert.Empty(findings);
    }

    // ── High cohesion blocks detection ──────────────────────────────────────────

    [Fact]
    public void Detect_HighAtfdHighWmcButCohesive_NotFlagged()
    {
        // ATFD = 3, WMC = 6, but all methods share _x → TCC = 1.0 ≥ 0.5 → not flagged
        var code = $$"""
            {{ForeignDecl}}
            class Cohesive {
                private int _x;
                public void M1(Foreign f) { if (f.A > 0) { _x = f.A; } }
                public void M2(Foreign f) { if (f.B > 0) { _x = f.B; } }
                public void M3(Foreign f) { if (f.C > 0) { _x = f.C; } }
            }
            """;

        var findings = Detector.Detect(CompilationHelper.CreateWithReferences(code)).ToList();

        Assert.Empty(findings);
    }

    // ── Trivial class (TCC = 1.0 by convention) ────────────────────────────────

    [Fact]
    public void Detect_FewerThanTwoPublicMethods_NotFlagged()
    {
        var code = $$"""
            {{ForeignDecl}}
            class Tiny {
                private int _x;
                public void Only(Foreign f) { if (f.A > 0) { _x = f.A; } }
            }
            """;

        var findings = Detector.Detect(CompilationHelper.CreateWithReferences(code)).ToList();

        Assert.Empty(findings);
    }

    // ── Metrics exposed ─────────────────────────────────────────────────────────

    [Fact]
    public void Detect_Finding_ExposesAtfdWmcTccMetrics()
    {
        var code = $$"""
            {{ForeignDecl}}
            class God {
                private int _x;
                private int _y;
                public void M1(Foreign f) { if (f.A > 0) { _x = f.A; } }
                public void M2(Foreign f) { if (f.B > 0) { _x = f.B; } }
                public void M3(Foreign f) { if (f.C > 0) { _y = f.C; } }
            }
            """;

        var finding = Detector.Detect(CompilationHelper.CreateWithReferences(code))
            .Single(f => f.SymbolName.Contains("God"));

        Assert.True(finding.Metrics.ContainsKey("ATFD"));
        Assert.True(finding.Metrics.ContainsKey("WMC"));
        Assert.True(finding.Metrics.ContainsKey("TCC"));
    }

    // ── Namespaced symbol name ──────────────────────────────────────────────────

    [Fact]
    public void Detect_NamespacedClass_IncludesNamespaceInSymbolName()
    {
        var code = $$"""
            {{ForeignDecl}}
            namespace My.App {
                class God {
                    private int _x;
                    private int _y;
                    public void M1(Foreign f) { if (f.A > 0) { _x = f.A; } }
                    public void M2(Foreign f) { if (f.B > 0) { _x = f.B; } }
                    public void M3(Foreign f) { if (f.C > 0) { _y = f.C; } }
                }
            }
            """;

        var finding = Detector.Detect(CompilationHelper.CreateWithReferences(code))
            .Single(f => f.SymbolName.Contains("God"));

        Assert.Contains("My.App", finding.SymbolName);
        Assert.Contains("God", finding.SymbolName);
    }
}
