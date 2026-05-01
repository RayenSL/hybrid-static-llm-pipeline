using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.Core.Models;

namespace HybridLens.CLI.Output;

/// <summary>
/// Emits a self-contained JSON document that includes every static finding
/// with its LLM analysis (one entry per model) nested inline.
/// </summary>
public sealed class JsonOutputFormatter : IOutputFormatter
{
    private static readonly JsonSerializerOptions SerializerOptions = new()
    {
        WriteIndented          = true,
        PropertyNamingPolicy   = JsonNamingPolicy.CamelCase,
        Converters             = { new JsonStringEnumConverter(JsonNamingPolicy.CamelCase) },
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
    };

    public async Task WriteAsync(
        IReadOnlyList<Finding>    findings,
        IReadOnlyList<LlmFinding> llmFindings,
        FileInfo                  target,
        TextWriter                writer,
        CancellationToken         cancellationToken = default)
    {
        // Index LLM results by finding for quick lookup
        var llmByFinding = llmFindings
            .GroupBy(lf => lf.Finding)
            .ToDictionary(g => g.Key, g => g.ToList());

        var baseDir = Path.GetDirectoryName(target.FullName)!;

        var doc = new
        {
            schemaVersion = "1.0",
            analysedAt    = DateTimeOffset.UtcNow,
            target        = target.FullName,
            summary = new
            {
                total        = findings.Count,
                critical     = findings.Count(f => f.Severity == Severity.Critical),
                warnings     = findings.Count(f => f.Severity == Severity.Warning),
                llmProcessed = llmFindings.Select(lf => lf.Finding).Distinct().Count()
            },
            findings = findings
                .OrderByDescending(f => f.Severity)
                .ThenBy(f => f.Type.ToString())
                .ThenBy(f => f.SymbolName)
                .Select(f => new
                {
                    type       = f.Type,
                    severity   = f.Severity,
                    symbolName = f.SymbolName,
                    filePath   = Path.GetRelativePath(baseDir, f.FilePath),
                    line       = f.Line,
                    snippet    = f.Snippet,
                    metrics    = f.Metrics.Count > 0 ? f.Metrics : null,
                    llmAnalysis = llmByFinding.TryGetValue(f, out var analyses)
                        ? analyses.Select(lf => new
                        {
                            model       = lf.ModelName,
                            explanation = lf.Explanation,
                            remediation = lf.Remediation
                        }).ToList()
                        : null
                })
                .ToList()
        };

        var json = JsonSerializer.Serialize(doc, SerializerOptions);
        await writer.WriteAsync(json.AsMemory(), cancellationToken);
        await writer.WriteLineAsync();
    }
}
