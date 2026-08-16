namespace HybridLens.Core.Models;

/// <summary>
/// One declaring source file supplied to a Full-context prompt, resolved once during preflight and
/// frozen into the campaign manifest rather than resolved at prompt time.
///
/// Resolution needs Roslyn; <see cref="HybridLens.ContextBuilder"/> deliberately has no compilation
/// and reads source with plain line scans. Freezing the payload also makes the prompt reproducible
/// from the manifest alone and lets the hash prove the supplied source predates every repair.
/// </summary>
public sealed record CrossFileDeclaration
{
    /// <summary>Path relative to the solution root, with forward slashes, as shown in the prompt.</summary>
    public required string RelativePath { get; init; }

    /// <summary>The declared types this file contributed, ordinal-ordered. Recorded for audit.</summary>
    public required IReadOnlyList<string> DeclaredTypes { get; init; }

    public required string Source { get; init; }

    public required string Sha256 { get; init; }
}

/// <summary>
/// The outcome of resolving cross-file context for one target, including what the cap discarded.
/// A truncation is a reported experimental outcome, not an implementation detail: on an industrial
/// solution the p90 dependency payload is an order of magnitude past any sane prompt budget.
/// </summary>
public sealed record CrossFileResolution
{
    public required IReadOnlyList<CrossFileDeclaration> Included { get; init; }

    /// <summary>Relative paths resolved but dropped by the cap, in the order they were dropped.</summary>
    public required IReadOnlyList<string> Dropped { get; init; }

    public bool Truncated => Dropped.Count > 0;

    /// <summary>Total characters across <see cref="Included"/>.</summary>
    public int IncludedChars => Included.Sum(d => d.Source.Length);

    public static CrossFileResolution Empty { get; } = new()
    {
        Included = [],
        Dropped = []
    };
}
