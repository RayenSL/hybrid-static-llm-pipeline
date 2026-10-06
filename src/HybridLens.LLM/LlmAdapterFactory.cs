using HybridLens.Core.Abstractions;
using HybridLens.Core.Configuration;

namespace HybridLens.LLM;

public sealed class LlmAdapterFactory : ILlmAdapterFactory
{
    public IReadOnlyDictionary<string, ILlmAdapter> CreateAll(LlmConfig config)
    {
        if (config.Models.Count == 0)
            throw new InvalidOperationException(
                "No models configured. Add at least one entry under Llm.Models in appsettings.json.");

        return config.Models.ToDictionary(
            kvp => kvp.Key,
            kvp => CreateAdapter(kvp.Value, config),
            StringComparer.OrdinalIgnoreCase);
    }

    private static ILlmAdapter CreateAdapter(LlmModelConfig model, LlmConfig defaults)
    {
        var resolved = new ResolvedLlmConfig(
            Provider:    model.Provider,
            Model:       model.Model,
            BaseUrl:     model.BaseUrl,
            Temperature: model.Temperature ?? defaults.Temperature,
            MaxTokens:   model.MaxTokens   ?? defaults.MaxTokens,
            ApiKey:      model.ApiKey      ?? defaults.ApiKey,
            TimeoutSeconds: model.TimeoutSeconds,
            MaxRetries:  model.MaxRetries);

        return resolved.Provider.ToLowerInvariant() switch
        {
            "claude" => new ClaudeAdapter(resolved),
            "azure"  => new AzureAIAdapter(resolved),
            _ => throw new InvalidOperationException(
                $"Unknown LLM provider '{resolved.Provider}'. Supported: claude, azure.")
        };
    }
}
