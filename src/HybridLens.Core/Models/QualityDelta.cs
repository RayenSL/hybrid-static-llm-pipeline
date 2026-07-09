namespace HybridLens.Core.Models;

/// <summary>
/// The before→after change in whole-solution quality for one applied repair — the answer to
/// "did this change improve or degrade the codebase, not just resolve the one flagged metric?".
/// Positive numbers mean the repair ADDED that kind of problem (worse); negative means it removed
/// problems (better). Computed by <c>SolutionQualityScanner.Diff</c> from a shared frozen baseline
/// scan (before, pristine corpus) and the post-repair scan (after, the applied working copy).
/// </summary>
public sealed record QualityDelta
{
    // ── Layer 1: custom detector (whole-solution smell counts) ───────────────
    /// <summary>Per anti-pattern type: after − before whole-solution finding count. Negative = smells removed.</summary>
    public required IReadOnlyDictionary<string, int> SmellDeltaByType { get; init; }
    /// <summary>Net whole-solution smell change across all types (after − before).</summary>
    public required int SmellTotalDelta { get; init; }
    /// <summary>True when the repair changed a smell count in a category OTHER than the one it targeted, or in a file other than the repaired one — the collateral signal.</summary>
    public required bool SmellCollateral { get; init; }

    // ── Layer 2: CA analyzers (independent instrument) ───────────────────────
    /// <summary>Headline-tier (enabled-by-default) net CA change per category (after − before).</summary>
    public required IReadOnlyDictionary<string, int> CaHeadlineDeltaByCategory { get; init; }
    /// <summary>Net headline-tier CA change (after − before). Negative = warnings removed.</summary>
    public required int CaHeadlineTotalDelta { get; init; }
    /// <summary>All-tier (incl. opt-in) net CA change per category — the sensitivity check.</summary>
    public required IReadOnlyDictionary<string, int> CaAllDeltaByCategory { get; init; }
    /// <summary>Net all-tier CA change (after − before).</summary>
    public required int CaAllTotalDelta { get; init; }
    /// <summary>Net compiler obsolete-usage (CS0618/CS0619) change (after − before).</summary>
    public required int CompilerObsoleteDelta { get; init; }

    // ── Best-effort set diff (coarse: ruleId|file|member) ────────────────────
    /// <summary>CA diagnostics present after but not before (introduced), as "ruleId|file|member" keys. Coarse — line excluded.</summary>
    public required IReadOnlyList<string> CaIntroduced { get; init; }
    /// <summary>CA diagnostics present before but not after (removed), as "ruleId|file|member" keys.</summary>
    public required IReadOnlyList<string> CaRemoved { get; init; }

    /// <summary>False when either scan lacked Layer 2 data (build failed / no SARIF), so CA deltas are not meaningful.</summary>
    public required bool CaAvailable { get; init; }

    /// <summary>
    /// Computes the before→after quality change for one repair. <paramref name="targetedType"/> and
    /// <paramref name="repairedRelFile"/> (solution-relative, forward slashes) identify the instance the
    /// repair was meant to fix; any smell change in a DIFFERENT file or category is flagged as collateral
    /// (resolving the targeted instance is expected, not collateral).
    /// </summary>
    public static QualityDelta Between(
        SolutionQualityScan before, SolutionQualityScan after,
        AntiPatternType targetedType, string repairedRelFile)
    {
        var repaired = Normalise(repairedRelFile);

        // Layer 1: per-type net delta + collateral.
        var smellTypes = before.SmellCountsByType.Keys.Union(after.SmellCountsByType.Keys, StringComparer.Ordinal);
        var smellDelta = smellTypes.ToDictionary(
            t => t,
            t => after.SmellCountsByType.GetValueOrDefault(t) - before.SmellCountsByType.GetValueOrDefault(t),
            StringComparer.Ordinal);

        var beforeSmells = new HashSet<string>(before.SmellKeys, StringComparer.Ordinal);
        var afterSmells  = new HashSet<string>(after.SmellKeys,  StringComparer.Ordinal);
        var changedSmells = beforeSmells.Except(afterSmells).Concat(afterSmells.Except(beforeSmells));
        var collateral = changedSmells.Any(k =>
        {
            var parts = k.Split('|');
            var type = parts.Length > 0 ? parts[0] : "";
            var file = parts.Length > 1 ? Normalise(parts[1]) : "";
            return !type.Equals(targetedType.ToString(), StringComparison.Ordinal) ||
                   !file.Equals(repaired, StringComparison.OrdinalIgnoreCase);
        });

        // Layer 2: per-category net deltas (headline + all) + set diff.
        var caAvailable = before.CaAvailable && after.CaAvailable;
        var beforeKeys = new HashSet<string>(before.Diagnostics.Select(d => d.Key), StringComparer.Ordinal);
        var afterKeys  = new HashSet<string>(after.Diagnostics.Select(d => d.Key),  StringComparer.Ordinal);

        return new QualityDelta
        {
            SmellDeltaByType          = smellDelta,
            SmellTotalDelta           = after.SmellTotal - before.SmellTotal,
            SmellCollateral           = collateral,

            CaHeadlineDeltaByCategory = DiffCounts(before.CaHeadlineByCategory, after.CaHeadlineByCategory),
            CaHeadlineTotalDelta      = after.CaHeadlineTotal - before.CaHeadlineTotal,
            CaAllDeltaByCategory      = DiffCounts(before.CaAllByCategory, after.CaAllByCategory),
            CaAllTotalDelta           = after.CaAllTotal - before.CaAllTotal,
            CompilerObsoleteDelta     = after.CompilerObsoleteCount - before.CompilerObsoleteCount,

            CaIntroduced = caAvailable ? afterKeys.Except(beforeKeys).OrderBy(k => k, StringComparer.Ordinal).ToList() : [],
            CaRemoved    = caAvailable ? beforeKeys.Except(afterKeys).OrderBy(k => k, StringComparer.Ordinal).ToList() : [],
            CaAvailable  = caAvailable
        };
    }

    private static IReadOnlyDictionary<string, int> DiffCounts(
        IReadOnlyDictionary<string, int> before, IReadOnlyDictionary<string, int> after)
        => before.Keys.Union(after.Keys, StringComparer.Ordinal)
            .Select(k => (k, d: after.GetValueOrDefault(k) - before.GetValueOrDefault(k)))
            .Where(x => x.d != 0)
            .ToDictionary(x => x.k, x => x.d, StringComparer.Ordinal);

    private static string Normalise(string p) => p.Replace('\\', '/').TrimStart('/');
}
