namespace HybridLens.Core.Models;

public sealed record LlmFinding
{
    public required Finding Finding { get; init; }

    /// <summary>The key from <c>Llm.Models</c> that produced this result.</summary>
    public required string ModelName { get; init; }

    public required string Explanation { get; init; }
    public required string Remediation { get; init; }

    /// <summary>Free-text quality-impact section emitted by the LLM (prompt v1.1.0+). May be empty for older prompts.</summary>
    public string QualityImpact { get; init; } = string.Empty;

    /// <summary>ISO/IEC 25010 attributes mentioned anywhere in the LLM's output (auto-extracted, lexical match).</summary>
    public IReadOnlyList<string> MentionedQualityAttributes { get; init; } = Array.Empty<string>();

    // ── Experiment metadata (Req #2, #4, #5) ─────────────────────────────────
    /// <summary>Run index 1..N when the same combination is executed multiple times.</summary>
    public int RunNumber { get; init; } = 1;

    /// <summary>Context level used to construct the prompt that produced this result.</summary>
    public ContextLevel ContextLevel { get; init; } = ContextLevel.Structural;

    /// <summary>Version of the prompt template that produced this result.</summary>
    public string PromptVersion { get; init; } = "unspecified";
}
