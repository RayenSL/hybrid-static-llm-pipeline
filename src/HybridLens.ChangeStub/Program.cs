using System.Text.Json;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace HybridLens.ChangeStub;

public sealed record StubResult(string Text, string[] Stubbed, string[] Unstubbable);

public static class ChangeStubber
{
    private const string Throw = "throw new global::System.NotImplementedException()";

    public static StubResult Stub(string pre, string post)
    {
        var before = Members(CSharpSyntaxTree.ParseText(pre).GetRoot());
        var stubber = new Rewriter(before);
        var text = stubber.Visit(CSharpSyntaxTree.ParseText(post).GetRoot()).ToFullString();
        return new StubResult(text, [.. stubber.Stubbed], [.. stubber.Unstubbable]);
    }

    private static string Tokens(SyntaxNode node) => string.Join(" ", node.DescendantTokens().Select(t => t.Text));

    internal static string TypeChain(SyntaxNode node) => string.Join(".", node.AncestorsAndSelf().OfType<BaseTypeDeclarationSyntax>().Reverse()
        .Select(t => t is TypeDeclarationSyntax { TypeParameterList: { } tp } ? $"{t.Identifier.Text}`{tp.Parameters.Count}" : t.Identifier.Text));

    private static string Parameters(BaseParameterListSyntax? list) => list is null ? "" :
        string.Join(",", list.Parameters.Select(p => string.Join(" ", p.Modifiers.Select(m => m.Text).Append(p.Type is null ? "" : Tokens(p.Type)))));

