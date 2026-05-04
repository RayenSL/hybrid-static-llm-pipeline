using System.Text;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Configuration;
using HybridLens.Core.Models;

namespace HybridLens.ContextBuilder;

public sealed class ContextBuilder : IContextBuilder
{
    public LlmRequest Build(Finding finding, IReadOnlyList<Finding> allFindings, ContextConfig config)
    {
        var userPrompt = config.Level switch
        {
            ContextLevel.Minimal     => BuildMinimal(finding),
            ContextLevel.Structural  => BuildStructural(finding),
            ContextLevel.Relational  => BuildRelational(finding, config),
            ContextLevel.Full        => BuildFull(finding, allFindings, config),
            _                        => BuildStructural(finding)
        };

        return new LlmRequest
        {
            SystemPrompt  = PromptTemplate.SystemPrompt,
            UserPrompt    = userPrompt,
            PromptVersion = PromptTemplate.Version
        };
    }

    // ── Level 1: code fragment only ──────────────────────────────────────────

    private static string BuildMinimal(Finding finding)
    {
        var sb = new StringBuilder();
        sb.AppendLine($"Anti-pattern: {finding.Type}");
        sb.AppendLine();
        AppendSnippet(sb, finding.Snippet);
        return sb.ToString();
    }

    // ── Level 2: snippet + symbol + location + metrics ────────────────────────

    private static string BuildStructural(Finding finding)
    {
        var sb = new StringBuilder();
        AppendHeader(sb, finding);
        AppendMetrics(sb, finding);
        sb.AppendLine();
        AppendSnippet(sb, finding.Snippet);
        return sb.ToString();
    }

    // ── Level 3: structural + surrounding lines + class member summary ────────

    private static string BuildRelational(Finding finding, ContextConfig config)
    {
        var sb = new StringBuilder();
        AppendHeader(sb, finding);
        AppendMetrics(sb, finding);
        sb.AppendLine();
        AppendClassMemberSummary(sb, finding);
        sb.AppendLine();
        AppendSurroundingLines(sb, finding, config.SnippetContextLines);
        sb.AppendLine();
        AppendSnippet(sb, finding.Snippet);
        return sb.ToString();
    }

    // ── Level 4: relational + metadata + related findings in same file ────────

    private static string BuildFull(Finding finding, IReadOnlyList<Finding> allFindings, ContextConfig config)
    {
        var sb = new StringBuilder();
        AppendHeader(sb, finding);
        AppendMetrics(sb, finding);
        sb.AppendLine();

        if (config.Metadata.Count > 0)
        {
            sb.AppendLine("## Project metadata");
            foreach (var (key, value) in config.Metadata)
                sb.AppendLine($"  {key}: {value}");
            sb.AppendLine();
        }

        var relatedInFile = allFindings
            .Where(f => f.FilePath == finding.FilePath && f != finding)
            .ToList();

        if (relatedInFile.Count > 0)
        {
            sb.AppendLine("## Other findings in the same file");
            foreach (var related in relatedInFile)
                sb.AppendLine($"  - [{related.Type}] {related.SymbolName} (line {related.Line})");
            sb.AppendLine();
        }

        AppendClassMemberSummary(sb, finding);
        sb.AppendLine();
        AppendSurroundingLines(sb, finding, config.SnippetContextLines);
        sb.AppendLine();
        AppendSnippet(sb, finding.Snippet);
        return sb.ToString();
    }

    // ── Shared building blocks ────────────────────────────────────────────────

    private static void AppendHeader(StringBuilder sb, Finding finding)
    {
        sb.AppendLine($"## Finding");
        sb.AppendLine($"Anti-pattern : {finding.Type}");
        sb.AppendLine($"Severity     : {finding.Severity}");
        sb.AppendLine($"Symbol       : {finding.SymbolName}");
        sb.AppendLine($"Location     : {finding.FilePath}:{finding.Line}");
    }

    private static void AppendMetrics(StringBuilder sb, Finding finding)
    {
        if (finding.Metrics.Count == 0) return;

        sb.AppendLine();
        sb.AppendLine("## Metrics");
        foreach (var (key, value) in finding.Metrics)
            sb.AppendLine($"  {key}: {value}");
    }

    private static void AppendSnippet(StringBuilder sb, string? snippet)
    {
        if (string.IsNullOrWhiteSpace(snippet)) return;

        sb.AppendLine("## Code");
        sb.AppendLine("```csharp");
        sb.AppendLine(snippet.TrimEnd());
        sb.AppendLine("```");
    }

    private static void AppendSurroundingLines(StringBuilder sb, Finding finding, int contextLines)
    {
        if (!File.Exists(finding.FilePath) || contextLines <= 0) return;

        var allLines = File.ReadAllLines(finding.FilePath);
        var start = Math.Max(0, finding.Line - 1 - contextLines);
        var end   = Math.Min(allLines.Length - 1, finding.Line - 1 + contextLines);

        sb.AppendLine("## Surrounding code");
        sb.AppendLine("```csharp");
        for (var i = start; i <= end; i++)
            sb.AppendLine($"{i + 1,5}: {allLines[i]}");
        sb.AppendLine("```");
    }

    private static void AppendClassMemberSummary(StringBuilder sb, Finding finding)
    {
        if (!File.Exists(finding.FilePath)) return;

        // Extract public/private member signatures from the file without re-parsing
        // via Roslyn — a lightweight line scan is sufficient here.
        var memberLines = File.ReadAllLines(finding.FilePath)
            .Select(l => l.Trim())
            .Where(l =>
                l.StartsWith("public ")  ||
                l.StartsWith("private ") ||
                l.StartsWith("protected ") ||
                l.StartsWith("internal "))
            .Where(l =>
                l.Contains('(') || // methods
                l.Contains(" { ") || // properties
                (l.Contains(' ') && !l.Contains('('))) // fields
            .Take(30)
            .ToList();

        if (memberLines.Count == 0) return;

        sb.AppendLine("## Class member summary (up to 30 members)");
        foreach (var line in memberLines)
            sb.AppendLine($"  {line}");
    }
}
