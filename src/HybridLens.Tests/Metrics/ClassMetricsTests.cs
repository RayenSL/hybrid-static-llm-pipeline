using HybridLens.StaticAnalysis.Metrics;
using HybridLens.Tests.Helpers;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace HybridLens.Tests.Metrics;

/// <summary>
/// Pins the exact ATFD / WMC / TCC values that the Lanza &amp; Marinescu God Class
/// strategy depends on. These are the research-validity-critical assertions: if a
/// reviewer challenges the metric definitions, these tests document the behaviour.
/// </summary>
public sealed class ClassMetricsTests
{
    private static ClassMetricsResult MetricsFor(string code, string className)
    {
        var compilation = CompilationHelper.CreateWithReferences(code);
        var tree  = compilation.SyntaxTrees.First();
        var model = compilation.GetSemanticModel(tree);
        var cls   = tree.GetRoot()
            .DescendantNodes()
            .OfType<ClassDeclarationSyntax>()
            .First(c => c.Identifier.Text == className);
        return ClassMetrics.Compute(cls, model);
    }

    // ── A class with known structure ────────────────────────────────────────────
    //
    //   class Foreign { public int Data; public int Other; }
    //   class Sample {
    //       private int _a;
    //       private int _b;
    //       public void M1(Foreign f) { _a = 1; if (_a > 0) { var x = f.Data; } }
    //       public void M2() { _a = 2; }
    //       public void M3() { _b = 3; }
    //   }
    //
    //   ATFD = 1   (one distinct foreign attribute: Foreign.Data)
    //   WMC  = 4   (M1 has CC 2 because of the if; M2 + M3 are 1 each)
    //   TCC  = 1/3 (M1 & M2 share _a; M3 is isolated → 1 of 3 pairs connected)

    private const string Sample = """
        class Foreign { public int Data; public int Other; }
        class Sample {
            private int _a;
            private int _b;
            public void M1(Foreign f) { _a = 1; if (_a > 0) { var x = f.Data; } }
            public void M2() { _a = 2; }
            public void M3() { _b = 3; }
        }
        """;

    [Fact]
    public void Atfd_CountsDistinctForeignProjectAttributes()
    {
        Assert.Equal(1, MetricsFor(Sample, "Sample").Atfd);
    }

    [Fact]
    public void Wmc_SumsMethodCyclomaticComplexities()
    {
        Assert.Equal(4, MetricsFor(Sample, "Sample").Wmc);
    }

    [Fact]
    public void Tcc_IsFractionOfConnectedPublicMethodPairs()
    {
        Assert.Equal(1.0 / 3.0, MetricsFor(Sample, "Sample").Tcc, precision: 3);
    }

    [Fact]
    public void PublicMethodCount_CountsOnlyPublicMethods()
    {
        Assert.Equal(3, MetricsFor(Sample, "Sample").PublicMethodCount);
    }

    // ── Framework/system attributes are NOT counted in ATFD ─────────────────────

    [Fact]
    public void Atfd_ExcludesFrameworkTypeAttributes()
    {
        const string code = """
            class UsesString {
                public int Len(string s) { return s.Length; }
            }
            """;
        // string.Length is a framework property (metadata, not source) → ATFD = 0.
        Assert.Equal(0, MetricsFor(code, "UsesString").Atfd);
    }

    // ── Own and inherited attributes are NOT foreign ────────────────────────────

    [Fact]
    public void Atfd_ExcludesOwnAndInheritedAttributes()
    {
        const string code = """
            class Base { protected int Inherited; }
            class Derived : Base {
                private int _own;
                public void Use() { _own = 1; Inherited = 2; }
            }
            """;
        // Both _own (own) and Inherited (from base) are excluded → ATFD = 0.
        Assert.Equal(0, MetricsFor(code, "Derived").Atfd);
    }

    // ── Fewer than two public methods → TCC defined as 1.0 ──────────────────────

    [Fact]
    public void Tcc_IsOneWhenFewerThanTwoPublicMethods()
    {
        const string code = """
            class Tiny {
                private int _x;
                public void Only() { _x = 1; }
            }
            """;
        Assert.Equal(1.0, MetricsFor(code, "Tiny").Tcc, precision: 3);
    }
}
