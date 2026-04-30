using Basic.Reference.Assemblies;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;

namespace HybridLens.Tests.Helpers;

/// <summary>
/// Factory helpers that produce in-memory Roslyn compilations for detector unit tests.
/// No MSBuild, no disk I/O — just syntax trees plus optional reference assemblies.
/// </summary>
internal static class CompilationHelper
{
    /// <summary>
    /// Syntax-only compilation — enough for LongMethodDetector and GodClassDetector
    /// which operate purely on syntax trees without a semantic model.
    /// </summary>
    public static Compilation CreateSyntaxOnly(string code, string fileName = "Test.cs")
    {
        var tree = CSharpSyntaxTree.ParseText(code, path: fileName);

        return CSharpCompilation.Create(
            "TestAssembly",
            syntaxTrees: [tree],
            references: [],
            options: new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary));
    }

    /// <summary>
    /// Full compilation with .NET 8 reference assemblies — needed for
    /// ObsoleteApiDetector which resolves symbols via the semantic model.
    /// </summary>
    public static Compilation CreateWithReferences(string code, string fileName = "Test.cs")
    {
        var tree = CSharpSyntaxTree.ParseText(code, path: fileName);

        return CSharpCompilation.Create(
            "TestAssembly",
            syntaxTrees: [tree],
            references: Net80.References.All,
            options: new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary));
    }
}
