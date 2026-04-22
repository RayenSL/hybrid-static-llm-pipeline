namespace HybridLens.Core.Configuration;

public sealed class LlmConfig
{
    public string Provider { get; set; } = "claude";
    public string Model { get; set; } = "claude-sonnet-4-6";
    public float Temperature { get; set; } = 0.2f;
    public int MaxTokens { get; set; } = 1024;
    public string? ApiKey { get; set; }
    public string? BaseUrl { get; set; }
}
