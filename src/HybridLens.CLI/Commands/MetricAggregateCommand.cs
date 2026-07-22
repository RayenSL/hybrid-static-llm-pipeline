using System.CommandLine;
using System.Text.Json;
using HybridLens.StaticAnalysis;

namespace HybridLens.CLI.Commands;

/// <summary>
/// Aggregates the before→after triggering metric for every RESOLVED repair of an iterative arm, offline,
/// from the frozen trajectories (no re-run, no LLM). For each resolved final-snapshot row it measures the
/// after metric on the trajectory's final_source with the exact detector computation — Long Method → CC,
/// God Class → WMC (both syntactic) — and pairs it with the before value from the original detector run.
/// Obsolete API is binary (present→absent), emitted as 1→0. Feeds the aggregate metric-reduction figure.
/// </summary>
public static class MetricAggregateCommand
{
    public static Command Build(IServiceProvider services)
    {
        var verifiedOption = new Option<FileInfo>("--verified") { Description = "Verify/agentic runs JSONL with the resolved final rows.", Required = true };
        var trajOption     = new Option<DirectoryInfo>("--trajectories") { Description = "Trajectory artefact directory for the same run.", Required = true };
        var originalOption = new Option<FileInfo>("--original") { Description = "experiments_to_rate.jsonl (supplies the before metrics).", Required = true };
        var corpusOption   = new Option<DirectoryInfo?>("--corpus") { Description = "Corpus root (unused unless before metrics are missing; reserved)." };
        var outOption      = new Option<FileInfo>("--out") { Description = "Output JSON (array of before/after rows).", Required = true };

        var command = new Command("metric-aggregate",
            "Measure before→after triggering metric for all resolved repairs of an iterative arm (offline).")
        {
            verifiedOption, trajOption, originalOption, corpusOption, outOption
        };

        command.SetAction(async (parseResult, cancellationToken) =>
        {
            var verified = parseResult.GetValue(verifiedOption)!;
            var trajDir  = parseResult.GetValue(trajOption)!;
            var original = parseResult.GetValue(originalOption)!;
            var outFile  = parseResult.GetValue(outOption)!;

            if (!verified.Exists) { await Console.Error.WriteLineAsync($"error: --verified not found: {verified.FullName}"); return 2; }
            if (!trajDir.Exists)  { await Console.Error.WriteLineAsync($"error: --trajectories not found: {trajDir.FullName}"); return 2; }
            if (!original.Exists) { await Console.Error.WriteLineAsync($"error: --original not found: {original.FullName}"); return 2; }

            // before metrics keyed by symbol (unique per instance in this corpus).
            var beforeCc  = new Dictionary<string, double>(StringComparer.Ordinal);
            var beforeWmc = new Dictionary<string, double>(StringComparer.Ordinal);
            foreach (var raw in File.ReadLines(original.FullName))
            {
                if (string.IsNullOrWhiteSpace(raw)) continue;
                try
                {
                    using var d = JsonDocument.Parse(raw);
                    var r = d.RootElement;
                    var sym = Str(r, "symbol_name"); if (sym is null) continue;
                    if (!r.TryGetProperty("metrics", out var m) || m.ValueKind != JsonValueKind.Object) continue;
                    if (m.TryGetProperty("CyclomaticComplexity", out var cc) && cc.TryGetDouble(out var ccv)) beforeCc[sym] = ccv;
                    if (m.TryGetProperty("WMC", out var w) && w.TryGetDouble(out var wv)) beforeWmc[sym] = wv;
                }
                catch { }
            }

            // trajectory index: (file basename, run) -> final_source.
            var trajBySrc = new Dictionary<(string, string), string>();
            foreach (var f in Directory.EnumerateFiles(trajDir.FullName, "*.json"))
            {
                try
                {
                    using var d = JsonDocument.Parse(await File.ReadAllTextAsync(f, cancellationToken));
                    var r = d.RootElement;
                    var file = r.TryGetProperty("file", out var fe) ? fe.GetString() ?? "" : "";
                    var run  = r.TryGetProperty("run", out var re) ? re.GetRawText() : "";
                    var src  = r.TryGetProperty("final_source", out var se) ? se.GetString() ?? "" : "";
                    if (file.Length > 0 && src.Length > 0)
                        trajBySrc[(Path.GetFileName(file), run)] = src;
                }
                catch { }
            }

            var rows = new List<object>();
            var missing = 0;
            foreach (var raw in File.ReadLines(verified.FullName))
            {
                if (string.IsNullOrWhiteSpace(raw)) continue;
                JsonDocument doc; try { doc = JsonDocument.Parse(raw); } catch { continue; }
                using (doc)
                {
                    var r = doc.RootElement;
                    if (Str(r, "agentic_snapshot") != "final") continue;
                    if (Str(r, "verified_repair_ladder") != "resolved") continue;

                    var type = Str(r, "anti_pattern_type") ?? "";
                    var sym  = Str(r, "symbol_name") ?? "";
                    var arch = Str(r, "architecture") ?? "";
                    var run  = r.TryGetProperty("run_number", out var rn) ? rn.GetRawText() : "";
                    var baseName = Path.GetFileName((Str(r, "file_path") ?? "").Replace('\\', '/'));

                    string? finalSrc = trajBySrc.GetValueOrDefault((baseName, run));
                    if (finalSrc is null) { missing++; continue; }

                    string metric; double before, after; double? threshold;
                    switch (type)
                    {
                        case "long_method":
                            metric = "CC"; threshold = 10;
                            before = beforeCc.GetValueOrDefault(sym, double.NaN);
                            after  = MethodMetricProbe.Measure(finalSrc, sym).Cc;
                            break;
                        case "god_class":
                            metric = "WMC"; threshold = 47;
                            before = beforeWmc.GetValueOrDefault(sym, double.NaN);
                            after  = MethodMetricProbe.MeasureWmc(finalSrc, sym).Wmc;
                            break;
                        case "obsolete_api_usage":
                            metric = "obsolete_present"; threshold = null;
                            before = 1; after = 0;   // binary: obsolete usage present → removed (resolved)
                            break;
                        default: continue;
                    }

                    rows.Add(new
                    {
                        architecture = arch, anti_pattern_type = type, symbol = sym, run = run,
                        metric, before, after, threshold, resolved = true
                    });
                }
            }

            await File.WriteAllTextAsync(outFile.FullName,
                JsonSerializer.Serialize(rows, new JsonSerializerOptions { WriteIndented = true }), cancellationToken);

            Console.Error.WriteLine($"wrote {rows.Count} resolved before/after row(s) to {outFile.FullName}" +
                                    (missing > 0 ? $" ({missing} skipped: no matching trajectory)" : ""));
            return 0;
        });

        return command;
    }

    private static string? Str(JsonElement e, string name)
        => e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;
}
