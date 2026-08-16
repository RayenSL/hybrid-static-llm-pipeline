using HybridLens.Core.Models;

namespace HybridLens.CLI.Commands;

/// <summary>
/// The frozen direct-edit context ladder manifest, shared by the command that writes it and the
/// command that executes it. One declaration rather than two: a writer and a reader that each own
/// their own copy of a schema drift apart silently, which is the failure mode this experiment
/// exists to correct.
/// </summary>
internal sealed record ContextLadderManifest
{
    public required string SchemaVersion { get; init; }
    public required string CampaignId { get; init; }
    public required string ModelName { get; init; }
    public required string TargetSolution { get; init; }
    public required string BaselineSource { get; init; }
    public required string BaselineSha256 { get; init; }
    public required string CodeRevision { get; init; }
    public required string PromptVersion { get; init; }

    /// <summary>Which <see cref="ContextLadder"/> defines the levels for this campaign.</summary>
    public required string LadderVersion { get; init; }

    /// <summary>
    /// <see cref="ContextLadder.Sha256"/> at freeze time. The campaign refuses to start when the
    /// compiled ladder no longer hashes to this, so a definition edited after freezing cannot
    /// produce assignments attributed to the old definition.
    /// </summary>
    public required string LadderSha256 { get; init; }

    public required int Repetitions { get; init; }
    public required int RandomizationSeed { get; init; }
    public required int BuildTimeoutSeconds { get; init; }
    public required List<LadderAssignment> Assignments { get; init; }
}

internal sealed record LadderAssignment
{
    public required int Order { get; init; }
    public required string AssignmentId { get; init; }

    /// <summary>One block per target per repetition; the four levels are matched within it.</summary>
    public required string BlockId { get; init; }

    public required int RunNumber { get; init; }
    public required ContextLevel ContextLevel { get; init; }
    public required AntiPatternType AntiPatternType { get; init; }
    public required Severity Severity { get; init; }
    public required string FilePath { get; init; }
    public required string SymbolName { get; init; }
    public required int Line { get; init; }
    public required int TargetEndLine { get; init; }
    public string? Snippet { get; init; }
    public required Dictionary<string, double> Metrics { get; init; }
    public required List<string> ExpectedQualityAttributes { get; init; }
    public required string PristineSourceSha256 { get; init; }
    public required Dictionary<string, string> ProjectMetadata { get; init; }

    /// <summary>
    /// Declaring sources resolved once at freeze time. Empty at every level whose specification
    /// does not ask for cross-file scope, which the campaign validates rather than assumes.
    /// </summary>
    public List<CrossFileDeclaration> CrossFileDeclarations { get; init; } = [];

    /// <summary>Relative paths resolved but dropped by the cap. Truncation is a reported outcome.</summary>
    public List<string> CrossFileDropped { get; init; } = [];

    public bool CrossFileTruncated => CrossFileDropped.Count > 0;
}
