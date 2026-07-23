using System.CommandLine;
using System.Text.Json;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;
using HybridLens.Pipeline;
using Microsoft.Extensions.DependencyInjection;

namespace HybridLens.CLI.Commands;

/// <summary>
/// The agentic architecture arm (§4.4.1, Appendix E prompt v2.0.0). Reads a normal analyzer
/// run trace, derives the distinct source files of the known instances, and runs an
/// autonomous detect-and-repair loop over each whole file: the agent edits the source and invokes
/// the compiler (its only tool) until it declares completion or the iteration budget is exhausted.
/// Self-detections are matched back to the known instances for recall/precision, and the agent's
/// FINAL edited solution is scored directly for verified-repair (build gate → detector re-run; no
/// separate applier). Both arms thus stay ungrounded — the detector is never exposed.
/// </summary>
public static class AgenticCommand
{
    public static Command Build(IServiceProvider services)
    {
        var fromOption = new Option<FileInfo>("--from")
        {
            Description = "Analyzer run JSONL supplying the files and known instances.",
            Required = true
        };

        var targetOption = new Option<FileInfo>("--target")
        {
            Description = "The corpus solution (Corpus.sln). Required — the agent builds a working copy of it as its only tool.",
            Required = true
        };

        var modelOption = new Option<string>("--model")
        {
            Description = "Frontier model key from Llm.Models (default: gpt-5.4)."
        };

        var runsOption = new Option<int>("--runs")
        {
            Description = "Trajectories per file (default: 3)."
        };

        var budgetOption = new Option<int>("--budget")
        {
            Description = "Frozen iteration budget — max edit→build attempts per trajectory (default: 6)."
        };

        var sweepOption = new Option<bool>("--sweep-corpus")
        {
            Description = "Run the agent over EVERY .cs under --target (incl. clean/distractor files) so detections " +
                          "on non-instances are scoreable as spurious (fuller precision). Default: only files holding a seeded instance."
        };

        var maxTokenGuardOption = new Option<int>("--max-input-tokens")
        {
            Description = "Heuristic token cap; files estimated above this are flagged context_truncated (default: 120000)."
        };

        var buildTimeoutOption = new Option<int>("--build-timeout")
        {
            Description = "Per-build dotnet build timeout in seconds (default: 180)."
        };

        var qualityDiffOption = new Option<bool>("--quality-diff")
        {
            Description = "Also measure whole-solution quality impact of each trajectory's FINAL built state " +
                          "(Layer 1 detectors + Layer 2 CA analyzers, before→after). Adds one dedicated analyzer " +
                          "build per trajectory; the agent's iteration builds stay analyzer-free."
        };

        var command = new Command("agentic",
            "Run the ungrounded agentic arm (H1b): an autonomous detect-and-repair loop with the compiler as its only tool.")
        {
            fromOption, targetOption, modelOption, runsOption, budgetOption, sweepOption, maxTokenGuardOption, buildTimeoutOption, qualityDiffOption
        };

        command.SetAction(async (parseResult, cancellationToken) =>
        {
            var from          = parseResult.GetValue(fromOption)!;
            var target        = parseResult.GetValue(targetOption)!;
            var model         = parseResult.GetValue(modelOption) is { Length: > 0 } m ? m : "gpt-5.4";
            var runs          = parseResult.GetValue(runsOption);
            if (runs < 1) runs = 3;
            var budget        = parseResult.GetValue(budgetOption);
            if (budget < 1) budget = 6;
            var sweepCorpus   = parseResult.GetValue(sweepOption);
            var maxTokenGuard = parseResult.GetValue(maxTokenGuardOption);
            if (maxTokenGuard <= 0) maxTokenGuard = 120_000;
            var buildTimeout  = parseResult.GetValue(buildTimeoutOption);
            if (buildTimeout <= 0) buildTimeout = 180;
            var qualityDiff   = parseResult.GetValue(qualityDiffOption);

            if (!from.Exists)
            {
                await Console.Error.WriteLineAsync($"error: --from file not found: {from.FullName}");
                return 2;
            }
            if (!target.Exists || !target.Extension.Equals(".sln", StringComparison.OrdinalIgnoreCase))
            {
                await Console.Error.WriteLineAsync($"error: --target must be an existing .sln: {target.FullName}");
                return 2;
            }

            var adapters = services.GetRequiredService<IReadOnlyDictionary<string, ILlmAdapter>>();
            if (!adapters.TryGetValue(model, out var adapter))
            {
                await Console.Error.WriteLineAsync(
                    $"error: model '{model}' not configured. Available: {string.Join(", ", adapters.Keys)}");
                return 2;
            }

            var known = LoadKnownInstances(from.FullName);
            if (known.Count == 0)
            {
                await Console.Error.WriteLineAsync("error: no known instances found in --from file.");
                return 2;
            }

            // Optional whole-corpus sweep: run the agent on every .cs under --target so detections on
            // clean/distractor files are scoreable as spurious (precision over non-instances).
            IReadOnlyList<string>? sweepFiles = null;
            if (sweepCorpus)
            {
                var root = Path.GetDirectoryName(target.FullName)!;
                sweepFiles = Directory.EnumerateFiles(root, "*.cs", SearchOption.AllDirectories)
                    .Where(p => !p.Split('\\', '/').Any(seg => seg is "bin" or "obj"))
                    .ToList();
                if (sweepFiles.Count == 0)
                    await Console.Error.WriteLineAsync($"warning: no .cs files under --target ({root}); using instance files only.");
            }

            var stamp         = DateTimeOffset.UtcNow.ToString("yyyyMMdd-HHmmss");
            var runStorePath  = Path.Combine("runs", $"{stamp}-agentic.jsonl");
            var trajectoryDir = Path.Combine("runs", $"{stamp}-agentic-trajectories");
            Console.Error.WriteLine($"Run trace: {Path.GetFullPath(runStorePath)}");
            Console.Error.WriteLine($"Trajectories: {Path.GetFullPath(trajectoryDir)}{Environment.NewLine}");

            var measurer = services.GetRequiredService<IRepairMeasurer>();
            var qualityScanner = qualityDiff ? services.GetRequiredService<ISolutionQualityScanner>() : null;
            if (qualityDiff)
                Console.Error.WriteLine("quality-diff: ON — whole-solution Layer 1 + Layer 2 measured for each trajectory's final built state.");

            await using IRunStore runStore = new JsonlRunStore(runStorePath);
            var runner = new AgenticRunner(adapter, model, measurer, target.FullName, budget, buildTimeout,
                qualityScanner: qualityScanner);
            await runner.RunAsync(known, runs, runStore, maxTokenGuard, trajectoryDir, Console.Error, cancellationToken, sweepFiles);

            Console.Error.WriteLine($"{Environment.NewLine}Agentic run complete.");
            return 0;
        });

        return command;
    }

