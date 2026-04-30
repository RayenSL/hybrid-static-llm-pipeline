namespace HybridLens.Core.Models;

public sealed record LlmFinding
{
    public required Finding Finding { get; init; }

    /// <summary>The key from <c>Llm.Models</c> that produced this result.</summary>
    public required string ModelName { get; init; }

    public required string Explanation { get; init; }
    public required string Remediation { get; init; }
}
