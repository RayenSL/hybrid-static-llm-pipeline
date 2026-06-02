using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
using HybridLens.Core.QualityAttributes;
using HybridLens.StaticAnalysis.Abstractions;
using HybridLens.StaticAnalysis.Metrics;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace HybridLens.StaticAnalysis.Detectors;

/// <summary>
/// Detects the Long Method anti-pattern. Cyclomatic complexity is the primary gate
/// (McCabe 1976; Watson &amp; McCabe 1996): a method is flagged only when its CC exceeds
/// the configured bound. Lines-of-code is a secondary signal — it does not flag a method
/// on its own, but escalates an already-flagged method to Critical severity.
/// </summary>
public sealed class LongMethodDetector(LongMethodConfig config) : IDetector
{
    public AntiPatternType Type => AntiPatternType.LongMethod;

    public IEnumerable<Finding> Detect(Compilation compilation)
    {
        foreach (var tree in compilation.SyntaxTrees)
        {
            var root = tree.GetRoot();
            var filePath = tree.FilePath;

            foreach (var method in root.DescendantNodes().OfType<MethodDeclarationSyntax>())
            {
                var complexity = CyclomaticComplexity.Of(method);

                // Primary gate: cyclomatic complexity must exceed the bound.
                if (complexity <= config.MaxCyclomaticComplexity)
                    continue;

                var loc = CountLines(method, tree);
                var exceedsLoc = loc > config.MaxLinesOfCode; // secondary signal

                var lineSpan = tree.GetLineSpan(method.Span);
                var methodName = GetFullMethodName(method);

                yield return new Finding
                {
                    Type = AntiPatternType.LongMethod,
                    Severity = exceedsLoc ? Severity.Critical : Severity.Warning,
                    FilePath = filePath,
                    SymbolName = methodName,
                    Line = lineSpan.StartLinePosition.Line + 1,
                    Snippet = method.ToFullString(),
                    ExpectedQualityAttributes = QualityAttributeMap.ForType(AntiPatternType.LongMethod),
                    Metrics = new Dictionary<string, double>
                    {
                        ["CyclomaticComplexity"] = complexity,
                        ["LinesOfCode"] = loc,
                        ["MaxCyclomaticComplexity"] = config.MaxCyclomaticComplexity,
                        ["MaxLinesOfCode"] = config.MaxLinesOfCode
                    }
                };
            }
        }
    }

    private static int CountLines(MethodDeclarationSyntax method, SyntaxTree tree)
    {
        var span = tree.GetLineSpan(method.Span);
        return span.EndLinePosition.Line - span.StartLinePosition.Line + 1;
    }

    private static string GetFullMethodName(MethodDeclarationSyntax method)
    {
        var className = method.Ancestors()
            .OfType<TypeDeclarationSyntax>()
            .FirstOrDefault()
            ?.Identifier.Text ?? "<unknown>";

        return $"{className}.{method.Identifier.Text}";
    }
}
