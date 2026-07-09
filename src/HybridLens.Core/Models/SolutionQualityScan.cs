namespace HybridLens.Core.Models;

/// <summary>
/// A whole-solution code-quality measurement at one point in time — the instrument behind the
/// quality-impact question ("do the applied changes improve or degrade the codebase, not just
/// resolve the one flagged metric?"). Two independent instruments are captured side by side:
///
///  • <b>Layer 1</b> — the study's own Roslyn detector run over the WHOLE solution, giving per-category
///    smell counts (God Class / Long Method / Obsolete API). This is self-scored, so it is vulnerable
///    to Goodhart's law (the detector both defines and scores the smell); it answers "did the repair
///    create or resolve smells of the same taxonomy elsewhere in the solution?".
///
///  • <b>Layer 2</b> — Microsoft.CodeAnalysis.NetAnalyzers diagnostics, an INDEPENDENT instrument not
///    written by us and not targeted by the repair, so it breaks the self-scoring circularity. Captured
///    at two tiers from a single <c>8.0-all</c> build: the <i>headline</i> tier restricts to rules that
///    are enabled-by-default (empirically identical to an <c>8.0-recommended</c> build — validated on the
///    corpus), and the <i>all</i> tier keeps every rule incl. opt-in ones (a sensitivity check). Compiler
///    obsolete-usage warnings (CS0618/CS0619) are counted separately as an independent corroboration of
///    the Obsolete-API detector.
/// </summary>
public sealed record SolutionQualityScan
{
    // ── Layer 1: custom detector, whole solution ─────────────────────────────
    /// <summary>Per anti-pattern type ("GodClass"/"LongMethod"/"ObsoleteApiUsage") whole-solution finding count.</summary>
    public required IReadOnlyDictionary<string, int> SmellCountsByType { get; init; }
    /// <summary>Total whole-solution findings across all types.</summary>
    public required int SmellTotal { get; init; }
    /// <summary>Per-finding identity ("Type|file|symbol", forward slashes) for the whole-solution set-diff that surfaces collateral (a new/removed smell in a different file or category).</summary>
    public required IReadOnlyList<string> SmellKeys { get; init; }

    // ── Layer 2: CA analyzers (headline = enabled-by-default) ────────────────
    /// <summary>Headline-tier (enabled-by-default CA rules) count per rule ID.</summary>
    public required IReadOnlyDictionary<string, int> CaHeadlineByRule { get; init; }
    /// <summary>Headline-tier count per CA category (Design/Performance/Naming/…).</summary>
    public required IReadOnlyDictionary<string, int> CaHeadlineByCategory { get; init; }
    /// <summary>Total headline-tier CA diagnostics.</summary>
    public required int CaHeadlineTotal { get; init; }

    // ── Layer 2: CA analyzers (all = incl. opt-in, sensitivity tier) ─────────
    /// <summary>All-tier (every fired CA rule, incl. opt-in) count per rule ID.</summary>
    public required IReadOnlyDictionary<string, int> CaAllByRule { get; init; }
    /// <summary>All-tier count per CA category.</summary>
    public required IReadOnlyDictionary<string, int> CaAllByCategory { get; init; }
    /// <summary>Total all-tier CA diagnostics.</summary>
    public required int CaAllTotal { get; init; }

    /// <summary>Compiler obsolete-usage diagnostics (CS0618/CS0619) — independent corroboration of the Obsolete-API detector.</summary>
    public required int CompilerObsoleteCount { get; init; }

    /// <summary>Every captured CA/IDE diagnostic, for the best-effort set-diff (introduced/removed) between states.</summary>
    public required IReadOnlyList<CaDiagnostic> Diagnostics { get; init; }

    /// <summary>False when the CA build produced no SARIF (e.g. build failed) so Layer 2 is unavailable for this state.</summary>
    public          bool    CaAvailable { get; init; }
    /// <summary>Non-fatal note (e.g. workspace load warnings, missing SARIF) for honest reporting.</summary>
    public          string? Note        { get; init; }
}

/// <summary>
/// One Microsoft.CodeAnalysis diagnostic captured from a SARIF result, normalised for cross-state diffing.
/// </summary>
public sealed record CaDiagnostic
{
    public required string  RuleId           { get; init; }
    public required string  Category         { get; init; }
    /// <summary>Effective SARIF result level (warning/error/note); descriptive only — the headline tier is gated on <see cref="EnabledByDefault"/>, not level.</summary>
    public required string  Level            { get; init; }
    /// <summary>True when the rule is enabled-by-default (the low-noise headline tier); false for opt-in ("all"-only) rules.</summary>
    public required bool    EnabledByDefault { get; init; }
    /// <summary>Solution-relative source path (forward slashes), or empty when the result had no physical location.</summary>
    public required string  File             { get; init; }
    public          int     Line             { get; init; }
    /// <summary>Enclosing member (SARIF logicalLocation.fullyQualifiedName) when available — best effort.</summary>
    public          string? Member           { get; init; }

    /// <summary>
    /// Stable identity for set-diff across states: <c>ruleId|file|member</c>. Line is deliberately excluded
    /// because it shifts when a repair adds/removes lines, which would otherwise register every diagnostic
    /// in the file as churn. Coarse by design; the primary signal is the per-rule/per-category net delta.
    /// </summary>
    public string Key => $"{RuleId}|{File}|{Member ?? "?"}";
}
