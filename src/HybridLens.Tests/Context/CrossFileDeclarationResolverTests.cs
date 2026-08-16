using Basic.Reference.Assemblies;
using HybridLens.Core.Models;
using HybridLens.StaticAnalysis;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;

namespace HybridLens.Tests.Context;

/// <summary>
/// The resolver supplies the V2 ladder's Full rung. Its job is the one the sealed supplement kept
/// failing: when a target calls a deprecated API, the file declaring the replacement is one file
/// away and no context level ever supplied it, so the applier refused with "references NotifyApiV2,
/// but the source file only shows a deprecated method".
/// </summary>
public sealed class CrossFileDeclarationResolverTests : IDisposable
{
    private readonly string _root = Directory.CreateTempSubdirectory("xfile").FullName;

    public void Dispose()
    {
        try { Directory.Delete(_root, recursive: true); } catch { /* best effort */ }
    }

    private string Write(string relative, string source)
    {
        var path = Path.Combine(_root, relative.Replace('/', Path.DirectorySeparatorChar));
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, source);
        return path;
    }

    private static Compilation Compile(params (string Path, string Source)[] files) =>
        CSharpCompilation.Create(
            "TestAssembly",
            syntaxTrees: files.Select(f =>
                CSharpSyntaxTree.ParseText(f.Source, path: f.Path)).ToArray(),
            references: Net80.References.All,
            options: new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary));

    private static ContextLevelSpec Spec(int maxFiles = 8, int maxChars = 60_000) => new()
    {
        Level = ContextLevel.Full,
        CrossFile = CrossFileScope.ReferencedTypeDeclarations,
        MaxCrossFileFiles = maxFiles,
        MaxCrossFileChars = maxChars,
        OrderingRule = "ordinal by repository-relative path, then by declaring type name"
    };

    [Fact]
    public void ResolvesTheDeclaringFileOfAReferencedType_AndExcludesTheTargetsOwnFile()
    {
        var legacy = Write("src/Legacy/NotifyApi.cs", """
            namespace Demo.Legacy;
            public static class NotifyApiV1 { public static bool Send(string to) => true; }
            public static class NotifyApiV2 { public static bool Send(Notification n) => true; }
            public sealed class Notification { public string Recipient = ""; }
            """);
        var target = Write("src/Scheduler.cs", """
            using Demo.Legacy;
            namespace Demo;
            public class Scheduler
            {
                public bool Remind(string to)
                {
                    return NotifyApiV1.Send(to);
                }
            }
            """);

        var compilation = Compile(
            (legacy, File.ReadAllText(legacy)),
            (target, File.ReadAllText(target)));

        var result = CrossFileDeclarationResolver.Resolve(
            compilation, target, targetLine: 5, targetEndLine: 8, Spec(), _root);

        var included = Assert.Single(result.Included);
        Assert.Equal("src/Legacy/NotifyApi.cs", included.RelativePath);
        Assert.Contains("NotifyApiV1", included.DeclaredTypes);
        // The replacement travels with the deprecated member because they share a declaring file:
        // exactly the information the supplement's applier said it could not find.
        Assert.Contains("NotifyApiV2", included.Source);
        Assert.False(result.Truncated);
        Assert.Empty(result.Dropped);
    }

    [Fact]
    public void ReturnsNothing_WhenTheLevelDoesNotAskForCrossFileScope()
    {
        var target = Write("src/Solo.cs", "public class Solo { public int Go() => 1; }");
        var compilation = Compile((target, File.ReadAllText(target)));

        var result = CrossFileDeclarationResolver.Resolve(
            compilation, target, 1, 1,
            new ContextLevelSpec { Level = ContextLevel.Relational, CrossFile = CrossFileScope.None },
            _root);

        Assert.Empty(result.Included);
        Assert.False(result.Truncated);
    }

    [Fact]
    public void HonoursTheFileCap_AndRecordsWhatItDropped()
    {
        var a = Write("src/A.cs", "namespace Demo; public class Alpha { public int V => 1; }");
        var b = Write("src/B.cs", "namespace Demo; public class Beta { public int V => 2; }");
        var target = Write("src/Uses.cs", """
            namespace Demo;
            public class Uses
            {
                public int Go()
                {
                    return new Alpha().V + new Beta().V;
                }
            }
            """);

        var compilation = Compile(
            (a, File.ReadAllText(a)), (b, File.ReadAllText(b)), (target, File.ReadAllText(target)));

        var uncapped = CrossFileDeclarationResolver.Resolve(
            compilation, target, 4, 7, Spec(), _root);
        Assert.Equal(2, uncapped.Included.Count);

        var capped = CrossFileDeclarationResolver.Resolve(
            compilation, target, 4, 7, Spec(maxFiles: 1), _root);

        // Ordinal ordering by relative path makes the cap deterministic: A.cs is kept, B.cs dropped,
        // so a truncated payload is reproducible rather than dependent on syntax-walk order.
        Assert.Single(capped.Included);
        Assert.Equal("src/A.cs", capped.Included[0].RelativePath);
        Assert.True(capped.Truncated);
        Assert.Equal(["src/B.cs"], capped.Dropped);
    }

    [Fact]
    public void HonoursTheCharacterCap_BySkippingWholeFiles()
    {
        var big = Write("src/Big.cs",
            "namespace Demo; public class Big { public int V => 1; } // " + new string('x', 5_000));
        var target = Write("src/UsesBig.cs", """
            namespace Demo;
            public class UsesBig
            {
                public int Go() => new Big().V;
            }
            """);

        var compilation = Compile((big, File.ReadAllText(big)), (target, File.ReadAllText(target)));

        var result = CrossFileDeclarationResolver.Resolve(
            compilation, target, 3, 4, Spec(maxChars: 100), _root);

        // Half a source file is not compilable context, so a file that will not fit is skipped
        // entirely rather than truncated mid-way.
        Assert.Empty(result.Included);
        Assert.Equal(["src/Big.cs"], result.Dropped);
        Assert.True(result.Truncated);
    }

    [Fact]
    public void IgnoresReferencesOutsideTheTargetDeclaration()
    {
        var other = Write("src/Other.cs", "namespace Demo; public class Other { public int V => 1; }");
        var target = Write("src/Two.cs", """
            namespace Demo;
            public class Two
            {
                public int Inside() => 1;

                public int Outside() => new Other().V;
            }
            """);

        var compilation = Compile((other, File.ReadAllText(other)), (target, File.ReadAllText(target)));

        var insideOnly = CrossFileDeclarationResolver.Resolve(
            compilation, target, targetLine: 4, targetEndLine: 4, Spec(), _root);
        Assert.Empty(insideOnly.Included);

        var outside = CrossFileDeclarationResolver.Resolve(
            compilation, target, targetLine: 6, targetEndLine: 6, Spec(), _root);
        Assert.Single(outside.Included);
    }
}
