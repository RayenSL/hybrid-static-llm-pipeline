using HybridLens.StaticAnalysis.Metrics;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace HybridLens.StaticAnalysis;

/// <summary>
/// Measures the Long Method triggering metrics (cyclomatic complexity + lines of code) for a single
/// target method from a STANDALONE source string, using the exact same computation as
/// <see cref="Detectors.LongMethodDetector"/>. Because CC and LOC are purely syntactic, this works on any
/// parseable source — including an intermediate agentic edit that failed to build — which is what makes a
/// per-iteration metric trace possible (§ metric-trajectory). Semantic metrics (God Class ATFD/WMC/TCC)
/// are deliberately out of scope here: they need a full compilation and so are only defined on states that
/// build, defeating the per-iteration purpose.
/// </summary>
public static class MethodMetricProbe
{
    /// <param name="Found">False when no method matched the target (e.g. renamed/removed by the refactor).</param>
    /// <param name="HasSyntaxErrors">True when the source did not parse cleanly (CC/LOC are then best-effort).</param>
    public sealed record MethodMetric(string Method, int Cc, int Loc, bool Found, bool HasSyntaxErrors);

    public static MethodMetric Measure(string source, string? targetSymbol)
    {
        var tree = CSharpSyntaxTree.ParseText(source);
        var root = tree.GetRoot();
        var hasErrors = root.GetDiagnostics().Any(d => d.Severity == DiagnosticSeverity.Error);

        var methods = root.DescendantNodes().OfType<MethodDeclarationSyntax>().ToList();
        if (methods.Count == 0)
            return new MethodMetric("", 0, 0, Found: false, hasErrors);

        MethodDeclarationSyntax? target = null;
        if (!string.IsNullOrWhiteSpace(targetSymbol))
        {
            var want   = LastTwoSegments(targetSymbol!);          // e.g. "AllocationCalculator.Allocate"
            var method = MethodIdentifier(targetSymbol!);         // e.g. "Allocate"
            target = methods.FirstOrDefault(m =>
                         FullName(m).EndsWith(want, StringComparison.OrdinalIgnoreCase))
                  ?? methods.FirstOrDefault(m =>
                         m.Identifier.Text.Equals(method, StringComparison.OrdinalIgnoreCase));
        }

        // Fallback: the worst (highest-CC) method — the Long Method instance the detector would flag.
        var found = target is not null;
        target ??= methods.OrderByDescending(CyclomaticComplexity.Of).First();

        var cc  = CyclomaticComplexity.Of(target);
        var ls  = tree.GetLineSpan(target.Span);
        var loc = ls.EndLinePosition.Line - ls.StartLinePosition.Line + 1;   // identical to LongMethodDetector.CountLines
        return new MethodMetric(FullName(target), cc, loc, found, hasErrors);
    }

    /// <param name="Found">False when no class matched the target symbol (e.g. renamed/removed).</param>
    public sealed record ClassWmc(string Class, int Wmc, int MethodCount, bool Found, bool HasSyntaxErrors);

    /// <summary>
    /// Measures a class's WMC (Weighted Method Count = sum of the cyclomatic complexities of its declared
    /// methods) from a standalone source string, identically to <see cref="Metrics.ClassMetrics"/>'s WMC —
    /// which is syntactic, so it is defined on any parseable God Class edit. The other God Class metrics
    /// (ATFD, TCC) are semantic and deliberately not traced here (they need a full compilation).
    /// </summary>
    public static ClassWmc MeasureWmc(string source, string classSymbol)
    {
        var tree = CSharpSyntaxTree.ParseText(source);
        var root = tree.GetRoot();
        var hasErrors = root.GetDiagnostics().Any(d => d.Severity == DiagnosticSeverity.Error);

        var className = classSymbol.Split('.', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries) is { Length: > 0 } p
            ? p[^1] : classSymbol;

        var target = root.DescendantNodes().OfType<ClassDeclarationSyntax>()
            .FirstOrDefault(c => c.Identifier.Text.Equals(className, StringComparison.OrdinalIgnoreCase));
        if (target is null)
            return new ClassWmc(className, 0, 0, Found: false, hasErrors);

        var methods = target.Members.OfType<MethodDeclarationSyntax>().ToList();
        return new ClassWmc(target.Identifier.Text, methods.Sum(CyclomaticComplexity.Of), methods.Count, true, hasErrors);
    }

    private static string FullName(MethodDeclarationSyntax m)
    {
        var cls = m.Ancestors().OfType<TypeDeclarationSyntax>().FirstOrDefault()?.Identifier.Text ?? "<unknown>";
        return $"{cls}.{m.Identifier.Text}";
    }

    private static string LastTwoSegments(string symbol)
    {
        var parts = symbol.Split('.', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        return parts.Length >= 2 ? $"{parts[^2]}.{parts[^1]}" : symbol;
    }

    private static string MethodIdentifier(string symbol)
    {
        var parts = symbol.Split('.', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        return parts.Length >= 1 ? parts[^1] : symbol;
    }
}
