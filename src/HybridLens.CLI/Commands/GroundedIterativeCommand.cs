using System.CommandLine;
using System.Text;
using System.Text.Json;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
using HybridLens.Pipeline;
using Microsoft.Extensions.DependencyInjection;

namespace HybridLens.CLI.Commands;

/// <summary>
/// The grounded-iterative arm (§4.4.1, §5.1.5) — the H1c contrast. It reuses the agentic loop and
/// prompt (v2.0.0) verbatim, but seeds the opening user prompt with the analyser's Structural-level
/// finding block for each seeded instance in the file (rendered by <see cref="IContextBuilder"/> at
/// <see cref="ContextLevel.Structural"/>), so the detector's output is routed into the loop rather than
/// withheld. It therefore differs from the ungrounded <c>agentic</c> command ONLY in that grounding,
/// which holds the iterative control structure fixed so the H1c contrast (grounded-iterative vs
/// ungrounded agentic) varies grounding alone. Like agentic, the agent's edited solution is scored
/// directly for verified-repair at BOTH the first-build and final snapshots (no separate applier,
/// §4.7.1); being supplied the findings, it writes no detection rows.
/// </summary>
public static class GroundedIterativeCommand
{
    public static Command Build(IServiceProvider services)
    {
        var fromOption = new Option<FileInfo>("--from")
        {
            Description = "Analyzer run JSONL supplying the files, known instances, and their metrics.",
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
            Description = "Frozen iteration budget — max edit→build attempts per trajectory (default: 6). Must match the agentic arm so the 2×2 holds the control structure fixed."
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

        var command = new Command("grounded-iterative",
            "Run the grounded-iterative arm (H1c): the agentic loop seeded with the analyser's Structural finding block, varying grounding alone.")
        {
            fromOption, targetOption, modelOption, runsOption, budgetOption, maxTokenGuardOption, buildTimeoutOption, qualityDiffOption
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

            var instances = LoadInstances(from.FullName);
            if (instances.Count == 0)
            {
                await Console.Error.WriteLineAsync("error: no known instances found in --from file.");
                return 2;
            }

            // Render the Structural-level finding block for each file via ContextBuilder — exactly the
            // grounding the hybrid arm shows (§5.1.5). Per file, all its findings' blocks are concatenated.
            var contextBuilder   = services.GetRequiredService<IContextBuilder>();
            var structuralConfig = new ContextConfig { Level = ContextLevel.Structural };

            var known           = instances.Select(i => i.Known).ToList();
            var groundingByFile = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            var missingMetrics  = 0;

            foreach (var g in instances.GroupBy(i => Path.GetFullPath(i.Finding.FilePath), StringComparer.OrdinalIgnoreCase))
            {
                var fileFindings = g.Select(x => x.Finding).ToList();
                var sb = new StringBuilder();
                foreach (var finding in fileFindings)
                {
                    if (finding.Metrics.Count == 0 && finding.Type != AntiPatternType.ObsoleteApiUsage)
                        missingMetrics++;
                    var req = contextBuilder.Build(finding, fileFindings, structuralConfig);
                    sb.AppendLine(req.UserPrompt.TrimEnd());
                    sb.AppendLine();
                }
                groundingByFile[g.Key] = sb.ToString().TrimEnd();
            }

            if (missingMetrics > 0)
                await Console.Error.WriteLineAsync(
                    $"warning: {missingMetrics} metric-based instance(s) had no metrics in --from; their grounding " +
                    "block omits the Metrics section. Use a run JSONL that carries detector metrics for full fidelity.");

            var stamp         = DateTimeOffset.UtcNow.ToString("yyyyMMdd-HHmmss");
            var runStorePath  = Path.Combine("runs", $"{stamp}-grounded-iterative.jsonl");
            var trajectoryDir = Path.Combine("runs", $"{stamp}-grounded-iterative-trajectories");
            Console.Error.WriteLine($"Run trace: {Path.GetFullPath(runStorePath)}");
            Console.Error.WriteLine($"Trajectories: {Path.GetFullPath(trajectoryDir)}{Environment.NewLine}");

            var measurer = services.GetRequiredService<IRepairMeasurer>();
            var qualityScanner = qualityDiff ? services.GetRequiredService<ISolutionQualityScanner>() : null;
            if (qualityDiff)
                Console.Error.WriteLine("quality-diff: ON — whole-solution Layer 1 + Layer 2 measured for each trajectory's final built state.");

            await using IRunStore runStore = new JsonlRunStore(runStorePath);
            var runner = new AgenticRunner(
                adapter, model, measurer, target.FullName, budget, buildTimeout, architecture: "grounded_iterative",
                qualityScanner: qualityScanner);
            await runner.RunAsync(
                known, runs, runStore, maxTokenGuard, trajectoryDir, Console.Error, cancellationToken,
                sweepFiles: null, groundingByFile: groundingByFile);

            Console.Error.WriteLine($"{Environment.NewLine}Grounded-iterative run complete.");
            return 0;
        });

        return command;
    }

