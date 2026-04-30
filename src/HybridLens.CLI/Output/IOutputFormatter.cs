using HybridLens.Core.Models;

namespace HybridLens.CLI.Output;

/// <summary>
/// Writes the final analysis results to <paramref name="writer"/>.
/// For the console formatter this covers only the LLM section — static findings
/// are already printed progressively to stdout before the LLM pipeline runs.
/// For structured formatters (JSON, SARIF) this includes everything.
/// </summary>
public interface IOutputFormatter
{
    Task WriteAsync(
        IReadOnlyList<Finding>    findings,
        IReadOnlyList<LlmFinding> llmFindings,
        FileInfo                  target,
        TextWriter                writer,
        CancellationToken         cancellationToken = default);
}
