namespace HybridLens.LLM;

/// <summary>
/// Flat, fully-resolved model config with defaults applied.
/// Created by <see cref="LlmAdapterFactory"/> — adapters only see this.
/// </summary>
internal sealed record ResolvedLlmConfig(
    string Provider,
    string Model,
    string? BaseUrl,
    float Temperature,
    int MaxTokens,
    string? ApiKey);
