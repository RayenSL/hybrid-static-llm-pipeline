namespace HybridLens.Core.Models;

/// <summary>
/// Anti-pattern-neutral coordinates for the declaration whose existing behaviour is
/// being characterised and repaired. The descriptor deliberately contains no detector
/// label, severity, metrics, thresholds, explanation, or suggested repair.
/// </summary>
public sealed record BlindedTargetDescriptor
{
    public required string SymbolName { get; init; }
    public required int StartLine { get; init; }
    public required int EndLine { get; init; }

    public static BlindedTargetDescriptor Create(string symbolName, int startLine, int endLine)
    {
        if (string.IsNullOrWhiteSpace(symbolName))
            throw new ArgumentException("target symbol is required", nameof(symbolName));
        if (startLine < 1)
            throw new ArgumentOutOfRangeException(nameof(startLine));
        if (endLine < startLine)
            throw new ArgumentOutOfRangeException(nameof(endLine));
        return new BlindedTargetDescriptor
        {
            SymbolName = symbolName.Trim(),
            StartLine = startLine,
            EndLine = endLine
        };
    }
}
