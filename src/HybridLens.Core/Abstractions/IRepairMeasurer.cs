using HybridLens.Core.Models;

namespace HybridLens.Core.Abstractions;

/// <summary>
/// Re-runs the static detector on an applied (repaired) source tree to decide whether the
/// triggering metric still fires for a specific seeded instance — the re-measurement step of
/// the objective repair verification (§4.5.1). Implemented in the StaticAnalysis layer so the
/// Pipeline layer that orchestrates verification stays free of Roslyn / MSBuild dependencies.
/// </summary>
public interface IRepairMeasurer
{
    /// <param name="type">The anti-pattern whose triggering metric is being re-checked.</param>
    /// <param name="workingFilePath">Absolute path to the applied (edited) file inside the working copy.</param>
    /// <param name="instanceSymbol">The seeded instance's symbol, as recorded by the detector that first flagged it.</param>
    Task<RemeasureResult> RemeasureAsync(
        AntiPatternType type,
        string workingFilePath,
        string instanceSymbol,
        CancellationToken cancellationToken = default);
}

/// <summary>
/// Outcome of a re-measurement. <see cref="StillTriggers"/> is <c>false</c> when the instance
/// no longer satisfies its detection rule on the applied source — i.e. the repair is
/// metric-resolved. <see cref="Metrics"/> carries the still-firing metric values when it does,
/// and is null when the instance resolved away.
/// </summary>
public sealed record RemeasureResult(bool StillTriggers, IReadOnlyDictionary<string, double>? Metrics);
