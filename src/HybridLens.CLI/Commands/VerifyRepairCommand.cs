using System.CommandLine;
using System.Text.Json;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;
using HybridLens.Pipeline;
using Microsoft.Extensions.DependencyInjection;

namespace HybridLens.CLI.Commands;

/// <summary>
/// Objective repair verification for the HYBRID arm (§4.5.1, §4.7.1). Reads a runs JSONL, takes every
/// hybrid generation row that produced a repair, and for each: applies it strict-literally with a
/// non-evaluated Claude-family applier, builds the applied corpus, and re-measures the triggering
/// metric. Emits one verification row per candidate with the ordinal ladder and binary outcome.
///
/// The agentic arm is NOT processed here: the agent edits the source itself within its loop, so its
/// final solution is scored directly inside <see cref="HybridLens.Pipeline.AgenticRunner"/> with no
/// separate apply step (§4.7.1). Only hybrid repairs flow through the applier.
/// </summary>
public static class VerifyRepairCommand
{
    public static Command Build(IServiceProvider services)
    {
        var fromOption = new Option<FileInfo>("--from")
        {
            Description = "Runs JSONL whose repair rows (parsed_suggested_fix) are verified.",
            Required = true
        };

        var targetOption = new Option<FileInfo>("--target")
        {
            Description = "The corpus solution (Corpus.sln) the runs were generated against.",
            Required = true
        };

        var applierOption = new Option<string>("--applier")
        {
            Description = "Applier model key from Llm.Models — a non-evaluated model from a different family than the evaluated model (default: DeepSeek-V4-Pro)."
        };

        var outOption = new Option<FileInfo?>("--out")
        {
            Description = "Output JSONL path (default: runs/<stamp>-verified.jsonl)."
        };

        var buildTimeoutOption = new Option<int>("--build-timeout")
        {
            Description = "Per-candidate dotnet build timeout in seconds (default: 180)."
        };

        var qualityDiffOption = new Option<bool>("--quality-diff")
        {
            Description = "Also measure whole-solution quality impact per built repair (Layer 1 detectors + Layer 2 CA analyzers, before→after). " +
                          "Adds a dedicated analyzer build per candidate; the verified-repair gate stays analyzer-free."
        };

        var command = new Command("verify-repair",
            "Apply each LLM repair, build, and re-measure the triggering metric (verified-repair, H1/H2b).")
        {
            fromOption, targetOption, applierOption, outOption, buildTimeoutOption, qualityDiffOption
        };

        command.SetAction(async (parseResult, cancellationToken) =>
        {
            var from         = parseResult.GetValue(fromOption)!;
            var target       = parseResult.GetValue(targetOption)!;
            var applierModel = parseResult.GetValue(applierOption) is { Length: > 0 } a ? a : "DeepSeek-V4-Pro";
            var outFile      = parseResult.GetValue(outOption);
            var buildTimeout = parseResult.GetValue(buildTimeoutOption);
            if (buildTimeout <= 0) buildTimeout = 180;
            var qualityDiff  = parseResult.GetValue(qualityDiffOption);

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
            if (!adapters.TryGetValue(applierModel, out var applierAdapter))
            {
                await Console.Error.WriteLineAsync(
                    $"error: applier model '{applierModel}' not configured. Available: {string.Join(", ", adapters.Keys)}");
                return 2;
            }

            var measurer   = services.GetRequiredService<IRepairMeasurer>();
            var candidates = LoadCandidates(from.FullName);
            if (candidates.Count == 0)
            {
                await Console.Error.WriteLineAsync("error: no repair candidates (rows with parsed_suggested_fix) found in --from file.");
                return 2;
            }

            var outPath = outFile?.FullName
                          ?? Path.Combine("runs", $"{DateTimeOffset.UtcNow:yyyyMMdd-HHmmss}-verified.jsonl");
            Console.Error.WriteLine($"Run trace: {Path.GetFullPath(outPath)}{Environment.NewLine}");

            var qualityScanner = qualityDiff ? services.GetRequiredService<ISolutionQualityScanner>() : null;
            if (qualityDiff)
                Console.Error.WriteLine("quality-diff: ON — whole-solution Layer 1 + Layer 2 measured per built repair.");

            await using IRunStore store = new JsonlRunStore(outPath);
            var applier  = new RepairApplier(applierAdapter, applierModel);
            var verifier = new RepairVerifier(applier, measurer, target.FullName, buildTimeout, qualityScanner: qualityScanner);
            await verifier.RunAsync(candidates, store, Console.Error, cancellationToken);

            Console.Error.WriteLine($"{Environment.NewLine}verify-repair complete.");
            return 0;
        });

        return command;
    }