    internal static string? Key(SyntaxNode node)
    {
        var owner = TypeChain(node.Parent!);
        return node switch
        {
            MethodDeclarationSyntax m => $"{owner}.{m.Identifier.Text}{(m.TypeParameterList is { } tp ? $"`{tp.Parameters.Count}" : "")}({Parameters(m.ParameterList)})",
            ConstructorDeclarationSyntax c => $"{owner}.{(c.Modifiers.Any(SyntaxKind.StaticKeyword) ? "static " : "")}{c.Identifier.Text}({Parameters(c.ParameterList)})",
            DestructorDeclarationSyntax d => $"{owner}.~{d.Identifier.Text}()",
            OperatorDeclarationSyntax o => $"{owner}.operator{o.OperatorToken.Text}({Parameters(o.ParameterList)})",
            ConversionOperatorDeclarationSyntax c => $"{owner}.operator {c.ImplicitOrExplicitKeyword.Text} {Tokens(c.Type)}({Parameters(c.ParameterList)})",
            PropertyDeclarationSyntax p => $"{owner}.{p.Identifier.Text}",
            IndexerDeclarationSyntax i => $"{owner}.this[{Parameters(i.ParameterList)}]",
            EventDeclarationSyntax e => $"{owner}.{e.Identifier.Text}",
            VariableDeclaratorSyntax v when v.Parent?.Parent is BaseFieldDeclarationSyntax f => $"{TypeChain(f.Parent!)}.{v.Identifier.Text}",
            _ => null
        };
    }

    private static string Shape(SyntaxNode node) => node is VariableDeclaratorSyntax v
        ? Tokens(((VariableDeclarationSyntax)v.Parent!).Type) + " " + Tokens(v)
        : Tokens(node);

    private static Dictionary<string, string> Members(SyntaxNode root)
    {
        var members = new Dictionary<string, string>();
        foreach (var node in root.DescendantNodes())
            if (Key(node) is { } key)
                members.TryAdd(key, Shape(node));
        return members;
    }

    private static BlockSyntax ThrowBlock(BlockSyntax old) =>
        ((BlockSyntax)SyntaxFactory.ParseStatement("{ " + Throw + "; }")).WithTriviaFrom(old);

    private static ArrowExpressionClauseSyntax ThrowArrow(ArrowExpressionClauseSyntax old) =>
        old.WithExpression(SyntaxFactory.ParseExpression(Throw).WithTriviaFrom(old.Expression));

    private sealed class Rewriter(Dictionary<string, string> before) : CSharpSyntaxRewriter
    {
        public List<string> Stubbed { get; } = [];
        public List<string> Unstubbable { get; } = [];

        private bool Changed(SyntaxNode node, out string key)
        {
            key = Key(node)!;
            return !before.TryGetValue(key, out var shape) || shape != Shape(node);
        }

        private SyntaxNode Body(SyntaxNode node, BlockSyntax? body, ArrowExpressionClauseSyntax? arrow,
            Func<BlockSyntax, SyntaxNode> withBody, Func<ArrowExpressionClauseSyntax, SyntaxNode> withArrow)
        {
            if (!Changed(node, out var key) || (body is null && arrow is null)) return node;
            Stubbed.Add(key);
            return body is not null ? withBody(ThrowBlock(body)) : withArrow(ThrowArrow(arrow!));
        }

        public override SyntaxNode? VisitMethodDeclaration(MethodDeclarationSyntax node) =>
            Body(node, node.Body, node.ExpressionBody, node.WithBody, node.WithExpressionBody);

        public override SyntaxNode? VisitConstructorDeclaration(ConstructorDeclarationSyntax node) =>
            Body(node, node.Body, node.ExpressionBody, node.WithBody, node.WithExpressionBody);

        public override SyntaxNode? VisitDestructorDeclaration(DestructorDeclarationSyntax node) =>
            Body(node, node.Body, node.ExpressionBody, node.WithBody, node.WithExpressionBody);

        public override SyntaxNode? VisitOperatorDeclaration(OperatorDeclarationSyntax node) =>
            Body(node, node.Body, node.ExpressionBody, node.WithBody, node.WithExpressionBody);

        public override SyntaxNode? VisitConversionOperatorDeclaration(ConversionOperatorDeclarationSyntax node) =>
            Body(node, node.Body, node.ExpressionBody, node.WithBody, node.WithExpressionBody);

        public override SyntaxNode? VisitPropertyDeclaration(PropertyDeclarationSyntax node) =>
            node.ExpressionBody is { } arrow ? Body(node, null, arrow, _ => node, node.WithExpressionBody) : Accessors(node, node.AccessorList, l => node.WithAccessorList(l));

        public override SyntaxNode? VisitIndexerDeclaration(IndexerDeclarationSyntax node) =>
            node.ExpressionBody is { } arrow ? Body(node, null, arrow, _ => node, node.WithExpressionBody) : Accessors(node, node.AccessorList, l => node.WithAccessorList(l));

        public override SyntaxNode? VisitEventDeclaration(EventDeclarationSyntax node) =>
            Accessors(node, node.AccessorList, l => node.WithAccessorList(l));

        public override SyntaxNode? VisitVariableDeclarator(VariableDeclaratorSyntax node)
        {
            if (Key(node) is not null && Changed(node, out var key) && (before.ContainsKey(key) || node.Initializer is not null))
                Unstubbable.Add(key);
            return node;
        }

        private SyntaxNode Accessors(SyntaxNode node, AccessorListSyntax? list, Func<AccessorListSyntax, SyntaxNode> withList)
        {
            if (list is null || !Changed(node, out var key)) return node;
            if (!list.Accessors.Any(a => a.Body is not null || a.ExpressionBody is not null))
            {
                if (before.ContainsKey(key)) Unstubbable.Add(key);
                return node;
            }
            Stubbed.Add(key);
            return withList(list.WithAccessors(SyntaxFactory.List(list.Accessors.Select(a =>
                a.Body is { } b ? a.WithBody(ThrowBlock(b)) : a.ExpressionBody is { } e ? a.WithExpressionBody(ThrowArrow(e)) : a))));
        }
    }
}

public static class ApiChecker
{
    public static string[] Missing(string reference, string candidate)
    {
        var have = Api(candidate);
        return [.. Api(reference).Where(k => !have.Contains(k)).OrderBy(k => k, StringComparer.Ordinal)];
    }

    private static HashSet<string> Api(string source)
    {
        var keys = new HashSet<string>(StringComparer.Ordinal);
        foreach (var node in CSharpSyntaxTree.ParseText(source).GetRoot().DescendantNodes())
        {
            if (node is BaseTypeDeclarationSyntax type && Visible(type))
                keys.Add(ChangeStubber.TypeChain(type));
            else if (ChangeStubber.Key(node) is { } key && Visible(node))
                keys.Add(key);
        }
        return keys;
    }

    private static bool Exposed(SyntaxTokenList modifiers) =>
        modifiers.Any(m => m.IsKind(SyntaxKind.PublicKeyword) || m.IsKind(SyntaxKind.ProtectedKeyword) || m.IsKind(SyntaxKind.InternalKeyword));

    private static bool Visible(SyntaxNode node)
    {
        var declaration = node is VariableDeclaratorSyntax ? node.Ancestors().OfType<BaseFieldDeclarationSyntax>().First() : (MemberDeclarationSyntax)node;
        var exposed = declaration is BaseTypeDeclarationSyntax { Parent: not TypeDeclarationSyntax }
            || declaration.Parent is InterfaceDeclarationSyntax
            || Exposed(declaration.Modifiers);
        return exposed && declaration.Ancestors().OfType<BaseTypeDeclarationSyntax>().All(t => Visible(t));
    }
}

public static class Program
{
    public static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "--self-test") return FixtureChecks.Run();
        if (args.Length == 3 && args[0] == "--missing-api")
        {
            Console.WriteLine(JsonSerializer.Serialize(new { missing = ApiChecker.Missing(File.ReadAllText(args[1]), File.ReadAllText(args[2])) }));
            return 0;
        }
        if (args.Length != 3)
        {
            Console.Error.WriteLine("Usage: HybridLens.ChangeStub <pre.cs> <post.cs> <output.cs> | --missing-api <reference.cs> <candidate.cs> | --self-test");
            return 2;
        }
        var result = ChangeStubber.Stub(File.ReadAllText(args[0]), File.ReadAllText(args[1]));
        File.WriteAllText(args[2], result.Text);
        Console.WriteLine(JsonSerializer.Serialize(new { stubbed = result.Stubbed, unstubbable = result.Unstubbable }));
        return 0;
    }
}
