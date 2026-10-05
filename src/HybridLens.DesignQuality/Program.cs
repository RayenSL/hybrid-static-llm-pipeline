using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using HybridLens.Core.Configuration;
using HybridLens.StaticAnalysis.Detectors;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;

namespace HybridLens.DesignQuality;

public static class Program
{
    private static readonly JsonSerializerOptions JsonOptions = new() { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
    private static string Hash(byte[] bytes) => Convert.ToHexStringLower(SHA256.HashData(bytes));
    private static string Str(JsonElement el, string key) => el.GetProperty(key).GetString()!;

    private static object[] Findings(Compilation compilation, string corpusRoot) =>
        new LongMethodDetector(new LongMethodConfig()).Detect(compilation)
            .Concat(new GodClassDetector(new GodClassConfig()).Detect(compilation))
            .Select(f => (object)new { type = f.Type.ToString(), file = Path.GetRelativePath(corpusRoot, f.FilePath).Replace('\\', '/'),
                symbol = f.SymbolName, line = f.Line, metrics = f.Metrics }).ToArray();

    public static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "--self-test") return FixtureChecks.Run();
        if (args.Length == 2 && args[0] == "--file-metrics")
        {
            var metrics = Directory.GetFiles(args[1], "*.cs").Order(StringComparer.Ordinal)
                .ToDictionary(Path.GetFileNameWithoutExtension, f => FileMetrics.Measure(File.ReadAllText(f)));
            Console.WriteLine(JsonSerializer.Serialize(metrics, JsonOptions));
            return 0;
        }
        if (args.Length != 2)
        {
            Console.Error.WriteLine("Usage: HybridLens.DesignQuality <manifest.json> <output.jsonl> | --self-test");
            return 2;
        }
        var manifestPath = Path.GetFullPath(args[0]);
        var directory = Path.GetDirectoryName(manifestPath)!;
        using var manifest = JsonDocument.Parse(File.ReadAllBytes(manifestPath));
        var corpus = Path.Combine(directory, "baseline", "corpus");
        // Recheck every exported baseline byte and reject stale extra source/project inputs.
        var declared = manifest.RootElement.GetProperty("baseline_files").EnumerateObject().ToDictionary(p => p.Name.Replace('/', Path.DirectorySeparatorChar), p => p.Value.GetString()!);
        foreach (var (path, expected) in declared)
            if (Hash(File.ReadAllBytes(Path.Combine(directory, "baseline", path))) != expected)
                throw new InvalidDataException($"Baseline hash mismatch: {path}");
        var actual = Directory.GetFiles(corpus, "*", SearchOption.AllDirectories)
            .Where(p => p.EndsWith(".cs") || p.EndsWith(".csproj") || Path.GetFileName(p).StartsWith("Directory.Build."))
            .Select(p => Path.GetRelativePath(Path.Combine(directory, "baseline"), p)).ToArray();
        if (actual.Any(p => !declared.ContainsKey(p))) throw new InvalidDataException("Untracked compilation input in reconstructed baseline");
        if (actual.Any(p => Path.GetFileName(p).StartsWith("Directory.Build."))) throw new InvalidDataException("Directory.Build overrides require full workspace adapter");
        var projects = Directory.GetFiles(corpus, "*.csproj", SearchOption.AllDirectories).Order().ToArray();
        var compilations = projects.ToDictionary(p => p, CorpusCompiler.Load);
        var baselineFindings = compilations.ToDictionary(k => k.Key, k => Findings(k.Value, corpus));
        var baselineFacts = new Dictionary<string, FileFacts>();
        var outputPath = Path.GetFullPath(args[1]);
        Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
        var temporary = outputPath + ".partial";
        using (var writer = new StreamWriter(temporary, false, new UTF8Encoding(false)))
        {
            var count = 0;
            foreach (var state in manifest.RootElement.GetProperty("states").EnumerateArray())
            {
                var baselinePath = Path.GetFullPath(Path.Combine(directory, Str(state, "baseline_path")));
                var project = projects.Single(p => baselinePath.StartsWith(Path.GetDirectoryName(p)! + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase));
                var original = compilations[project];
                var beforeTree = original.SyntaxTrees.Single(t => t.FilePath == baselinePath);
                var bytes = File.ReadAllBytes(Path.Combine(directory, Str(state, "final_path")));
                if (Hash(bytes) != Str(state, "source_sha256")) throw new InvalidDataException("Final source hash mismatch");
                var afterTree = CSharpSyntaxTree.ParseText(Encoding.UTF8.GetString(bytes), CorpusCompiler.ParseOptions, baselinePath);
                var repaired = original.ReplaceSyntaxTree(beforeTree, afterTree);
                if (!baselineFacts.TryGetValue(baselinePath, out var before))
                    baselineFacts[baselinePath] = before = StructuralFacts.Measure(original, beforeTree);
                var after = StructuralFacts.Measure(repaired, afterTree);
                var solutionBefore = baselineFindings.Values.SelectMany(v => v).ToArray();
                object[]? solutionAfter = after.Status == "measured"
                    ? baselineFindings.Where(p => p.Key != project).SelectMany(p => p.Value).Concat(Findings(repaired, corpus)).ToArray() : null;
                var result = new { schema_version = "repair-design-facts/0.1", measurement_key = Str(state, "measurement_key"),
                    target_id = Str(state, "target_id"), relative_file = Str(state, "relative_file"),
                    before, after, lineage = Lineage.Compare(before, after, Str(state, "symbol_name"), Str(state, "anti_pattern_type")),
                    solution_findings_before = solutionBefore, solution_findings_after = solutionAfter,
                    primary_descendant_endpoint = (bool?)null,
                    primary_endpoint_status = "requires_lineage_adjudication" };
                writer.WriteLine(JsonSerializer.Serialize(result, JsonOptions));
                if (++count % 50 == 0) { writer.Flush(); Console.WriteLine($"Measured {count} states"); }
            }
        }
        File.Move(temporary, outputPath, true);
        File.WriteAllText(outputPath + ".provenance.json", JsonSerializer.Serialize(new {
            schema_version = "repair-design-run/0.1", manifest_sha256 = Hash(File.ReadAllBytes(manifestPath)),
            output_sha256 = Hash(File.ReadAllBytes(outputPath)),
            executable_sha256 = Hash(File.ReadAllBytes(typeof(Program).Assembly.Location)),
            structural_metrics_sha256 = Hash(File.ReadAllBytes(typeof(HybridLens.StaticAnalysis.Metrics.ClassMetrics).Assembly.Location)),
            roslyn_version = typeof(CSharpCompilation).Assembly.GetName().Version?.ToString(),
            adapter = "independent-net8-corpus-projects/0.1", language = "CSharp12", reference_assemblies = "Basic.Reference.Assemblies.Net80/1.7.9",
            expected_projects = projects.Length, loaded_projects = compilations.Count,
            source_trees = compilations.Values.Sum(c => c.SyntaxTrees.Count(t => t.FilePath != "__ImplicitUsings.g.cs")),
            projects = projects.Select(p => Path.GetRelativePath(corpus, p).Replace('\\', '/')).ToArray()
        }, new JsonSerializerOptions(JsonOptions) { WriteIndented = true }));
        Console.WriteLine($"Saved {outputPath}");
        return 0;
    }
}
