using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
using HybridLens.StaticAnalysis.Detectors;
using HybridLens.Tests.Helpers;

namespace HybridLens.Tests.Detectors;

/// <summary>
/// ObsoleteApiDetector requires a semantic model so all compilations here
/// include reference assemblies (Net80) to resolve System.ObsoleteAttribute.
/// </summary>
public sealed class ObsoleteApiDetectorTests
{
    private static ObsoleteApiDetector DefaultDetector =>
        new(new ObsoleteApiConfig());

    // ── Clean ─────────────────────────────────────────────────────────────────

    [Fact]
    public void Detect_NoObsoleteUsage_ReturnsNoFindings()
    {
        const string code = """
            class Api  { public void Current() { } }
            class User { void Caller() { new Api().Current(); } }
            """;

        var findings = DefaultDetector
            .Detect(CompilationHelper.CreateWithReferences(code))
            .ToList();

        Assert.Empty(findings);
    }

    // ── [Obsolete] without isError → Warning ──────────────────────────────────

    [Fact]
    public void Detect_ObsoleteMethodCall_ReturnsWarning()
    {
        const string code = """
            using System;

            class Api {
                [Obsolete("Use NewMethod instead")]
                public void OldMethod() { }
            }

            class User {
                void Caller() { new Api().OldMethod(); }
            }
            """;

        var findings = DefaultDetector
            .Detect(CompilationHelper.CreateWithReferences(code))
            .ToList();

        // The detector may report on the member access and/or the invocation node;
        // there should be at least one warning.
        Assert.NotEmpty(findings);
        Assert.All(findings, f => Assert.Equal(AntiPatternType.ObsoleteApiUsage, f.Type));
        Assert.Contains(findings, f => f.Severity == Severity.Warning);
        Assert.DoesNotContain(findings, f => f.Severity == Severity.Critical);
    }

    // ── [Obsolete(msg, true)] → Critical ──────────────────────────────────────

    [Fact]
    public void Detect_ObsoleteErrorMethodCall_ReturnsCritical()
    {
        const string code = """
            using System;

            class Api {
                [Obsolete("Removed — do not use", true)]
                public void RemovedMethod() { }
            }

            class User {
                void Caller() { new Api().RemovedMethod(); }
            }
            """;

        var findings = DefaultDetector
            .Detect(CompilationHelper.CreateWithReferences(code))
            .ToList();

        Assert.NotEmpty(findings);
        Assert.Contains(findings, f => f.Severity == Severity.Critical);
    }

    // ── Deprecated namespace prefix ───────────────────────────────────────────

    [Fact]
    public void Detect_DeprecatedNamespacePrefix_ReturnsWarning()
    {
        const string code = """
            using Legacy.Internal;

            namespace Legacy.Internal {
                public class OldHelper { public void Do() { } }
            }

            class User {
                void Caller() { new OldHelper().Do(); }
            }
            """;

        var config = new ObsoleteApiConfig
        {
            DeprecatedNamespacePrefixes = ["Legacy.Internal"]
        };

        var findings = new ObsoleteApiDetector(config)
            .Detect(CompilationHelper.CreateWithReferences(code))
            .ToList();

        Assert.NotEmpty(findings);
        Assert.All(findings, f => Assert.Equal(AntiPatternType.ObsoleteApiUsage, f.Type));
    }

    // ── No false-positive on own namespace ────────────────────────────────────

    [Fact]
    public void Detect_PrefixNotConfigured_NoDeprecatedNamespaceFindings()
    {
        const string code = """
            namespace Legacy.Internal {
                public class Helper { public void Do() { } }
            }

            class User {
                void Caller() { new Legacy.Internal.Helper().Do(); }
            }
            """;

        // No prefixes configured → should not flag the namespace
        var findings = DefaultDetector
            .Detect(CompilationHelper.CreateWithReferences(code))
            .ToList();

        Assert.Empty(findings);
    }
}
