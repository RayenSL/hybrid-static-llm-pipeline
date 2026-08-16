using System.Security.Cryptography;
using System.Text;
using HybridLens.Core.Models;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace HybridLens.StaticAnalysis;

/// <summary>
/// Resolves the declaring source of every external type a target references, which is the payload
/// the V2 ladder's Full rung supplies (§4.4.3).
///
/// The sealed supplement's applier repeatedly refused Obsolete API repairs with reasons of the form
/// "references NotifyApiV2, but the source file only shows a deprecated method". The replacement
/// existed the whole time, one file away, and no context level ever supplied it. This resolver is
/// what closes that gap: for an Obsolete API target it returns the Legacy file declaring both the
/// deprecated member and its successor, and for a refactoring target it returns the collaborator
/// types the method operates on.
///
/// Resolution runs once during preflight and its result is frozen into the campaign manifest, so
/// prompts stay reproducible from the manifest alone and the supplied source is provably older than
/// every repair. The cap is load-bearing rather than defensive: on an industrial solution the p90
/// dependency payload runs to six figures of characters, well past any prompt budget, so what was
/// dropped is recorded and reported as an experimental outcome.
/// </summary>
public static class CrossFileDeclarationResolver
{
    /// <summary>
    /// Resolves cross-file declarations for one target declaration.
    /// </summary>
    /// <param name="compilation">The compilation holding the target.</param>
    /// <param name="targetFilePath">Absolute path of the target's own file, which is never returned.</param>
    /// <param name="targetLine">1-based line of the target declaration.</param>
    /// <param name="targetEndLine">1-based last line of the target declaration.</param>
    /// <param name="spec">Supplies the cap and the ordering rule.</param>
    /// <param name="solutionRoot">Root that returned paths are made relative to.</param>
    public static CrossFileResolution Resolve(
        Compilation compilation,
        string targetFilePath,
        int targetLine,
        int targetEndLine,
        ContextLevelSpec spec,
        string solutionRoot)
    {
        if (spec.CrossFile != CrossFileScope.ReferencedTypeDeclarations)
            return CrossFileResolution.Empty;

        var targetFull = Path.GetFullPath(targetFilePath);
        var tree = compilation.SyntaxTrees.FirstOrDefault(
            t => string.Equals(Path.GetFullPath(t.FilePath), targetFull, StringComparison.OrdinalIgnoreCase));
        if (tree is null) return CrossFileResolution.Empty;

        var model = compilation.GetSemanticModel(tree);
        var root = tree.GetRoot();

        // Types declared by files, keyed by the declaring file. A file is the unit because the
        // prompt supplies whole files: a partial extract would not compile if the model reused it.
        var byFile = new SortedDictionary<string, SortedSet<string>>(StringComparer.Ordinal);

        foreach (var node in NodesInRange(root, tree, targetLine, targetEndLine))
        {
            // Ambiguous binding leaves Symbol null with CandidateSymbols populated; the detectors
            // use the same fallback, which matters on partially-compiling industrial workspaces.
            var info = model.GetSymbolInfo(node);
            var symbol = info.Symbol ?? info.CandidateSymbols.FirstOrDefault();
            if (symbol is null) continue;

            var type = symbol as INamedTypeSymbol ?? symbol.ContainingType;
            if (type is null) continue;
            if (type.TypeKind is TypeKind.Error or TypeKind.Dynamic) continue;

            foreach (var reference in type.DeclaringSyntaxReferences)
            {
                var path = reference.SyntaxTree.FilePath;
                if (string.IsNullOrEmpty(path)) continue;

                var full = Path.GetFullPath(path);
                // The target's own file is already supplied in full by every prompt.
                if (string.Equals(full, targetFull, StringComparison.OrdinalIgnoreCase)) continue;
                if (!File.Exists(full)) continue;

                if (!byFile.TryGetValue(full, out var declared))
                    byFile[full] = declared = new SortedSet<string>(StringComparer.Ordinal);
                declared.Add(type.Name);
            }
        }

        // Ordinal by repository-relative path, then by declaring type name: a total order that does
        // not depend on syntax-walk order, so the same target always yields the same payload and the
        // same files are dropped when the cap bites.
        var ordered = byFile
            .Select(kv => (Full: kv.Key, Relative: Relative(kv.Key, solutionRoot), Types: kv.Value))
            .OrderBy(x => x.Relative, StringComparer.Ordinal)
            .ThenBy(x => string.Join(",", x.Types), StringComparer.Ordinal)
            .ToList();

        var included = new List<CrossFileDeclaration>();
        var dropped = new List<string>();
        var chars = 0;

        foreach (var candidate in ordered)
        {
            if (included.Count >= spec.MaxCrossFileFiles)
            {
                dropped.Add(candidate.Relative);
                continue;
            }

            string source;
            try { source = File.ReadAllText(candidate.Full); }
            catch (IOException) { dropped.Add(candidate.Relative); continue; }
            catch (UnauthorizedAccessException) { dropped.Add(candidate.Relative); continue; }

            if (chars + source.Length > spec.MaxCrossFileChars)
            {
                // Skipped rather than truncated mid-file: half a source file is not compilable
                // context and would make the prompt misleading rather than merely smaller.
                dropped.Add(candidate.Relative);
                continue;
            }

            chars += source.Length;
            included.Add(new CrossFileDeclaration
            {
                RelativePath = candidate.Relative,
                DeclaredTypes = [.. candidate.Types],
                Source = source,
                Sha256 = Sha256(source)
            });
        }

        return new CrossFileResolution { Included = included, Dropped = dropped };
    }

    /// <summary>
    /// Symbol-referencing nodes inside the target declaration's line span. The span is used rather
    /// than the declaration syntax so the caller can supply detector coordinates directly, which is
    /// what the manifest already carries.
    /// </summary>
    private static IEnumerable<SyntaxNode> NodesInRange(
        SyntaxNode root, SyntaxTree tree, int startLine, int endLine)
    {
        foreach (var node in root.DescendantNodes())
        {
            if (node is not (IdentifierNameSyntax or MemberAccessExpressionSyntax
                or ObjectCreationExpressionSyntax or InvocationExpressionSyntax
                or GenericNameSyntax or QualifiedNameSyntax))
                continue;

            var line = tree.GetLineSpan(node.Span).StartLinePosition.Line + 1;
            if (line < startLine || line > endLine) continue;
            yield return node;
        }
    }

    private static string Relative(string full, string solutionRoot)
    {
        if (string.IsNullOrEmpty(solutionRoot)) return full.Replace('\\', '/');
        var relative = Path.GetRelativePath(solutionRoot, full);
        return relative.StartsWith("..", StringComparison.Ordinal) || Path.IsPathRooted(relative)
            ? full.Replace('\\', '/')
            : relative.Replace('\\', '/');
    }

    private static string Sha256(string value) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
}
