using System.Security.Cryptography;
using System.Text;

namespace HybridLens.Core.Models;

/// <summary>
/// How much file-external context a level supplies. <see cref="None"/> keeps a level inside the
/// target's own file, which is what every level of the sealed four-level supplement did.
/// </summary>
public enum CrossFileScope
{
    /// <summary>Nothing outside the target's own file.</summary>
    None,

    /// <summary>
    /// The declaring source of every external type the target references. For an Obsolete API
    /// target this is the file that declares both the deprecated member and its replacement, which
    /// is the information the supplement's applier repeatedly reported as missing.
    /// </summary>
    ReferencedTypeDeclarations
}

/// <summary>
/// One frozen source of one context level's meaning (§4.4.3). Every consumer derives from this:
/// the resolver takes its cap and ordering rule from here, the builder renders from here, and the
/// campaign manifest carries the whole ladder plus <see cref="ContextLadder.Sha256"/> so prose and
/// code cannot drift apart.
///
/// The sealed supplement is why this exists. <c>ContextBuilder.BuildFull</c> promised "other
/// findings in the same file" while the caller passed a single-element list, so the clause was dead
/// and Full silently collapsed onto Relational — a divergence between the written definition and
/// the executed one that nothing in the pipeline could detect.
/// </summary>
public sealed record ContextLevelSpec
{
    public required ContextLevel Level { get; init; }

    /// <summary>Triggering metrics and their thresholds.</summary>
    public bool IncludeMetrics { get; init; }

    /// <summary>The enclosing type's member signatures.</summary>
    public bool IncludeMemberSummary { get; init; }

    /// <summary>A window of source either side of the finding.</summary>
    public bool IncludeSurroundingWindow { get; init; }

    /// <summary>Frozen project, framework and domain metadata.</summary>
    public bool IncludeProjectMetadata { get; init; }

    /// <summary>Other detector findings located in the same file.</summary>
    public bool IncludeCoLocatedFindings { get; init; }

    /// <summary>
    /// Lines either side of the finding for <see cref="IncludeSurroundingWindow"/>. Null defers to
    /// <c>ContextConfig.SnippetContextLines</c>, which is what the sealed ladder does.
    /// </summary>
    public int? SnippetContextLines { get; init; }

    public CrossFileScope CrossFile { get; init; }

    /// <summary>Maximum declaring files supplied. Ignored when <see cref="CrossFile"/> is None.</summary>
    public int MaxCrossFileFiles { get; init; }

    /// <summary>Maximum total characters across supplied files. Ignored when CrossFile is None.</summary>
    public int MaxCrossFileChars { get; init; }

    /// <summary>How resolved files are ordered before the cap is applied. Recorded so a truncation is reproducible.</summary>
    public string OrderingRule { get; init; } = "none";

    /// <summary>The canonical form that <see cref="ContextLadder.Sha256"/> hashes.</summary>
    internal string Canonical() =>
        $"{Level}|metrics={IncludeMetrics}|members={IncludeMemberSummary}|window={IncludeSurroundingWindow}"
        + $"|metadata={IncludeProjectMetadata}|colocated={IncludeCoLocatedFindings}"
        + $"|lines={(SnippetContextLines?.ToString() ?? "config")}"
        + $"|crossfile={CrossFile}|maxFiles={MaxCrossFileFiles}|maxChars={MaxCrossFileChars}|order={OrderingRule}";
}

/// <summary>
/// The versioned four-level ladders. A ladder is never edited in place: a changed definition is a
/// new version, so a completed campaign's manifest always names the ladder that produced it.
/// </summary>
public static class ContextLadder
{
    /// <summary>
    /// The ladder of the sealed supplement (<c>experiments/grounding-gpt56-sol-20260728</c>).
    /// Full differs from Relational only by project metadata and co-located findings, and because
    /// every corpus target occupies a unique file the second of those is empty by construction.
    /// Retained verbatim so that experiment stays reproducible.
    /// </summary>
    public const string V1Version = "ladder-v1.0.0";

    /// <summary>
    /// The direct-editing ladder. Full is redefined as the cross-file declarations the repair
    /// actually needs, replacing the metadata-only rung that could not move the sealed outcome.
    /// </summary>
    public const string V2Version = "ladder-v2.0.0";

    public static IReadOnlyList<ContextLevelSpec> V1 { get; } =
    [
        new ContextLevelSpec { Level = ContextLevel.Minimal },
        new ContextLevelSpec { Level = ContextLevel.Structural, IncludeMetrics = true },
        new ContextLevelSpec
        {
            Level = ContextLevel.Relational,
            IncludeMetrics = true,
            IncludeMemberSummary = true,
            IncludeSurroundingWindow = true
        },
        new ContextLevelSpec
        {
            Level = ContextLevel.Full,
            IncludeMetrics = true,
            IncludeMemberSummary = true,
            IncludeSurroundingWindow = true,
            IncludeProjectMetadata = true,
            IncludeCoLocatedFindings = true
        }
    ];

    public static IReadOnlyList<ContextLevelSpec> V2 { get; } =
    [
        new ContextLevelSpec { Level = ContextLevel.Minimal },
        new ContextLevelSpec { Level = ContextLevel.Structural, IncludeMetrics = true },
        new ContextLevelSpec
        {
            Level = ContextLevel.Relational,
            IncludeMetrics = true,
            IncludeMemberSummary = true,
            IncludeSurroundingWindow = true
        },
        new ContextLevelSpec
        {
            Level = ContextLevel.Full,
            IncludeMetrics = true,
            IncludeMemberSummary = true,
            IncludeSurroundingWindow = true,
            IncludeProjectMetadata = false,
            IncludeCoLocatedFindings = true,
            CrossFile = CrossFileScope.ReferencedTypeDeclarations,
            MaxCrossFileFiles = 8,
            MaxCrossFileChars = 60_000,
            OrderingRule = "ordinal by repository-relative path, then by declaring type name"
        }
    ];

    public static IReadOnlyList<ContextLevelSpec> ForVersion(string version) => version switch
    {
        V1Version => V1,
        V2Version => V2,
        _ => throw new ArgumentOutOfRangeException(nameof(version), version, "unknown context ladder version")
    };

    public static string VersionOf(IReadOnlyList<ContextLevelSpec> ladder) =>
        ReferenceEquals(ladder, V2) ? V2Version : V1Version;

    /// <summary>
    /// The level's specification. <see cref="ContextLevel.AnalyserOnly"/> makes no model call and
    /// therefore has no level specification.
    /// </summary>
    public static ContextLevelSpec For(IReadOnlyList<ContextLevelSpec> ladder, ContextLevel level) =>
        ladder.FirstOrDefault(s => s.Level == level)
        ?? throw new ArgumentOutOfRangeException(nameof(level), level, "level is not part of this ladder");

    /// <summary>
    /// Stable hash over the whole ladder. The campaign refuses to start when this differs from the
    /// value frozen in its manifest, so a definition edited after freezing cannot silently produce
    /// assignments attributed to the old definition.
    /// </summary>
    public static string Sha256(IReadOnlyList<ContextLevelSpec> ladder)
    {
        var canonical = string.Join("\n", ladder.Select(s => s.Canonical()));
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(canonical))).ToLowerInvariant();
    }
}
