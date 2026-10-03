using System.Collections.Immutable;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using HybridLens.Core.Configuration;
using HybridLens.StaticAnalysis.Abstractions;
using HybridLens.StaticAnalysis.Detectors;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Text;

// Capture reads an evaluated compiler command; replay only reads content-addressed files.
// Detector implementations are copied verbatim into the frozen scanner by study.py.
static class Program
{
    static readonly JsonSerializerOptions Json = new() { WriteIndented = true };
    static string Hash(byte[] b) => Convert.ToHexString(SHA256.HashData(b)).ToLowerInvariant();
    static string HashFile(string p) => Hash(File.ReadAllBytes(p));
    static string Slash(string s) => s.Replace('\\', '/');
    static void Write(string p, object value) => File.WriteAllText(p, JsonSerializer.Serialize(value, Json) + "\n");
    static T Read<T>(string p) => JsonSerializer.Deserialize<T>(File.ReadAllText(p))!;
    static string Store(string original, string bundle)
    {
        var hash = HashFile(original);
        var dest = Path.Combine(bundle, "blobs", hash);
        if (!File.Exists(dest)) File.Copy(original, dest);
        return hash;
    }
    record Source(string Path, string Hash);
    record Reference(string Name, string Hash, string[] Aliases, bool EmbedInteropTypes);
    record Input(string[] Arguments, string BaseDirectory, Source[] Sources, Reference[] References,
        string ProtocolHash, string ScannerHash, string SnapshotLabel, string ScopePrefix);
    static CSharpCommandLineArguments Parse(string[] args, string baseDir) =>
        CSharpCommandLineParser.Default.Parse(args, baseDir, sdkDirectory: null);
    static void Capture(string rsp, string project, string repository, string bundle, string protocol, string scannerHash, string snapshotLabel, string scopePrefix)
    {
        Directory.CreateDirectory(Path.Combine(bundle, "blobs"));
        // WriteLinesToFile emits one already-tokenized argument per line. Keep quoted spaces intact.
        var args = File.ReadAllLines(rsp).Where(x => !string.IsNullOrWhiteSpace(x)).ToArray();
        var command = Parse(args, project);
        var errors = command.Errors.Where(d => d.Severity == DiagnosticSeverity.Error).ToArray();
        if (errors.Length != 0) throw new Exception(string.Join("\n", errors.Select(x => x.ToString())));
        var sources = command.SourceFiles.Select(f => {
            var path = Path.GetFullPath(f.Path, project);
            var relative = Slash(Path.GetRelativePath(repository, path));
            if (relative.StartsWith("../")) throw new Exception("Source outside captured repository: " + relative);
            return new Source(relative, Store(path, bundle));
        }).ToArray();
        var refs = command.MetadataReferences.Select(r => {
            var path = Path.GetFullPath(r.Reference, project);
            return new Reference(Path.GetFileName(path), Store(path, bundle), r.Properties.Aliases.ToArray(), r.Properties.EmbedInteropTypes);
        }).ToArray();
        File.Copy(protocol, Path.Combine(bundle, "protocol.json"), true);
        Write(Path.Combine(bundle, "input.json"), new Input(args, project, sources, refs, HashFile(protocol), scannerHash, snapshotLabel, Slash(scopePrefix)));
    }
    static void Replay(string bundle, string output, string expectedScannerHash)
    {
        var input = Read<Input>(Path.Combine(bundle, "input.json"));
        if (input.ScannerHash != expectedScannerHash) throw new Exception("Frozen scanner identity mismatch");
        var protocolPath = Path.Combine(bundle, "protocol.json");
        if (HashFile(protocolPath) != input.ProtocolHash) throw new Exception("Protocol checksum mismatch");
        var protocol = JsonNode.Parse(File.ReadAllText(protocolPath))!;
        byte[] Blob(string hash) {
            var bytes = File.ReadAllBytes(Path.Combine(bundle, "blobs", hash));
            if (Hash(bytes) != hash) throw new Exception("Input checksum mismatch: " + hash);
            return bytes;
        }
        string Text(string hash) {
            using var stream = new MemoryStream(Blob(hash));
            using var reader = new StreamReader(stream, Encoding.UTF8, true);
            return reader.ReadToEnd();
        }
        var cmd = Parse(input.Arguments, input.BaseDirectory);
        var parseErrors = cmd.Errors.Where(x => x.Severity == DiagnosticSeverity.Error).ToArray();
        if (parseErrors.Length != 0) throw new Exception("Archived command is invalid");
        var texts = input.Sources.ToDictionary(x => x.Path, x => Text(x.Hash));
        var trees = input.Sources.Select(s => CSharpSyntaxTree.ParseText(SourceText.From(texts[s.Path], Encoding.UTF8), cmd.ParseOptions, s.Path)).ToArray();
        var references = input.References.Select(r => MetadataReference.CreateFromImage(Blob(r.Hash),
            new MetadataReferenceProperties(MetadataImageKind.Assembly, r.Aliases.ToImmutableArray(), r.EmbedInteropTypes))).ToArray();
        var compilation = CSharpCompilation.Create("Newtonsoft.Json", trees, references, cmd.CompilationOptions);
        var errors = compilation.GetDiagnostics().Where(d => d.Severity == DiagnosticSeverity.Error)
            .Select(d => new { id = d.Id, message = d.GetMessage(System.Globalization.CultureInfo.InvariantCulture),
                file = d.Location.SourceTree?.FilePath, start = d.Location.IsInSource ? d.Location.SourceSpan.Start : -1 })
            .OrderBy(d => d.file, StringComparer.Ordinal).ThenBy(d => d.start).ThenBy(d => d.id, StringComparer.Ordinal).ToArray();
        var scope = protocol["scope"]!;
        string? Excluded(string path) {
            if (!path.StartsWith(input.ScopePrefix, StringComparison.Ordinal)) return "outside production prefix";
            var relative = path[input.ScopePrefix.Length..];
            if (scope["exclude_paths"]!.AsArray().Any(p => ("/" + relative).Contains("/" + p!.GetValue<string>(), StringComparison.OrdinalIgnoreCase))) return "build output";
            if (scope["exclude_generated_filename_suffixes"]!.AsArray().Any(p => path.EndsWith(p!.GetValue<string>(), StringComparison.OrdinalIgnoreCase))) return "generated filename";
            var header = texts[path][..Math.Min(texts[path].Length, scope["generated_header_scan_characters"]!.GetValue<int>())];
            if (scope["exclude_generated_header_markers"]!.AsArray().Any(p => header.Contains(p!.GetValue<string>(), StringComparison.OrdinalIgnoreCase))) return "generated header";
            return null;
        }
        var eligible = trees.Where(t => Excluded(t.FilePath) == null).ToArray();
        var eligiblePaths = eligible.Select(t => t.FilePath).ToHashSet(StringComparer.Ordinal);
        var config = protocol["detectors"]!.Deserialize<DetectorConfig>()!;
        IDetector[] detectors = [new GodClassDetector(config.GodClass), new LongMethodDetector(config.LongMethod), new ObsoleteApiDetector(config.ObsoleteApi)];
        var findings = detectors.SelectMany(d => d.Detect(compilation)).Where(f => eligiblePaths.Contains(f.FilePath))
            .Select(f => new { type = f.Type.ToString(), severity = f.Severity.ToString(), file = f.FilePath,
                symbol = f.SymbolName, line = f.Line, snippet_sha256 = Hash(Encoding.UTF8.GetBytes(f.Snippet ?? "")),
                metrics = new SortedDictionary<string, double>(f.Metrics.ToDictionary(x => x.Key, x => x.Value), StringComparer.Ordinal) })
            .OrderBy(f => f.type, StringComparer.Ordinal).ThenBy(f => f.file, StringComparer.Ordinal).ThenBy(f => f.line)
            .ThenBy(f => f.symbol, StringComparer.Ordinal).ThenBy(f => f.snippet_sha256, StringComparer.Ordinal).ToArray();
        var classes = eligible.Sum(t => t.GetRoot().DescendantNodes().OfType<ClassDeclarationSyntax>().Count());
        var methods = eligible.Sum(t => t.GetRoot().DescendantNodes().OfType<MethodDeclarationSyntax>().Count());
        var counts = detectors.ToDictionary(d => d.Type.ToString(), d => findings.Count(f => f.type == d.Type.ToString()));
        var obsoleteFiles = findings.Where(f => f.type == "ObsoleteApiUsage").Select(f => f.file).Distinct().Count();
        double? Rate(int n, int denominator) => denominator == 0 ? null : (double)n / denominator;
        string NormalizeArg(string arg) {
            var s = Slash(arg).Replace(Slash(Path.GetFullPath(Path.Combine(input.BaseDirectory, "../.."))), "<repository>", StringComparison.OrdinalIgnoreCase);
            foreach (var r in cmd.MetadataReferences.Zip(input.References)) s = s.Replace(Slash(r.First.Reference), "<reference:" + r.Second.Hash + ">", StringComparison.OrdinalIgnoreCase);
            // Independent extraction roots differ physically but carry the same PathMap semantics.
            if (s.StartsWith("/pathmap:", StringComparison.OrdinalIgnoreCase) && s.Contains('='))
                s = "/pathmap:<source-root>=" + s[(s.IndexOf('=') + 1)..];
            return s;
        }
        Write(output, new {
            schema_version = "1.0", status = errors.Length != 0 ? "partial" : eligible.Length == 0 ? "not_applicable" : "complete",
            protocol_sha256 = input.ProtocolHash, scanner_sha256 = input.ScannerHash,
            sources = input.Sources.OrderBy(s => s.Path, StringComparer.Ordinal),
            references = input.References.OrderBy(r => r.Name, StringComparer.Ordinal).ThenBy(r => r.Hash, StringComparer.Ordinal),
            compiler = new { arguments = input.Arguments.Select(NormalizeArg).ToArray(),
                language = cmd.ParseOptions.LanguageVersion.ToString(), defines = cmd.ParseOptions.PreprocessorSymbolNames.Order(StringComparer.Ordinal).ToArray(),
                target = cmd.CompilationOptions.OutputKind.ToString(), optimization = cmd.CompilationOptions.OptimizationLevel.ToString() },
            excluded = trees.Where(t => !eligiblePaths.Contains(t.FilePath)).Select(t => new { file = t.FilePath, reason = Excluded(t.FilePath) }).OrderBy(x => x.file, StringComparer.Ordinal),
            denominators = new { files = eligible.Length, class_declarations = classes, method_declarations = methods,
                physical_lines = eligible.Sum(t => { var s = texts[t.FilePath]; return s.Length == 0 ? 0 : s.Count(c => c == '\n') + (s.EndsWith('\n') ? 0 : 1); }) },
            counts, obsolete_affected_files = obsoleteFiles,
            rates = new { god_class = Rate(counts["GodClass"], classes), long_method = Rate(counts["LongMethod"], methods), obsolete_affected_files = Rate(obsoleteFiles, eligible.Length) },
            compilation_errors = errors, findings
        });
    }
    static int Main(string[] args)
    {
        try {
            if (args[0] == "capture") Capture(args[1], args[2], args[3], args[4], args[5], args[6], args[7], args[8]);
            else if (args[0] == "replay") Replay(args[1], args[2], args[3]);
            else throw new ArgumentException("Expected capture or replay");
            return 0;
        } catch (Exception ex) { Console.Error.WriteLine(ex.ToString()); return 1; }
    }
}
