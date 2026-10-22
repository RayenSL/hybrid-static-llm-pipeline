using System.Security.Cryptography;
using System.Text;
using HybridLens.StaticAnalysis.Metrics;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace HybridLens.DesignQuality;

public sealed record CallableFact(string Id, string Kind, string Owner, int Line, int EndLine,
    int DecisionCount, int Complexity, int HistoricalComplexity, int MaxControlNesting,
    int TokenCount, string BodyFingerprint, string[] Calls, string[] AttributeAccesses,
    string[] ExternalTypes, int UnresolvedInvocations, string[] Statements);
public sealed record TypeFact(string Id, string Kind, int Line, int? Atfd, int? Wmc,
    double? Tcc, double? HistoricalTcc, int? PublicMethodCount, string[] BaseTypes);
public sealed record StateFact(string Id, string Owner, string Kind, string Type, bool IsStatic, bool IsReadOnlyField, string Accessibility);
public sealed record ExposureFact(string Id, string Accessibility, string Kind, string Signature);
public sealed record FileFacts(string Status, string[] ParseErrors, string[] SemanticErrors,
    CallableFact[] Callables, TypeFact[] Types, StateFact[] DeclaredState, ExposureFact[] ExposedMembers,
    string[] ExternalTypes, int DecisionCount, int? MaxComplexity,
    int? MaxControlNesting, Dictionary<int, CloneFact> Clones);
public sealed record CloneFact(int MinimumTokens, int EligibleTokens, int CoveredTokens, double? Proportion);

