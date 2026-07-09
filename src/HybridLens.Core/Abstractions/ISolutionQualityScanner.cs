using HybridLens.Core.Models;

namespace HybridLens.Core.Abstractions;

/// <summary>
/// Measures whole-solution code quality for one state of a working copy — the instrument behind the
/// codebase-quality-impact question ("do the applied changes improve or degrade the codebase, not just
/// resolve the one flagged metric?"). Implemented in the StaticAnalysis layer (Roslyn + SARIF parsing) so
/// the Pipeline layer that orchestrates the repair runners stays free of Roslyn/MSBuild dependencies —
/// mirroring <see cref="IRepairMeasurer"/>.
/// </summary>
public interface ISolutionQualityScanner
{
    /// <summary>
    /// Scans the current state of the solution. <paramref name="solutionPath"/> is the .sln/.csproj to load
    /// for Layer 1 (the study's own detectors, whole solution); <paramref name="sarifRoot"/> is the tree
    /// under which the build's per-project <c>*.sarif</c> logs live for Layer 2 (the CA analyzer instrument).
    /// Does not build — consumes SARIF a prior build emitted.
    /// </summary>
    Task<SolutionQualityScan> ScanAsync(string solutionPath, string sarifRoot, CancellationToken cancellationToken = default);

    /// <summary>
    /// Captures a scan of whatever state is currently materialised in <paramref name="workingRoot"/> using a
    /// DEDICATED analyzer build (injects analyzer props, runs <paramref name="build"/> only to emit SARIF, then
    /// removes the props), so the caller's own gate/loop <c>dotnet build</c> can stay analyzer-free and remain
    /// the authoritative verified-repair gate. The dedicated build's pass/fail is intentionally ignored.
    /// </summary>
    Task<SolutionQualityScan> BuildAndScanAsync(
        string solutionPath,
        string workingRoot,
        Func<string, int, CancellationToken, Task<(bool Ok, string Output)>> build,
        int buildTimeoutSeconds,
        CancellationToken cancellationToken = default);
}
