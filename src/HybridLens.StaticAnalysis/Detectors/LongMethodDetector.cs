using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
using HybridLens.StaticAnalysis.Abstractions;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace HybridLens.StaticAnalysis.Detectors;

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
                var loc = CountLines(method, tree);
                var complexity = CountCyclomaticComplexity(method);

                var exceedsLoc = loc > config.MaxLinesOfCode;
                var exceedsComplexity = complexity > config.MaxCyclomaticComplexity;

                if (!exceedsLoc && !exceedsComplexity)
                    continue;

                var lineSpan = tree.GetLineSpan(method.Span);
                var methodName = GetFullMethodName(method);

                yield return new Finding
                {
                    Type = AntiPatternType.LongMethod,
                    Severity = exceedsLoc && exceedsComplexity ? Severity.Critical : Severity.Warning,
                    FilePath = filePath,
                    SymbolName = methodName,
                    Line = lineSpan.StartLinePosition.Line + 1,
                    Snippet = method.ToFullString(),
                    Metrics = new Dictionary<string, double>
                    {
                        ["LinesOfCode"] = loc,
                        ["CyclomaticComplexity"] = complexity,
                        ["MaxLinesOfCode"] = config.MaxLinesOfCode,
                        ["MaxCyclomaticComplexity"] = config.MaxCyclomaticComplexity
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

    /// <summary>
    /// Cyclomatic complexity = 1 + number of branching nodes in the method body.
    /// Each if / else-if / for / foreach / while / do / case / catch / when /
    /// conditional expression / null-coalescing / logical && or || adds 1.
    /// </summary>
    private static int CountCyclomaticComplexity(MethodDeclarationSyntax method)
    {
        var complexity = 1;

        foreach (var node in method.DescendantNodes())
        {
            complexity += node switch
            {
                IfStatementSyntax                                           => 1,
                ForStatementSyntax                                          => 1,
                ForEachStatementSyntax                                      => 1,
                WhileStatementSyntax                                        => 1,
                DoStatementSyntax                                           => 1,
                CaseSwitchLabelSyntax                                       => 1,
                CasePatternSwitchLabelSyntax                                => 1,
                SwitchExpressionArmSyntax                                   => 1,
                CatchClauseSyntax                                           => 1,
                WhenClauseSyntax                                            => 1,
                ConditionalExpressionSyntax                                 => 1,
                BinaryExpressionSyntax b when
                    b.IsKind(SyntaxKind.LogicalAndExpression) ||
                    b.IsKind(SyntaxKind.LogicalOrExpression)                => 1,
                AssignmentExpressionSyntax a when
                    a.IsKind(SyntaxKind.CoalesceAssignmentExpression)       => 1,
                BinaryExpressionSyntax c when
                    c.IsKind(SyntaxKind.CoalesceExpression)                 => 1,
                _                                                           => 0
            };
        }

        return complexity;
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
