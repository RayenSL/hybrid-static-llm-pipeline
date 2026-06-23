using HybridLens.Core.Models;
using HybridLens.StaticAnalysis;

namespace HybridLens.Tests.Repair;

/// <summary>
/// The re-measure matcher must recognise the same seeded instance across the symbol formats the
/// detectors emit: namespaced vs not (Long Method), and the "caller → Deprecated.Symbol" form
/// (Obsolete API). Examples are taken from the constructed corpus INDEX.
/// </summary>
public sealed class RepairInstanceMatcherTests
{
    [Fact]
    public void GodClass_SameType_Matches()
        => Assert.True(RepairInstanceMatcher.Matches(
            AntiPatternType.GodClass, "Ordering.ReturnsHandler", "Ordering.ReturnsHandler"));

    [Fact]
    public void GodClass_DifferentType_DoesNotMatch()
        => Assert.False(RepairInstanceMatcher.Matches(
            AntiPatternType.GodClass, "Ordering.CatalogService", "Ordering.ReturnsHandler"));

    [Fact]
    public void LongMethod_NamespacedInstanceVsBareFinding_Matches()
        // Detector emits "OrderImporter.ImportBatch"; truth record uses "Ordering.OrderImporter.ImportBatch".
        => Assert.True(RepairInstanceMatcher.Matches(
            AntiPatternType.LongMethod, "OrderImporter.ImportBatch", "Ordering.OrderImporter.ImportBatch"));

    [Fact]
    public void LongMethod_DifferentMethod_DoesNotMatch()
        => Assert.False(RepairInstanceMatcher.Matches(
            AntiPatternType.LongMethod, "OrderImporter.ValidateBatch", "Ordering.OrderImporter.ImportBatch"));

    [Fact]
    public void ObsoleteApi_SameDeprecatedCallee_Matches()
        => Assert.True(RepairInstanceMatcher.Matches(
            AntiPatternType.ObsoleteApiUsage,
            "LabelPrinter.Print → Ordering.Legacy.LabelApiV1.Render",
            "Ordering.LabelPrinter.Print → Ordering.Legacy.LabelApiV1.Render"));

    [Fact]
    public void ObsoleteApi_DifferentDeprecatedCallee_DoesNotMatch()
        => Assert.False(RepairInstanceMatcher.Matches(
            AntiPatternType.ObsoleteApiUsage,
            "PdfExporter.Export → Invoicing.Legacy.RenderApiV1.ToPdf",
            "Ordering.LabelPrinter.Print → Ordering.Legacy.LabelApiV1.Render"));
}
