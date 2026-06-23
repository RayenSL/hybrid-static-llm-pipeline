using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

/// <summary>
/// One repair to verify: a generation row (hybrid or llm-only) that produced a remediation,
/// reconstructed from a runs JSONL. Carries the generation identity (so the verification row can
/// be grouped by architecture × context × model) plus the candidate repair text to apply.
/// </summary>
public sealed record RepairCandidate
{
    /// <summary>RunId of the generation row this repair came from.</summary>
    public required string SourceRunId { get; init; }

    public required AntiPatternType Type        { get; init; }
    /// <summary>Absolute path of the source file as recorded by the generating run (an original corpus file).</summary>
    public required string          FilePath    { get; init; }
    public required string          SymbolName  { get; init; }
    public required int             Line        { get; init; }
    public required Severity        Severity    { get; init; }
    public          string?         Snippet     { get; init; }
    /// <summary>Original triggering metrics, carried through for reference. May be null (e.g. llm-only rows).</summary>
    public          IReadOnlyDictionary<string, double>? Metrics { get; init; }

    public required ContextLevel    ContextLevel  { get; init; }
    public required string          ModelName     { get; init; }
    public required string          PromptVersion { get; init; }
    public required string          Architecture  { get; init; }
    public required int             RunNumber     { get; init; }

    /// <summary>The remediation text under test (parsed_suggested_fix).</summary>
    public required string          RepairText    { get; init; }
}
