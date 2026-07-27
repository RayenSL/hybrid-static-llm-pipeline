namespace HybridLens.Core.Abstractions;

public interface ILlmAdapter
{
    /// <summary>Single-shot completion (system + one user message). Used by the hybrid arm and the repair applier.</summary>
    Task<LlmResponse> CompleteAsync(LlmRequest request, CancellationToken cancellationToken = default);

    /// <summary>
    /// Multi-turn completion over a running conversation (system + an alternating user/assistant
    /// transcript). Used by the agentic arm (§4.4.1, Appendix E v2.0.2), whose loop feeds each
    /// build result back as a new user turn and reads the model's next action.
    /// </summary>
    Task<LlmResponse> CompleteAsync(LlmConversation conversation, CancellationToken cancellationToken = default);
}

public sealed record LlmRequest
{
    public required string SystemPrompt { get; init; }
    public required string UserPrompt { get; init; }
    /// <summary>Version identifier of the prompt template that produced this request (Req #4).</summary>
    public required string PromptVersion { get; init; }
}

public enum ChatRole
{
    User,
    Assistant
}

/// <summary>One turn in an agentic conversation transcript.</summary>
public sealed record ChatTurn(ChatRole Role, string Content);

/// <summary>
/// A running conversation: a fixed system prompt plus the user/assistant transcript so far.
/// The adapter appends nothing of its own — the caller owns the turn list.
/// </summary>
public sealed record LlmConversation
{
    public required string SystemPrompt { get; init; }
    public required IReadOnlyList<ChatTurn> Turns { get; init; }
    /// <summary>Version identifier of the prompt template driving the conversation (Req #4).</summary>
    public required string PromptVersion { get; init; }
}

public sealed record LlmResponse
{
    public required string Content { get; init; }
    public int InputTokens { get; init; }
    public int OutputTokens { get; init; }
}
