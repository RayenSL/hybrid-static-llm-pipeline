using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace HybridLens.StaticAnalysis.Metrics;

/// <summary>
/// McCabe cyclomatic complexity (1976): 1 + the number of independent decision points.
///
/// Each of the following adds one to the count: if, for, foreach, while, do,
/// switch case label, switch-expression arm, catch, when filter, conditional
/// (ternary) expression, logical &amp;&amp; / ||, and null-coalescing (?? / ??=).
///
/// Shared by <c>LongMethodDetector</c> (per-method CC) and the WMC component of
/// <c>ClassMetrics</c> (sum of method CCs), so both report identical numbers.
/// </summary>
public static class CyclomaticComplexity
{
    public static int Of(SyntaxNode node)
    {
        var complexity = 1;

        foreach (var n in node.DescendantNodes())
        {
            complexity += n switch
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
}
