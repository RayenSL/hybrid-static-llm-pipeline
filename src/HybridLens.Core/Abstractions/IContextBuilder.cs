using HybridLens.Core.Configuration;
using HybridLens.Core.Models;

namespace HybridLens.Core.Abstractions;

public interface IContextBuilder
{
    /// <summary>
    /// Builds a grounded LLM request from a finding.
    /// <paramref name="allFindings"/> is required for Full context level
    /// to include related findings from the same file.
    /// </summary>
    LlmRequest Build(Finding finding, IReadOnlyList<Finding> allFindings, ContextConfig config);
}
