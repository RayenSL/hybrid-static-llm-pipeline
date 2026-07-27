using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

/// <summary>
/// A known anti-pattern instance from the static analyser — the ground truth against
/// which an agentic self-detection is matched (§4.5.1). Reconstructed from a
/// normal analyzer run trace: the line range is derived from the start line plus
/// the snippet's line count.
/// </summary>
public sealed record KnownInstance
{
    public required AntiPatternType Type       { get; init; }
    public required string          FilePath   { get; init; }
    public required string          SymbolName { get; init; }
    public required int             Line       { get; init; }   // start line (1-based)
    public required int             EndLine    { get; init; }   // inclusive end line
    public required Severity        Severity   { get; init; }
    public          string?         Snippet    { get; init; }

    /// <summary>Stable identifier used to pair agentic matches with hybrid rows in analysis.</summary>
    public string InstanceKey => $"{FilePath}::{SymbolName}::{Line}";

    /// <summary>Builds an instance, deriving the end line from the snippet length.</summary>
    public static KnownInstance Create(
        AntiPatternType type, string filePath, string symbolName, int line,
        Severity severity, string? snippet)
    {
        var normalizedSnippet = snippet?.Replace("\r\n", "\n").Trim('\r', '\n');
        var lineCount = string.IsNullOrEmpty(normalizedSnippet)
            ? 1
            : normalizedSnippet.Split('\n').Length;
        return new KnownInstance
        {
            Type       = type,
            FilePath   = filePath,
            SymbolName = symbolName,
            Line       = line,
            EndLine    = line + Math.Max(0, lineCount - 1),
            Severity   = severity,
            Snippet    = snippet
        };
    }
}
