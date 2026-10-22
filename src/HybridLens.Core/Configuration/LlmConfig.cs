namespace HybridLens.Core.Configuration;

public sealed class LlmConfig
{
    /// <summary>Shared defaults inherited by every model unless overridden at model level.</summary>
    public float Temperature { get; set; } = 0.2f;
    public int MaxTokens { get; set; } = 1024;
    public string? ApiKey { get; set; }

    /// <summary>Named model configurations. At least one entry is required.</summary>
    public IDictionary<string, LlmModelConfig> Models { get; set; } = new Dictionary<string, LlmModelConfig>();
}

public sealed class LlmModelConfig
{
    public string Provider { get; set; } = "azure";
    public string Model { get; set; } = string.Empty;
    public string? BaseUrl { get; set; }

    /// <summary>Overrides <see cref="LlmConfig.Temperature"/> when set.</summary>
    public float? Temperature { get; set; }

    /// <summary>Overrides <see cref="LlmConfig.MaxTokens"/> when set.</summary>
    public int? MaxTokens { get; set; }

    /// <summary>Overrides <see cref="LlmConfig.ApiKey"/> when set.</summary>
    public string? ApiKey { get; set; }

    // Unset keeps the SDK defaults (100 s, three retries) used by earlier campaigns; retries resend billed requests whose usage is never reported.
    public int? TimeoutSeconds { get; set; }
    public int? MaxRetries { get; set; }
}
