using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
using HybridLens.Core.QualityAttributes;
using HybridLens.StaticAnalysis.Abstractions;
using HybridLens.StaticAnalysis.Metrics;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace HybridLens.StaticAnalysis.Detectors;

/// <summary>
/// Detects the God Class anti-pattern using the composite detection strategy of
/// Lanza &amp; Marinescu (2006): a class is flagged iff all three conditions hold
/// simultaneously —
/// <c>(ATFD &gt; FEW) ∧ (WMC ≥ VERY_HIGH) ∧ (TCC &lt; 1/3)</c>.
/// Requires the semantic model to resolve foreign-data access and field cohesion.
/// Operates on class declarations only (not struct/record/interface).
/// </summary>
public sealed class GodClassDetector(GodClassConfig config) : IDetector
{
    public AntiPatternType Type => AntiPatternType.GodClass;

    public IEnumerable<Finding> Detect(Compilation compilation)
    {
        foreach (var tree in compilation.SyntaxTrees)
        {
            var model = compilation.GetSemanticModel(tree);
            var root  = tree.GetRoot();

            foreach (var cls in root.DescendantNodes().OfType<ClassDeclarationSyntax>())
            {
                var m = ClassMetrics.Compute(cls, model);

                var exceedsAtfd = m.Atfd >  config.AtfdFew;
                var exceedsWmc  = m.Wmc  >= config.WmcVeryHigh;
                var lowCohesion = m.Tcc  <  config.TccThreshold;

                // Composite strategy: all three must hold.
                if (!(exceedsAtfd && exceedsWmc && lowCohesion))
                    continue;

                var lineSpan = tree.GetLineSpan(cls.Span);

                yield return new Finding
                {
                    Type       = AntiPatternType.GodClass,
                    Severity   = Severity.Critical, // composite condition is binary — always critical when met
                    FilePath   = tree.FilePath,
                    SymbolName = GetFullTypeName(cls),
                    Line       = lineSpan.StartLinePosition.Line + 1,
                    Snippet    = cls.ToFullString(),
                    ExpectedQualityAttributes = QualityAttributeMap.ForType(AntiPatternType.GodClass),
                    Metrics    = new Dictionary<string, double>
                    {
                        ["ATFD"]          = m.Atfd,
                        ["WMC"]           = m.Wmc,
                        ["TCC"]           = Math.Round(m.Tcc, 4),
                        ["PublicMethods"] = m.PublicMethodCount,
                        ["AtfdFew"]       = config.AtfdFew,
                        ["WmcVeryHigh"]   = config.WmcVeryHigh,
                        ["TccThreshold"]  = Math.Round(config.TccThreshold, 4)
                    }
                };
            }
        }
    }

    private static string GetFullTypeName(TypeDeclarationSyntax type)
    {
        var ns = type.Ancestors()
            .OfType<BaseNamespaceDeclarationSyntax>()
            .FirstOrDefault()
            ?.Name.ToString();

        return ns is not null
            ? $"{ns}.{type.Identifier.Text}"
            : type.Identifier.Text;
    }
}
