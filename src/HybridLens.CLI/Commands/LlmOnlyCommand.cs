using System.CommandLine;
using System.Text.Json;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;
using HybridLens.Pipeline;
using Microsoft.Extensions.DependencyInjection;

namespace HybridLens.CLI.Commands;

/// <summary>
/// The LLM-only architecture arm (§4.4.1). Reads the rated set produced by
/// select_rating_set.py, derives the distinct source files of the known instances,
/// and runs the frontier model over each whole file with prompt v1.2.0 (no static
/// grounding). Self-detections are matched back to the known instances for recall.
/// </summary>
public static class LlmOnlyCommand
{
    public static Command Build(IServiceProvider services)
    {
        var fromOption = new Option<FileInfo>("--from")
        {
            Description = "experiments_to_rate.jsonl (or any run JSONL) supplying the files + known instances.",
            Required = true
        };

        var modelOption = new Option<string>("--model")
        {
            Description = "Frontier model key from Llm.Models (default: gpt-5.4)."
        };

        var runsOption = new Option<int>("--runs")
        {
            Description = "Runs per file (default: 3)."
        };

        var maxTokenGuardOption = new Option<int>("--max-input-tokens")
        {
            Description = "Heuristic token cap; files estimated above this are flagged context_truncated (default: 120000)."
        };

        var command = new Command("llm-only",
            "Run the ungrounded LLM-only arm over the files of the known instances (H1b).")
        {
            fromOption, modelOption, runsOption, maxTokenGuardOption
        };

        command.SetAction(async (parseResult, cancellationToken) =>
        {
            var from          = parseResult.GetValue(fromOption)!;
            var model         = parseResult.GetValue(modelOption) is { Length: > 0 } m ? m : "gpt-5.4";
            var runs          = parseResult.GetValue(runsOption);
            if (runs < 1) runs = 3;
            var maxTokenGuard = parseResult.GetValue(maxTokenGuardOption);
            if (maxTokenGuard <= 0) maxTokenGuard = 120_000;

            if (!from.Exists)
            {
                await Console.Error.WriteLineAsync($"error: --from file not found: {from.FullName}");
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

            var runStorePath = Path.Combine("runs", $"{DateTimeOffset.UtcNow:yyyyMMdd-HHmmss}-llmonly.jsonl");
            Console.Error.WriteLine($"Run trace: {Path.GetFullPath(runStorePath)}{Environment.NewLine}");

            await using IRunStore runStore = new JsonlRunStore(runStorePath);
            var runner = new LlmOnlyRunner(adapter, model);
            await runner.RunAsync(known, runs, runStore, maxTokenGuard, Console.Error, cancellationToken);

            Console.Error.WriteLine($"{Environment.NewLine}LLM-only run complete.");
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

                // Skip rows that are themselves LLM-only or analyser placeholders without a real instance.
                var typeStr = GetString(root, "anti_pattern_type");
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
