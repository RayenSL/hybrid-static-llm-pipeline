using HybridLens.Core.Configuration;
using HybridLens.Core.Models;

namespace HybridLens.Core.Abstractions;

public interface IContextBuilder
{
    /// <summary>Builds a grounded LLM request from a single finding and the current context config.</summary>
    LlmRequest Build(Finding finding, ContextConfig config);
}
