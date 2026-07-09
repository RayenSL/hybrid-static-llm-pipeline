using HybridLens.Core.Models;

namespace HybridLens.Tests.Quality;

/// <summary>
/// <see cref="QualityDelta.Between"/> is the arithmetic behind the codebase-quality-impact measurement:
/// it turns two whole-solution scans (before = frozen baseline, after = applied repair) into signed
/// deltas and a collateral flag. These tests pin the sign convention (positive = worse), the collateral
/// rule (a change in a DIFFERENT file/category than the targeted instance is collateral; resolving the
/// target itself is not), and the Layer-2 per-category delta + introduced/removed set diff.
/// </summary>
public sealed class QualityDeltaTests
{
    // ── Layer 1: smell delta + collateral ────────────────────────────────────

    [Fact]
    public void ResolvingTargetedInstance_IsNotCollateral()
    {
        var before = Scan(smells: new() { ["GodClass"] = 1 },
                          smellKeys: ["GodClass|Ordering/Foo.cs|Ordering.Foo"]);
        var after  = Scan(smells: new(), smellKeys: []);

        var d = QualityDelta.Between(before, after, AntiPatternType.GodClass, "Ordering/Foo.cs");

        Assert.False(d.SmellCollateral);           // removing the very smell we targeted is expected
        Assert.Equal(-1, d.SmellTotalDelta);       // one fewer smell overall (improvement)
        Assert.Equal(-1, d.SmellDeltaByType["GodClass"]);
    }

    [Fact]
    public void NewSmellInDifferentFile_IsCollateral_EvenWhenTotalUnchanged()
    {
        // Target God Class resolved in Foo.cs, but the repair spawned a new God Class in Bar.cs.
        var before = Scan(smells: new() { ["GodClass"] = 1 },
                          smellKeys: ["GodClass|Ordering/Foo.cs|Ordering.Foo"]);
        var after  = Scan(smells: new() { ["GodClass"] = 1 },
                          smellKeys: ["GodClass|Ordering/Bar.cs|Ordering.Bar"]);

        var d = QualityDelta.Between(before, after, AntiPatternType.GodClass, "Ordering/Foo.cs");

        Assert.True(d.SmellCollateral);            // a new smell in a different file is collateral
        Assert.Equal(0, d.SmellTotalDelta);        // net count unchanged, yet the codebase moved
    }

    [Fact]
    public void NewSmellOfDifferentCategoryInSameFile_IsCollateral()
    {
        // Extract-method repair on the targeted Long Method leaves a God Class behind in the SAME file.
        var before = Scan(smells: new() { ["LongMethod"] = 1 },
                          smellKeys: ["LongMethod|Ordering/Foo.cs|Foo.DoAll"]);
        var after  = Scan(smells: new() { ["GodClass"] = 1 },
                          smellKeys: ["GodClass|Ordering/Foo.cs|Ordering.Foo"]);

        var d = QualityDelta.Between(before, after, AntiPatternType.LongMethod, "Ordering/Foo.cs");

        Assert.True(d.SmellCollateral);            // different category ⇒ collateral
        Assert.Equal(-1, d.SmellDeltaByType["LongMethod"]);
        Assert.Equal(+1, d.SmellDeltaByType["GodClass"]);
    }

    [Fact]
    public void PathSeparatorNormalisation_TreatsBackslashRepairedFileAsSameFile()
    {
        var before = Scan(smells: new() { ["GodClass"] = 1 },
                          smellKeys: ["GodClass|Ordering/Foo.cs|Ordering.Foo"]);
        var after  = Scan(smells: new(), smellKeys: []);

        // Caller passes a Windows-style relative path; Between must normalise before comparing.
        var d = QualityDelta.Between(before, after, AntiPatternType.GodClass, @"Ordering\Foo.cs");

        Assert.False(d.SmellCollateral);
    }

    // ── Layer 2: CA delta + set diff ─────────────────────────────────────────

