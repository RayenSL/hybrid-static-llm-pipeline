using HybridLens.Core.Models;

namespace HybridLens.ContextBuilder;

/// <summary>
/// Everything the direct-edit runner needs to issue one call under a prompt family other than the
/// frozen factorial one. Supplied as a whole so the runner's default path stays literally unchanged
/// when no profile is given.
/// </summary>
public sealed record DirectEditPromptProfile
{
    public required string Architecture { get; init; }
    public required ContextLevel ContextLevel { get; init; }
    public required string SystemPrompt { get; init; }
    public required string PromptVersion { get; init; }

    /// <summary>(relativePath, pristineSource, target, contextBlock, visibleTest) → user prompt.</summary>
    public required Func<string, string, BlindedTargetDescriptor, string?, LoadedVisibleTestPrompt?, string> BuildUserPrompt { get; init; }

    /// <summary>Whether the Full rung's cross-file payload was capped for this assignment.</summary>
    public bool ContextTruncated { get; init; }
}

/// <summary>
/// The direct-editing prompt family for the four-level context ladder (§4.4.3), version v1.0.0.
///
/// This is a new family rather than an edit to <see cref="FactorialSingleShotPrompt"/>, which is
/// frozen at v1.1.0 and reproduces the sealed v2 factorial. Two things differ and both require the
/// new identifier the thesis's own rule demands: the ladder covers Obsolete API Usage as well as
/// the two refactoring patterns, and every one of its conditions is grounded — the levels differ in
/// how much diagnosis they carry, not in whether they carry any, so there is no ungrounded variant.
///
/// The contract is otherwise deliberately identical to the factorial family: neutral target
/// coordinates, one complete edited file returned as JSON, no build or test feedback. Holding that
/// constant is what lets a ladder result be read alongside the confirmatory factorial rather than
/// being confounded with a change of task.
/// </summary>
public static class ContextLadderPrompt
{
    public const string Version = "ladder-v1.0.0";

    public const string SystemPrompt = """
        You are repairing a supplied, already-located static-analysis finding in one C# file. The
        finding is a God Class, a Long Method, or a use of a deprecated API.

        Return one complete edited production file. Preserve observable behaviour and the public
        contract. For a deprecated-API finding, migrate the call to the replacement the supplied
        context evidences; do not invent a replacement that the context does not show exists.

        You have one response and receive no build or test feedback.

        Respond ONLY with one JSON object:
        {
          "edited_file": "<full edited C# source>",
          "findings": [{"anti_pattern":"<GodClass|LongMethod|ObsoleteApiUsage>","symbol":"<symbol>","line":<int>,"remediation":"<what changed>"}]
        }
        """;

    /// <summary>
    /// The user prompt. The context block is whatever the level's specification produced, so the
    /// only thing that varies across the ladder is its content: the surrounding contract, the
    /// neutral coordinates and the pristine file are identical at every level.
    /// </summary>
    public static string BuildUserPrompt(
        string relativePath,
        string pristineSource,
        BlindedTargetDescriptor target,
        string? contextBlock,
        LoadedVisibleTestPrompt? visibleTest)
    {
        var context = string.IsNullOrWhiteSpace(contextBlock)
            ? string.Empty
            : $"## Static-analysis finding (repair this occurrence)\n{contextBlock.TrimEnd()}\n\n";

        var prompt = $$"""
            ## Neutral target declaration
            Symbol: {{target.SymbolName}}
            Source lines: {{target.StartLine}}-{{target.EndLine}}
            These coordinates identify the common repair unit but provide no anti-pattern label or metrics.

            {{context}}## Pristine source file: {{relativePath}}
            ```csharp
            {{pristineSource}}
            ```
            """;

        return PromptTemplate.AppendImmutableVisibleTest(prompt, visibleTest);
    }

    public static DirectEditPromptProfile Profile(ContextLevel level, bool contextTruncated = false) => new()
    {
        Architecture = $"context_ladder_{level.ToString().ToLowerInvariant()}",
        ContextLevel = level,
        SystemPrompt = SystemPrompt,
        PromptVersion = Version,
        BuildUserPrompt = BuildUserPrompt,
        ContextTruncated = contextTruncated
    };
}