public static class StructuralFacts
{
    public static string SymbolId(ISymbol symbol)
    {
        var id = symbol.OriginalDefinition.GetDocumentationCommentId()
            ?? symbol.OriginalDefinition.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat);
        if (symbol is IMethodSymbol { MethodKind: MethodKind.LocalFunction or MethodKind.AnonymousFunction })
            id += "@" + symbol.DeclaringSyntaxReferences.FirstOrDefault()?.Span.Start;
        return id;
    }

    public static bool IsCallable(SyntaxNode n) => n is BaseMethodDeclarationSyntax
        or LocalFunctionStatementSyntax or AccessorDeclarationSyntax or AnonymousFunctionExpressionSyntax;

    private static IEnumerable<SyntaxNode> OwnedNodes(SyntaxNode n) =>
        n.DescendantNodes(descendIntoChildren: child => child == n || !IsCallable(child));

    public static int DecisionWeight(SyntaxNode n) => n switch
    {
        IfStatementSyntax or ForStatementSyntax or ForEachStatementSyntax or ForEachVariableStatementSyntax
            or WhileStatementSyntax or DoStatementSyntax or CaseSwitchLabelSyntax or CasePatternSwitchLabelSyntax
            or SwitchExpressionArmSyntax or CatchClauseSyntax or WhenClauseSyntax or ConditionalExpressionSyntax => 1,
        BinaryExpressionSyntax b when b.IsKind(SyntaxKind.LogicalAndExpression)
            || b.IsKind(SyntaxKind.LogicalOrExpression) || b.IsKind(SyntaxKind.CoalesceExpression) => 1,
        AssignmentExpressionSyntax a when a.IsKind(SyntaxKind.CoalesceAssignmentExpression) => 1,
        _ => 0
    };

    private static bool IsControl(SyntaxNode n) => n is IfStatementSyntax or ForStatementSyntax
        or ForEachStatementSyntax or ForEachVariableStatementSyntax or WhileStatementSyntax
        or DoStatementSyntax or SwitchStatementSyntax or SwitchExpressionSyntax or CatchClauseSyntax
        or ConditionalExpressionSyntax;

    private static string Tokens(SyntaxNode n) => string.Join(" ", n.DescendantTokens().Select(t => t.Text));
    private static string Hash(string text) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(text)));
    private static SyntaxNode Body(SyntaxNode n) => n switch
    {
        BaseMethodDeclarationSyntax m => (SyntaxNode?)m.Body ?? m.ExpressionBody ?? n,
        LocalFunctionStatementSyntax m => (SyntaxNode?)m.Body ?? m.ExpressionBody ?? n,
        AccessorDeclarationSyntax m => (SyntaxNode?)m.Body ?? m.ExpressionBody ?? n,
        AnonymousFunctionExpressionSyntax m => m.Body,
        _ => n
    };
    private static ISymbol? Declared(SemanticModel model, SyntaxNode n) => n is AnonymousFunctionExpressionSyntax
        ? model.GetSymbolInfo(n).Symbol : model.GetDeclaredSymbol(n);

    public static FileFacts Measure(Compilation compilation, SyntaxTree tree)
    {
        var root = tree.GetRoot();
        var parseErrors = tree.GetDiagnostics().Where(d => d.Severity == DiagnosticSeverity.Error).Select(d => d.ToString()).ToArray();
        var semanticErrors = compilation.GetDiagnostics().Where(d => d.Severity == DiagnosticSeverity.Error).Select(d => d.ToString()).ToArray();
        var semanticOk = semanticErrors.Length == 0;
        var model = compilation.GetSemanticModel(tree);
        var callables = new List<CallableFact>();
        foreach (var n in root.DescendantNodes().Where(IsCallable))
        {
            var symbol = Declared(model, n);
            var span = n.GetLocation().GetLineSpan();
            var id = symbol is null ? $"unresolved:{n.Kind()}:{n.SpanStart}" : SymbolId(symbol);
            var nodes = OwnedNodes(n).ToArray();
            var decisions = nodes.Sum(DecisionWeight);
            var nesting = nodes.Where(IsControl).Select(c => 1 + c.Ancestors().TakeWhile(a => a != n).Count(IsControl)).DefaultIfEmpty(0).Max();
            var calls = new HashSet<string>();
            var attributes = new HashSet<string>();
            var external = new HashSet<string>();
            var unresolved = 0;
            foreach (var node in nodes)
            {
                if (node is InvocationExpressionSyntax or ObjectCreationExpressionSyntax or ImplicitObjectCreationExpressionSyntax)
                {
                    var info = model.GetSymbolInfo(node);
                    if (info.Symbol is IMethodSymbol method) calls.Add(SymbolId(method.ReducedFrom ?? method));
                    else unresolved++;
                }
                if (node is IdentifierNameSyntax or MemberAccessExpressionSyntax)
                {
                    var accessed = model.GetSymbolInfo(node).Symbol;
                    if (accessed is IFieldSymbol or IPropertySymbol) attributes.Add(SymbolId(accessed));
                    var owner = accessed as INamedTypeSymbol ?? accessed?.ContainingType;
                    if (owner is not null && !owner.Locations.Any(l => l.SourceTree == tree)) external.Add(SymbolId(owner));
                }
            }
            callables.Add(new(id, n.Kind().ToString(), symbol?.ContainingType is { } type ? SymbolId(type) : "unresolved",
                span.StartLinePosition.Line + 1, span.EndLinePosition.Line + 1,
                decisions, decisions + 1, CyclomaticComplexity.Of(n), nesting,
                Body(n).DescendantTokens().Count(), Hash(Tokens(Body(n))),
                semanticOk ? calls.Order().ToArray() : [], semanticOk ? attributes.Order().ToArray() : [],
                semanticOk ? external.Order().ToArray() : [], unresolved,
                nodes.OfType<StatementSyntax>().Where(s => s is not BlockSyntax).Select(s => Hash(Tokens(s))).Distinct().Order().ToArray()));
        }
        var types = root.DescendantNodes().OfType<TypeDeclarationSyntax>().Select(n =>
        {
            var symbol = model.GetDeclaredSymbol(n);
            var metrics = semanticOk && n is ClassDeclarationSyntax cls ? ClassMetrics.Compute(cls, model) : null;
            return new TypeFact(symbol is null ? $"unresolved:{n.SpanStart}" : SymbolId(symbol), n.Kind().ToString(),
                n.GetLocation().GetLineSpan().StartLinePosition.Line + 1,
                metrics?.Atfd, metrics?.Wmc, metrics is { PublicMethodCount: >= 2 } ? metrics.Tcc : null,
                metrics?.Tcc, metrics?.PublicMethodCount,
                semanticOk && symbol is INamedTypeSymbol named
                    ? named.Interfaces.Select(SymbolId).Concat(named.BaseType is null ? [] : new[] { SymbolId(named.BaseType) }).Order().ToArray() : []);
        }).ToArray();
        // Restrict semantic facts to complete compilations. Empty arrays are not usable when status != measured.
        var state = semanticOk ? root.DescendantNodes().Select(n => n is VariableDeclaratorSyntax or PropertyDeclarationSyntax ? Declared(model, n) : null)
            .Where(s => s is IFieldSymbol or IPropertySymbol).Select(s => new StateFact(SymbolId(s!), SymbolId(s!.ContainingType),
                s.Kind.ToString(), s is IFieldSymbol f ? f.Type.ToDisplayString() : ((IPropertySymbol)s).Type.ToDisplayString(),
                s.IsStatic, s is IFieldSymbol { IsReadOnly: true }, s.DeclaredAccessibility.ToString())).OrderBy(s => s.Id).ToArray() : [];
        var exposures = semanticOk ? root.DescendantNodes().Select(n => n is MemberDeclarationSyntax or VariableDeclaratorSyntax ? Declared(model, n) : null)
            .Where(s => s is not null && s.DeclaredAccessibility is Accessibility.Public or Accessibility.Protected or Accessibility.ProtectedOrInternal)
            .Select(s => new ExposureFact(SymbolId(s!), s!.DeclaredAccessibility.ToString(), s.Kind.ToString(), s.ToDisplayString(SymbolDisplayFormat.CSharpErrorMessageFormat)))
            .Distinct().OrderBy(s => s.Id).ToArray() : [];
        var cloneBodies = root.DescendantNodes().Where(n => IsCallable(n) && !n.Ancestors().Any(IsCallable))
            .Select(n => Body(n).DescendantTokens().Select(t => t.Text).ToArray()).ToArray();
        return new FileFacts(parseErrors.Length > 0 ? "parse_error" : semanticOk ? "measured" : "semantic_error",
            parseErrors, semanticErrors, callables.ToArray(), types, state, exposures,
            callables.SelectMany(c => c.ExternalTypes).Distinct().Order().ToArray(), callables.Sum(c => c.DecisionCount),
            callables.Count == 0 ? null : callables.Max(c => c.Complexity),
            callables.Count == 0 ? null : callables.Max(c => c.MaxControlNesting),
            new[] { 30, 50, 70 }.ToDictionary(n => n, n => CloneCoverage(cloneBodies, n)));
    }

    // Exact token windows, no identifier/literal renaming, cross-callable only.
    // A repeated window is clone evidence only if its occurrences are in different bodies.
    public static CloneFact CloneCoverage(string[][] bodies, int minimum)
    {
        if (minimum < 1) throw new ArgumentOutOfRangeException(nameof(minimum));
        var windows = new Dictionary<string, List<(int Body, int Start)>>();
        for (var b = 0; b < bodies.Length; b++)
            for (var i = 0; i + minimum <= bodies[b].Length; i++)
            {
                var key = string.Join("\0", bodies[b].Skip(i).Take(minimum));
                if (!windows.TryGetValue(key, out var occurrences)) windows[key] = occurrences = [];
                occurrences.Add((b, i));
            }
        var covered = new HashSet<(int, int)>();
        foreach (var occurrences in windows.Values.Where(v => v.Select(x => x.Body).Distinct().Count() > 1))
            foreach (var (b, start) in occurrences)
                for (var i = start; i < start + minimum; i++) covered.Add((b, i));
        var eligible = bodies.Sum(b => b.Length);
        return new(minimum, eligible, covered.Count, eligible == 0 ? null : (double)covered.Count / eligible);
    }
}
