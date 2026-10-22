using System.Xml.Linq;
using Basic.Reference.Assemblies;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;

namespace HybridLens.DesignQuality;

/// <summary>Deliberately narrow adapter for the pinned, independent .NET 8 corpus projects.</summary>
public static class CorpusCompiler
{
    public static readonly CSharpParseOptions ParseOptions = new(LanguageVersion.CSharp12,
        preprocessorSymbols: ["TRACE", "DEBUG", "NET", "NET8_0", "NETCOREAPP", "NET5_0_OR_GREATER",
            "NET6_0_OR_GREATER", "NET7_0_OR_GREATER", "NET8_0_OR_GREATER", "NETCOREAPP1_0_OR_GREATER",
            "NETCOREAPP1_1_OR_GREATER", "NETCOREAPP2_0_OR_GREATER", "NETCOREAPP2_1_OR_GREATER",
            "NETCOREAPP2_2_OR_GREATER", "NETCOREAPP3_0_OR_GREATER", "NETCOREAPP3_1_OR_GREATER"]);
    private const string GlobalUsings = "global using System; global using System.Collections.Generic; global using System.IO; global using System.Linq; global using System.Net.Http; global using System.Threading; global using System.Threading.Tasks;";

    public static CSharpCompilation FromSources(IEnumerable<SyntaxTree> trees, string name = "Fixture") =>
        CSharpCompilation.Create(name, trees.Append(CSharpSyntaxTree.ParseText(GlobalUsings, ParseOptions, "__ImplicitUsings.g.cs")),
            Net80.References.All, new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary,
                nullableContextOptions: NullableContextOptions.Enable, optimizationLevel: OptimizationLevel.Debug));

    public static CSharpCompilation Load(string project)
    {
        var xml = XDocument.Load(project);
        var root = xml.Root ?? throw new InvalidDataException("Missing project XML root");
        var allowed = new Dictionary<string, string> { ["TargetFramework"] = "net8.0", ["ImplicitUsings"] = "enable", ["Nullable"] = "enable", ["LangVersion"] = "12.0" };
        if ((string?)root.Attribute("Sdk") != "Microsoft.NET.Sdk" || root.Attributes().Count() != 1 ||
            root.Elements().Any(e => e.Name != "PropertyGroup" || e.HasAttributes) ||
            root.Elements().SelectMany(e => e.Elements()).Count() != allowed.Count ||
            !root.Elements().SelectMany(e => e.Elements()).Select(e => e.Name.LocalName).ToHashSet().SetEquals(allowed.Keys) ||
            root.Elements().SelectMany(e => e.Elements()).Any(e => e.HasAttributes || !allowed.TryGetValue(e.Name.LocalName, out var value) || e.Value != value))
            throw new InvalidDataException($"Unsupported project settings: {project}; use a real workspace adapter for other projects.");
        var dir = Path.GetDirectoryName(project)!;
        var files = Directory.GetFiles(dir, "*.cs", SearchOption.AllDirectories)
            .Where(p => !p.Split(Path.DirectorySeparatorChar).Any(c => c is "bin" or "obj")).Order().ToArray();
        var trees = files.Select(p => CSharpSyntaxTree.ParseText(File.ReadAllText(p), ParseOptions, p));
        var compilation = FromSources(trees, Path.GetFileNameWithoutExtension(project));
        var errors = compilation.GetDiagnostics().Where(d => d.Severity == DiagnosticSeverity.Error).ToArray();
        if (errors.Length > 0) throw new InvalidDataException($"Baseline compilation failed: {project}\n{string.Join("\n", errors.Select(e => e.ToString()))}");
        return compilation;
    }
}