    [Fact]
    public void CaHeadlineDelta_IsPerCategory_WithIntroducedAndRemovedKeys()
    {
        var before = Scan(
            headlineCat: new() { ["Performance"] = 2 },
            allCat:      new() { ["Performance"] = 2 },
            diags:
            [
                Diag("CA1822", "Performance", "Ordering/Foo.cs", "Foo.A"),
                Diag("CA1822", "Performance", "Ordering/Foo.cs", "Foo.B"),
            ]);
        var after = Scan(
            headlineCat: new() { ["Performance"] = 1, ["Design"] = 1 },
            allCat:      new() { ["Performance"] = 1, ["Design"] = 1 },
            diags:
            [
                Diag("CA1822", "Performance", "Ordering/Foo.cs", "Foo.A"),
                Diag("CA1055", "Design",      "Ordering/Foo.cs", "Foo.Url"),
            ]);

        var d = QualityDelta.Between(before, after, AntiPatternType.LongMethod, "Ordering/Foo.cs");

        Assert.True(d.CaAvailable);
        Assert.Equal(0, d.CaHeadlineTotalDelta);                       // 2 → 2 overall
        Assert.Equal(-1, d.CaHeadlineDeltaByCategory["Performance"]);  // but Performance improved
        Assert.Equal(+1, d.CaHeadlineDeltaByCategory["Design"]);       // and Design regressed
        Assert.Contains("CA1055|Ordering/Foo.cs|Foo.Url", d.CaIntroduced);
        Assert.Contains("CA1822|Ordering/Foo.cs|Foo.B",   d.CaRemoved);
    }

    [Fact]
    public void CaUnavailable_OnEitherSide_SuppressesSetDiff()
    {
        var before = Scan(diags: [Diag("CA1822", "Performance", "Ordering/Foo.cs", "Foo.A")]);
        var after  = Scan(diags: [], caAvailable: false);   // e.g. the after build emitted no SARIF

        var d = QualityDelta.Between(before, after, AntiPatternType.LongMethod, "Ordering/Foo.cs");

        Assert.False(d.CaAvailable);
        Assert.Empty(d.CaIntroduced);
        Assert.Empty(d.CaRemoved);
    }

    [Fact]
    public void CompilerObsoleteDelta_IsSigned()
    {
        var before = Scan(obsolete: 5);
        var after  = Scan(obsolete: 3);

        var d = QualityDelta.Between(before, after, AntiPatternType.ObsoleteApiUsage, "Ordering/Foo.cs");

        Assert.Equal(-2, d.CompilerObsoleteDelta);   // two obsolete call sites removed
    }

    // ── Helpers ──────────────────────────────────────────────────────────────

    private static CaDiagnostic Diag(string rule, string category, string file, string? member) => new()
    {
        RuleId = rule, Category = category, Level = "warning",
        EnabledByDefault = true, File = file, Line = 1, Member = member
    };

    private static SolutionQualityScan Scan(
        Dictionary<string, int>? smells = null,
        IEnumerable<string>? smellKeys = null,
        Dictionary<string, int>? headlineCat = null,
        Dictionary<string, int>? allCat = null,
        IEnumerable<CaDiagnostic>? diags = null,
        int obsolete = 0,
        bool caAvailable = true)
    {
        smells ??= new();
        headlineCat ??= new();
        allCat ??= new();
        var dl = (diags ?? []).ToList();
        return new SolutionQualityScan
        {
            SmellCountsByType     = smells,
            SmellTotal            = smells.Values.Sum(),
            SmellKeys             = (smellKeys ?? []).ToList(),
            CaHeadlineByRule      = new Dictionary<string, int>(),
            CaHeadlineByCategory  = headlineCat,
            CaHeadlineTotal       = headlineCat.Values.Sum(),
            CaAllByRule           = new Dictionary<string, int>(),
            CaAllByCategory       = allCat,
            CaAllTotal            = allCat.Values.Sum(),
            CompilerObsoleteCount = obsolete,
            Diagnostics           = dl,
            CaAvailable           = caAvailable,
            Note                  = null
        };
    }
}
