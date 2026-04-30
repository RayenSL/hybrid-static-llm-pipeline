namespace HybridLens.Core.Configuration;

public sealed class PipelineConfig
{
    /// <summary>Maximum number of findings sent to the LLM concurrently.</summary>
    public int MaxParallelism { get; set; } = 4;

    /// <summary>
    /// When false (default), only Critical findings are sent to the LLM.
    /// Set to true to also send Warning findings.
    /// </summary>
    public bool ProcessWarnings { get; set; } = false;
}
