using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
using HybridLens.StaticAnalysis.Abstractions;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace HybridLens.StaticAnalysis.Detectors;

public sealed class GodClassDetector(GodClassConfig config) : IDetector
{
    public AntiPatternType Type => AntiPatternType.GodClass;

    public IEnumerable<Finding> Detect(Compilation compilation)
    {
        foreach (var tree in compilation.SyntaxTrees)
        {
            var root = tree.GetRoot();

            foreach (var type in root.DescendantNodes().OfType<TypeDeclarationSyntax>())
            {
                var methods = type.Members.OfType<MethodDeclarationSyntax>().Count();
                var fields  = type.Members.OfType<FieldDeclarationSyntax>().Count()
                            + type.Members.OfType<PropertyDeclarationSyntax>().Count();
                var loc     = CountLines(type, tree);

                var exceedsMethods = methods > config.MaxMethods;
                var exceedsFields  = fields  > config.MaxFields;
                var exceedsLoc     = loc     > config.MaxLinesOfCode;

                var violations = (exceedsMethods ? 1 : 0)
                               + (exceedsFields  ? 1 : 0)
                               + (exceedsLoc     ? 1 : 0);

                if (violations == 0)
                    continue;

                var lineSpan = tree.GetLineSpan(type.Span);

                yield return new Finding
                {
                    Type     = AntiPatternType.GodClass,
                    Severity = violations >= 2 ? Severity.Critical : Severity.Warning,
                    FilePath   = tree.FilePath,
                    SymbolName = GetFullTypeName(type),
                    Line       = lineSpan.StartLinePosition.Line + 1,
                    Snippet    = type.ToFullString(),
                    Metrics    = new Dictionary<string, double>
                    {
                        ["Methods"]              = methods,
                        ["Fields"]               = fields,
                        ["LinesOfCode"]          = loc,
                        ["MaxMethods"]           = config.MaxMethods,
                        ["MaxFields"]            = config.MaxFields,
                        ["MaxLinesOfCode"]       = config.MaxLinesOfCode
                    }
                };
            }
        }
    }

    private static int CountLines(TypeDeclarationSyntax type, SyntaxTree tree)
    {
        var span = tree.GetLineSpan(type.Span);
        return span.EndLinePosition.Line - span.StartLinePosition.Line + 1;
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
