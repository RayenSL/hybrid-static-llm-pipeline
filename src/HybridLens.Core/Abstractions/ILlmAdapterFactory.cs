using HybridLens.Core.Configuration;

namespace HybridLens.Core.Abstractions;

public interface ILlmAdapterFactory
{
    /// <summary>
    /// Creates one <see cref="ILlmAdapter"/> per entry in <see cref="LlmConfig.Models"/>,
    /// keyed by model name.
    /// </summary>
    IReadOnlyDictionary<string, ILlmAdapter> CreateAll(LlmConfig config);
}
