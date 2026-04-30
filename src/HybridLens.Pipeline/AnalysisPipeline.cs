using System.Text.Json;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Configuration;
using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

public sealed class AnalysisPipeline(
    IContextBuilder contextBuilder,
    IReadOnlyDictionary<string, ILlmAdapter> adapters,
    ContextConfig contextConfig,
    PipelineConfig pipelineConfig)
{
    public async Task<IReadOnlyList<LlmFinding>> RunAsync(
        IReadOnlyList<Finding> findings,
        Severity minSeverity = Severity.Critical,
        CancellationToken cancellationToken = default)
    {
        var eligible = Filter(findings, minSeverity);

        if (eligible.Count == 0 || adapters.Count == 0)
            return [];

        // One work item per (finding × model) combination
        var workItems = eligible
            .SelectMany(f => adapters.Select(a => (Finding: f, ModelName: a.Key, Adapter: a.Value)))
            .Select((item, i) => (item.Finding, item.ModelName, item.Adapter, Index: i))
            .ToList();

        var results = new LlmFinding?[workItems.Count];

        await Parallel.ForEachAsync(
            workItems,
            new ParallelOptions
            {
                MaxDegreeOfParallelism = pipelineConfig.MaxParallelism,
                CancellationToken      = cancellationToken
            },
            async (item, ct) =>
            {
                try
                {
                    var request  = contextBuilder.Build(item.Finding, findings, contextConfig);
                    var response = await item.Adapter.CompleteAsync(request, ct);
                    results[item.Index] = ParseResponse(response.Content, item.Finding, item.ModelName);
                }
                catch (OperationCanceledException)
                {
                    throw; // let cancellation propagate normally
                }
                catch (Exception ex)
                {
                    await Console.Error.WriteLineAsync(
                        $"  [llm-error] {item.ModelName} / {item.Finding.SymbolName}: {ex.Message}");
                }
            });

        return results.OfType<LlmFinding>().ToList();
    }

    private static List<Finding> Filter(IReadOnlyList<Finding> findings, Severity minSeverity)
    {
        return findings.Where(f => f.Severity >= minSeverity).ToList();
    }

    private static LlmFinding ParseResponse(string content, Finding finding, string modelName)
    {
        try
        {
            var json = content.Trim();
            if (json.StartsWith("```"))
            {
                json = string.Join('\n', json.Split('\n').Skip(1));
                json = json[..json.LastIndexOf("```", StringComparison.Ordinal)].Trim();
            }

            using var doc   = JsonDocument.Parse(json);
            var explanation = doc.RootElement.GetProperty("explanation").GetString() ?? string.Empty;
            var remediation = doc.RootElement.GetProperty("remediation").GetString() ?? string.Empty;

            return new LlmFinding
            {
                Finding     = finding,
                ModelName   = modelName,
                Explanation = explanation,
                Remediation = remediation
            };
        }
        catch
        {
            return new LlmFinding
            {
                Finding     = finding,
                ModelName   = modelName,
                Explanation = content,
                Remediation = "Could not parse structured response."
            };
        }
    }
}
