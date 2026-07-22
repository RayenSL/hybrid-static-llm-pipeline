using System.CommandLine;
using System.Text.Json;
using HybridLens.StaticAnalysis;

namespace HybridLens.CLI.Commands;

/// <summary>
/// Reconstructs the per-iteration triggering-metric trajectory of a single agentic/grounded run
/// (the supervisor's "do the metrics improve iteration by iteration?" question). Reads a frozen
/// trajectory artefact, replays the original source and every edit the agent submitted (iteration 0 =
/// pristine, 1..n = each edit→build), and measures the Long Method metric (cyclomatic complexity + LOC)
/// on each with the SAME computation as the detector. CC/LOC are syntactic, so even an edit that failed to
/// build is measured — which is exactly what lets the loop be traced step by step. Emits a JSON series for
/// the plotting script.
/// </summary>
public static class MetricTraceCommand
{
    public static Command Build(IServiceProvider services)
    {
        var trajOption = new Option<FileInfo>("--trajectory")
        {
            Description = "Path to a frozen trajectory artefact (runs/<stamp>-*-trajectories/<file>__run<N>.json).",
            Required = true
        };
        var corpusOption = new Option<DirectoryInfo>("--corpus")
        {
            Description = "Corpus root that holds the original source (iteration 0), e.g. …/hybrid-pipeline-corpus/corpus.",
            Required = true
        };
        var symbolOption = new Option<string?>("--symbol")
        {
            Description = "Target method symbol (e.g. AllocationCalculator.Allocate). Default: the highest-CC method per iteration."
        };
        var outOption = new Option<FileInfo?>("--out")
        {
            Description = "Write the JSON series here (default: alongside the trajectory as <name>.metric-trace.json)."
        };

        var command = new Command("metric-trace",
            "Trace a run's triggering metric (CC/LOC) iteration by iteration from its frozen trajectory.")
        {
            trajOption, corpusOption, symbolOption, outOption
        };

        command.SetAction(async (parseResult, cancellationToken) =>
        {
            var traj   = parseResult.GetValue(trajOption)!;
            var corpus = parseResult.GetValue(corpusOption)!;
            var symbol = parseResult.GetValue(symbolOption);
            var outFile = parseResult.GetValue(outOption);

            if (!traj.Exists) { await Console.Error.WriteLineAsync($"error: trajectory not found: {traj.FullName}"); return 2; }
            if (!corpus.Exists) { await Console.Error.WriteLineAsync($"error: corpus root not found: {corpus.FullName}"); return 2; }

            using var doc = JsonDocument.Parse(await File.ReadAllTextAsync(traj.FullName, cancellationToken));
            var root = doc.RootElement;

            var relFile = root.TryGetProperty("file", out var fe) ? fe.GetString() ?? "" : "";
            var origPath = Path.Combine(corpus.FullName, relFile.Replace('/', Path.DirectorySeparatorChar));
            if (!File.Exists(origPath)) { await Console.Error.WriteLineAsync($"error: original source not found: {origPath}"); return 2; }

            // Ordered build verdicts (one per edit).
            var buildOks = new List<bool>();
            if (root.TryGetProperty("builds", out var builds) && builds.ValueKind == JsonValueKind.Array)
                foreach (var b in builds.EnumerateArray())
                    buildOks.Add(b.TryGetProperty("ok", out var ok) && ok.ValueKind == JsonValueKind.True);

            // Reconstruct the edit sequence from the assistant turns (authoritative order of edits).
            var edits = new List<string>();
            if (root.TryGetProperty("turns", out var turns) && turns.ValueKind == JsonValueKind.Array)
                foreach (var t in turns.EnumerateArray())
                {
                    if (!t.TryGetProperty("role", out var r) || r.GetString() != "assistant") continue;
                    var content = t.TryGetProperty("content", out var c) ? c.GetString() ?? "" : "";
                    var edited = ExtractEditedFile(content);
                    if (edited is not null) edits.Add(edited);
                }

            // Iteration 0 = pristine; 1..n = each edit. build_ok aligns edits[k] with buildOks[k].
            var series = new List<object>();
            var originalSource = await File.ReadAllTextAsync(origPath, cancellationToken);
            var iter0 = MethodMetricProbe.Measure(originalSource, symbol);
            var target = iter0.Method;   // lock onto the method the detector would flag; track it across edits
            series.Add(Row(0, "original", buildOk: true, iter0));

            for (var k = 0; k < edits.Count; k++)
            {
                var m = MethodMetricProbe.Measure(edits[k], string.IsNullOrWhiteSpace(symbol) ? target : symbol);
                var ok = k < buildOks.Count && buildOks[k];
                series.Add(Row(k + 1, $"edit {k + 1}", ok, m));
            }

            var result = new
            {
                trajectory   = Path.GetFileName(traj.FullName),
                file         = relFile,
                architecture = root.TryGetProperty("architecture", out var a) ? a.GetString() : null,
                model        = root.TryGetProperty("model", out var mo) ? mo.GetString() : null,
                symbol       = symbol ?? target,
                target_method = target,
                cc_threshold = 10,
                loc_threshold = 50,
                iterations   = edits.Count,
                budget_exhausted = root.TryGetProperty("budget_exhausted", out var be) && be.ValueKind == JsonValueKind.True,
                series
            };

            var outPath = outFile?.FullName
                          ?? Path.Combine(traj.DirectoryName!, Path.GetFileNameWithoutExtension(traj.Name) + ".metric-trace.json");
            var json = JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true });
            await File.WriteAllTextAsync(outPath, json, cancellationToken);

            Console.WriteLine($"target: {target}  (cc threshold {result.cc_threshold})");
            using (var printed = JsonDocument.Parse(json))
                foreach (var row in printed.RootElement.GetProperty("series").EnumerateArray())
                    Console.WriteLine(
                        $"  iter {row.GetProperty("iteration").GetInt32()} " +
                        $"[{row.GetProperty("phase").GetString(),-9}] build={row.GetProperty("build_ok").GetBoolean(),-5} " +
                        $"CC={row.GetProperty("cc").GetInt32(),-3} LOC={row.GetProperty("loc").GetInt32(),-3} " +
                        $"triggers={row.GetProperty("triggers").GetBoolean()}" +
                        (row.GetProperty("has_syntax_errors").GetBoolean() ? " (unparseable-ish)" : ""));
            Console.Error.WriteLine($"wrote {outPath}");
            return 0;
        });

        return command;
    }

    private static object Row(int iteration, string phase, bool buildOk, MethodMetricProbe.MethodMetric m) => new
    {
        iteration,
        phase,
        build_ok = buildOk,
        cc = m.Cc,
        loc = m.Loc,
        triggers = m.Cc > 10,                 // Long Method primary gate (LongMethodDetector)
        method_found = m.Found,
        has_syntax_errors = m.HasSyntaxErrors
    };

    /// <summary>Pulls edited_file out of one assistant turn's raw JSON content, tolerating ``` fences.</summary>
    private static string? ExtractEditedFile(string content)
    {
        var json = content.Trim();
        if (json.StartsWith("```"))
        {
            json = string.Join('\n', json.Split('\n').Skip(1));
            var fence = json.LastIndexOf("```", StringComparison.Ordinal);
            if (fence >= 0) json = json[..fence].Trim();
        }
        try
        {
            using var d = JsonDocument.Parse(json);
            if (d.RootElement.ValueKind == JsonValueKind.Object &&
                d.RootElement.TryGetProperty("edited_file", out var e) &&
                e.ValueKind == JsonValueKind.String)
            {
                var s = e.GetString();
                return string.IsNullOrWhiteSpace(s) ? null : s;
            }
        }
        catch { /* not a JSON turn / no edit */ }
        return null;
    }
}