    /// <summary>
    /// Reads a run JSONL and reconstructs the distinct known instances
    /// (deduplicated by file + symbol + line). Tolerant of the snake_case schema.
    /// </summary>
    private static IReadOnlyList<KnownInstance> LoadKnownInstances(string path)
    {
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var result = new List<KnownInstance>();

        foreach (var raw in File.ReadLines(path))
        {
            var line = raw.Trim();
            if (line.Length == 0) continue;

            JsonDocument doc;
            try { doc = JsonDocument.Parse(line); }
            catch { continue; }

            using (doc)
            {
                var root = doc.RootElement;

                var typeStr  = GetString(root, "anti_pattern_type");
                var filePath = GetString(root, "file_path");
                var symbol   = GetString(root, "symbol_name");
                if (typeStr is null || filePath is null || symbol is null) continue;

                var type = NormaliseType(typeStr);
                if (type is null) continue;

                var lineNo  = GetInt(root, "line") ?? 0;
                var snippet = GetString(root, "snippet");
                var sevStr  = GetString(root, "severity");
                var severity = sevStr?.ToLowerInvariant() switch
                {
                    "critical" => Severity.Critical,
                    "warning"  => Severity.Warning,
                    _          => Severity.Info
                };

                var key = $"{filePath}::{symbol}::{lineNo}";
                if (!seen.Add(key)) continue;

                result.Add(KnownInstance.Create(type.Value, filePath, symbol, lineNo, severity, snippet));
            }
        }

        return result;
    }

    private static string? GetString(JsonElement e, string name)
        => e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;

    private static int? GetInt(JsonElement e, string name)
        => e.TryGetProperty(name, out var v) && v.TryGetInt32(out var i) ? i : null;

    private static AntiPatternType? NormaliseType(string raw)
    {
        var t = raw.Replace(" ", "").Replace("_", "").Replace("-", "").ToLowerInvariant();
        return t switch
        {
            "godclass"                          => AntiPatternType.GodClass,
            "longmethod"                        => AntiPatternType.LongMethod,
            "obsoleteapiusage" or "obsoleteapi" => AntiPatternType.ObsoleteApiUsage,
            _                                   => null
        };
    }
}
