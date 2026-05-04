namespace HybridLens.Core.Abstractions;

public interface ILlmAdapter
{
    Task<LlmResponse> CompleteAsync(LlmRequest request, CancellationToken cancellationToken = default);
}

public sealed record LlmRequest
{
    public required string SystemPrompt { get; init; }
    public required string UserPrompt { get; init; }
    /// <summary>Version identifier of the prompt template that produced this request (Req #4).</summary>
    public required string PromptVersion { get; init; }
}

public sealed record LlmResponse
{
    public required string Content { get; init; }
    public int InputTokens { get; init; }
    public int OutputTokens { get; init; }
}