    /// <summary>
    /// Reads a run JSONL and reconstructs the distinct known instances (deduplicated by file + symbol +
    /// line), pairing each with a <see cref="Finding"/> carrying the detector metrics needed to render the
    /// Structural grounding block. When several records share a key, the first record carrying non-empty
    /// metrics supplies them (analyser/hybrid rows carry metrics; agentic detection rows do not).
    /// </summary>
    private static IReadOnlyList<(KnownInstance Known, Finding Finding)> LoadInstances(string path)
    {
        var order   = new List<string>();
        var byKey   = new Dictionary<string, (AntiPatternType Type, string File, string Symbol, int Line, Severity Sev, string? Snippet, Dictionary<string, double> Metrics)>(StringComparer.Ordinal);

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
                var metrics = GetMetrics(root);

                var key = $"{filePath}::{symbol}::{lineNo}";
                if (!byKey.TryGetValue(key, out var entry))
                {
                    order.Add(key);
                    byKey[key] = (type.Value, filePath, symbol, lineNo, severity, snippet, metrics);
                }
                else if (entry.Metrics.Count == 0 && metrics.Count > 0)
                {
                    // Backfill metrics from a later record (e.g. a hybrid row) when the first lacked them.
                    entry.Metrics = metrics;
                    if (string.IsNullOrEmpty(entry.Snippet) && !string.IsNullOrEmpty(snippet)) entry.Snippet = snippet;
                    byKey[key] = entry;
                }
            }
        }

        var result = new List<(KnownInstance, Finding)>(order.Count);
        foreach (var key in order)
        {
            var e = byKey[key];
            var known = KnownInstance.Create(e.Type, e.File, e.Symbol, e.Line, e.Sev, e.Snippet);
            var finding = new Finding
            {
                Type       = e.Type,
                Severity   = e.Sev,
                FilePath   = e.File,
                SymbolName = e.Symbol,
                Line       = e.Line,
                Snippet    = e.Snippet,
                Metrics    = e.Metrics
            };
            result.Add((known, finding));
        }

        return result;
    }

    private static string? GetString(JsonElement e, string name)
        => e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;

    private static int? GetInt(JsonElement e, string name)
        => e.TryGetProperty(name, out var v) && v.TryGetInt32(out var i) ? i : null;

    private static Dictionary<string, double> GetMetrics(JsonElement e)
    {
        var metrics = new Dictionary<string, double>(StringComparer.Ordinal);
        if (e.TryGetProperty("metrics", out var m) && m.ValueKind == JsonValueKind.Object)
            foreach (var prop in m.EnumerateObject())
                if (prop.Value.ValueKind == JsonValueKind.Number && prop.Value.TryGetDouble(out var d))
                    metrics[prop.Name] = d;
        return metrics;
    }

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
