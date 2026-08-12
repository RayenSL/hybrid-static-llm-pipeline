using System.Text;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace HybridLens.ContextBuilder;

/// <summary>
/// Builds a deterministic, diagnosis-blind slice of project-local types named by the target file.
/// Only relevant type declarations and their externally accessible members are shown.
/// </summary>
public static class NeutralDependencyContextBuilder
{
    private const int MaximumTypes = 16;
    private const int MaximumCharacters = 30_000;

    public static async Task<string> BuildAsync(
        string targetSourceFile,
        string projectFile,
        string targetSource,
        CancellationToken cancellationToken)
    {
        var projectDirectory = Path.GetDirectoryName(Path.GetFullPath(projectFile))!;
        var targetFull = Path.GetFullPath(targetSourceFile);
        var referencedNames = IdentifierNames(targetSource);
        var candidates = new List<(string Path, BaseTypeDeclarationSyntax Type)>();

        foreach (var path in Directory.EnumerateFiles(projectDirectory, "*.cs", SearchOption.AllDirectories)
                     .Where(path => !IsBuildOutput(path, projectDirectory))
                     .Where(path => !Path.GetFullPath(path).Equals(targetFull, StringComparison.OrdinalIgnoreCase))
                     .OrderBy(path => path, StringComparer.OrdinalIgnoreCase))
        {
            cancellationToken.ThrowIfCancellationRequested();
            var source = await File.ReadAllTextAsync(path, cancellationToken);
            var root = CSharpSyntaxTree.ParseText(source, cancellationToken: cancellationToken).GetRoot(cancellationToken);
            candidates.AddRange(root.DescendantNodes().OfType<BaseTypeDeclarationSyntax>()
                .Where(type => type.Parent is not BaseTypeDeclarationSyntax)
                .Where(type => type.Modifiers.Any(modifier => modifier.IsKind(SyntaxKind.PublicKeyword)))
                .Select(type => (path, type)));
        }

        var selected = new List<(string Path, BaseTypeDeclarationSyntax Type)>();
        var selectedNames = new HashSet<string>(StringComparer.Ordinal);
        while (selected.Count < MaximumTypes)
        {
            var added = false;
            foreach (var candidate in candidates)
            {
                var name = candidate.Type.Identifier.ValueText;
                if (selectedNames.Contains(name) || !referencedNames.Contains(name)) continue;
                selected.Add(candidate);
                selectedNames.Add(name);
                foreach (var identifier in candidate.Type.DescendantTokens()
                             .Where(token => token.IsKind(SyntaxKind.IdentifierToken)))
                    referencedNames.Add(identifier.ValueText);
                added = true;
                if (selected.Count == MaximumTypes) break;
            }
            if (!added) break;
        }

        if (selected.Count == 0)
            return "No project-local public dependencies were referenced by the target file.";

        var output = new StringBuilder();
        foreach (var group in selected.GroupBy(item => item.Path, StringComparer.OrdinalIgnoreCase))
        {
            var relative = Path.GetRelativePath(projectDirectory, group.Key).Replace('\\', '/');
            output.AppendLine($"### {relative}");
            output.AppendLine("```csharp");
            foreach (var (_, type) in group)
            {
                output.AppendLine(RenderPublicSurface(type));
                output.AppendLine();
                if (output.Length >= MaximumCharacters) break;
            }
            output.AppendLine("```");
            if (output.Length >= MaximumCharacters) break;
        }
        return output.ToString(0, Math.Min(output.Length, MaximumCharacters)).TrimEnd();
    }

    private static HashSet<string> IdentifierNames(string source)
    {
        var root = CSharpSyntaxTree.ParseText(source).GetRoot();
        return root.DescendantTokens()
            .Where(token => token.IsKind(SyntaxKind.IdentifierToken))
            .Select(token => token.ValueText)
            .ToHashSet(StringComparer.Ordinal);
    }

    private static string RenderPublicSurface(BaseTypeDeclarationSyntax type)
    {
        if (type is EnumDeclarationSyntax enumeration)
            return NamespacePrefix(type) + enumeration.NormalizeWhitespace().ToFullString();

        var header = type switch
        {
            RecordDeclarationSyntax record => record.WithMembers(default).WithOpenBraceToken(default)
                .WithCloseBraceToken(default).WithSemicolonToken(default).NormalizeWhitespace().ToFullString(),
            TypeDeclarationSyntax declaration => declaration.WithMembers(default).WithOpenBraceToken(default)
                .WithCloseBraceToken(default).WithSemicolonToken(default).NormalizeWhitespace().ToFullString(),
            _ => type.Identifier.ValueText
        };
        var brace = header.IndexOf('{');
        if (brace >= 0) header = header[..brace].TrimEnd();
        header = header.TrimEnd(';', ' ');

        var members = (type as TypeDeclarationSyntax)?.Members
            ?? [];
        var renderedMembers = members
            .Where(IsExternallyAccessible)
            .Select(member => member.NormalizeWhitespace().ToFullString())
            .ToList();
        return NamespacePrefix(type) + header + "\n{\n" +
               string.Join("\n\n", renderedMembers.Select(Indent)) + "\n}";
    }

    private static bool IsExternallyAccessible(MemberDeclarationSyntax member)
    {
        if (member.Parent is InterfaceDeclarationSyntax) return true;
        return member.Modifiers.Any(modifier => modifier.IsKind(SyntaxKind.PublicKeyword) ||
                                                modifier.IsKind(SyntaxKind.ProtectedKeyword));
    }

    private static string NamespacePrefix(SyntaxNode node)
    {
        var ns = node.Ancestors().OfType<BaseNamespaceDeclarationSyntax>().FirstOrDefault();
        return ns is null ? string.Empty : $"namespace {ns.Name};\n";
    }

    private static string Indent(string value) =>
        string.Join("\n", value.Split('\n').Select(line => "    " + line));

    private static bool IsBuildOutput(string path, string projectDirectory)
    {
        var relative = Path.GetRelativePath(projectDirectory, path).Replace('\\', '/');
        return relative.StartsWith("bin/", StringComparison.OrdinalIgnoreCase) ||
               relative.StartsWith("obj/", StringComparison.OrdinalIgnoreCase) ||
               relative.Contains("/bin/", StringComparison.OrdinalIgnoreCase) ||
               relative.Contains("/obj/", StringComparison.OrdinalIgnoreCase);
    }
}
