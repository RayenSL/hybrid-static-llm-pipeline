using HybridLens.Core.Models;

namespace HybridLens.CLI.Output;

/// <summary>
/// Renders LLM findings as a human-readable box-drawing table.
/// Static findings are printed progressively by AnalyseCommand before the LLM
/// pipeline runs, so this formatter only handles the LLM section.
/// </summary>
public sealed class ConsoleOutputFormatter : IOutputFormatter
{
    public Task WriteAsync(
        IReadOnlyList<Finding>    findings,
        IReadOnlyList<LlmFinding> llmFindings,
        FileInfo                  target,
        TextWriter                writer,
        CancellationToken         cancellationToken = default)
    {
        if (llmFindings.Count == 0)
            return Task.CompletedTask;

        var baseDir = Path.GetDirectoryName(target.FullName)!;

        foreach (var modelGroup in llmFindings.GroupBy(f => f.ModelName).OrderBy(g => g.Key))
        {
            writer.WriteLine($"{'═',1}{new string('═', 78)}");
            writer.WriteLine($"  Model: {modelGroup.Key}");
            writer.WriteLine($"{new string('═', 80)}{Environment.NewLine}");

            foreach (var lf in modelGroup.OrderByDescending(f => f.Finding.Severity))
            {
                var path = Path.GetRelativePath(baseDir, lf.Finding.FilePath);

                writer.WriteLine($"┌─ [{lf.Finding.Severity}] {lf.Finding.Type} — {lf.Finding.SymbolName}");
                writer.WriteLine($"│  {path}:{lf.Finding.Line}");
                writer.WriteLine($"│");
                writer.WriteLine($"│  Explanation");
                foreach (var line in lf.Explanation.Split('\n'))
                    writer.WriteLine($"│    {line}");
                writer.WriteLine($"│");
                writer.WriteLine($"│  Remediation");
                foreach (var line in lf.Remediation.Split('\n'))
                    writer.WriteLine($"│    {line}");

                if (lf.Finding.Snippet is { Length: > 0 } snippet)
                {
                    writer.WriteLine($"│");
                    writer.WriteLine($"│  Snippet");
                    foreach (var line in snippet.Split('\n'))
                        writer.WriteLine($"│    {line.TrimEnd()}");
                }

                writer.WriteLine($"└{new string('─', 80)}{Environment.NewLine}");
            }
        }

        return Task.CompletedTask;
    }
}