    /// <summary>
    /// Reconstructs HYBRID repair candidates from a runs JSONL: every hybrid row carrying a non-empty
    /// parsed_suggested_fix. Analyser-only rows (no real repair), agentic rows (scored in their own
    /// runner), and pre-existing verification rows are skipped.
    /// </summary>
    private static IReadOnlyList<RepairCandidate> LoadCandidates(string path)
    {
        var result = new List<RepairCandidate>();

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

                // Skip rows that are themselves verification rows.
                if (root.TryGetProperty("verified_repair_ladder", out var vl) && vl.ValueKind != JsonValueKind.Null)
                    continue;
                if (root.TryGetProperty("applier_model", out var am) && am.ValueKind == JsonValueKind.String)
                    continue;

                var repair = GetString(root, "parsed_suggested_fix");
                if (string.IsNullOrWhiteSpace(repair)) continue;

                var typeStr = GetString(root, "anti_pattern_type");
                var filePath = GetString(root, "file_path");
                var symbol   = GetString(root, "symbol_name");
                if (typeStr is null || filePath is null || symbol is null) continue;

                var type = NormaliseType(typeStr);
                if (type is null) continue;

                // Hybrid only. Analyser-only emits no repair; the agentic arm is scored inside its own
                // runner (no separate applier, §4.7.1). Skip anything that is not a hybrid generation row.
                var architecture = GetString(root, "architecture") ?? "hybrid";
                if (!architecture.Equals("hybrid", StringComparison.OrdinalIgnoreCase)) continue;

                result.Add(new RepairCandidate
                {
                    SourceRunId   = GetString(root, "run_id") ?? Guid.NewGuid().ToString("N"),
                    Type          = type.Value,
                    FilePath      = filePath,
                    SymbolName    = symbol,
                    Line          = GetInt(root, "line") ?? 0,
                    Severity      = ParseSeverity(GetString(root, "severity")),
                    Snippet       = GetString(root, "snippet"),
                    Metrics       = ParseMetrics(root),
                    ContextLevel  = ParseContextLevel(GetString(root, "context_level")),
                    ModelName     = GetString(root, "model_name") ?? "unknown",
                    PromptVersion = GetString(root, "prompt_version") ?? "unknown",
                    Architecture  = architecture,
                    RunNumber     = GetInt(root, "run_number") ?? 1,
                    RepairText    = repair!
                });
            }
        }

        return result;
    }

    private static string? GetString(JsonElement e, string name)
        => e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;

    private static int? GetInt(JsonElement e, string name)
        => e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.Number && v.TryGetInt32(out var i) ? i : null;

    private static IReadOnlyDictionary<string, double>? ParseMetrics(JsonElement root)
    {
        if (!root.TryGetProperty("metrics", out var m) || m.ValueKind != JsonValueKind.Object)
            return null;

        var dict = new Dictionary<string, double>();
        foreach (var prop in m.EnumerateObject())
            if (prop.Value.ValueKind == JsonValueKind.Number && prop.Value.TryGetDouble(out var d))
                dict[prop.Name] = d;

        return dict.Count > 0 ? dict : null;
    }

    private static Severity ParseSeverity(string? raw) => raw?.ToLowerInvariant() switch
    {
        "critical" => Severity.Critical,
        "warning"  => Severity.Warning,
        _          => Severity.Info
    };

    private static ContextLevel ParseContextLevel(string? raw) => raw?.ToLowerInvariant() switch
    {
        "analyser_only" => ContextLevel.AnalyserOnly,
        "minimal"       => ContextLevel.Minimal,
        "structural"    => ContextLevel.Structural,
        "relational"    => ContextLevel.Relational,
        "full"          => ContextLevel.Full,
        _               => ContextLevel.Minimal
    };

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
