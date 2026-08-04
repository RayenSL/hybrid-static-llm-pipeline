using System.CommandLine;
using System.Globalization;
using System.Text;
using System.Text.Json;
using HybridLens.StaticAnalysis;

namespace HybridLens.CLI.Commands;

/// <summary>
/// Mechanical post-run export of the syntactic triggering metrics used by the Chapter 5.4
/// before/after figure. It reads frozen final-source artifacts only; it performs no model call,
/// build, detector decision, or mutation of the archived codebases.
/// </summary>
public static class Chapter54MetricExportCommand
{
    public static Command Build()
    {
        var attemptsOption = new Option<FileInfo>("--attempts")
        {
            Description = "Canonical factorial attempts.json.",
            Required = true
        };
        var baselineOption = new Option<FileInfo>("--baseline")
        {
            Description = "Frozen confirmatory detector baseline JSONL.",
            Required = true
        };
        var outOption = new Option<FileInfo>("--out")
        {
            Description = "Output CSV.",
            Required = true
        };

        var command = new Command(
            "chapter54-metric-export",
            "Export frozen before/after Long Method CC and God Class WMC values for Chapter 5.4.")
        {
            attemptsOption, baselineOption, outOption
        };

        command.SetAction(async (parseResult, ct) =>
        {
            var attemptsFile = parseResult.GetValue(attemptsOption)!;
            var baselineFile = parseResult.GetValue(baselineOption)!;
            var outFile = parseResult.GetValue(outOption)!;
            if (!attemptsFile.Exists || !baselineFile.Exists)
            {
                await Console.Error.WriteLineAsync("error: attempts or baseline file not found");
                return 2;
            }

            var baseline = new Dictionary<string, BaselineRow>(StringComparer.OrdinalIgnoreCase);
            foreach (var line in File.ReadLines(baselineFile.FullName))
            {
                if (string.IsNullOrWhiteSpace(line)) continue;
                using var doc = JsonDocument.Parse(line);
                var root = doc.RootElement;
                var file = root.GetProperty("file_path").GetString() ?? "";
                var symbol = root.GetProperty("symbol_name").GetString() ?? "";
                var start = root.GetProperty("line").GetInt32();
                var type = root.GetProperty("anti_pattern_type").GetString() ?? "";
                var metrics = root.GetProperty("metrics");
                baseline[Key(file, symbol, start)] = new BaselineRow(type, symbol, metrics.Clone());
            }

            using var attemptsDoc = JsonDocument.Parse(
                await File.ReadAllTextAsync(attemptsFile.FullName, ct));
            var rows = new List<string>
            {
                "run_id,instance_key,anti_pattern_type,grounding_enabled,control_structure,visible_tests_enabled,metric_resolved,primary_metric,threshold,before_value,after_value,secondary_metric,before_secondary,after_secondary,target_found,syntax_errors,source_artifact"
            };

            foreach (var attempt in attemptsDoc.RootElement.EnumerateArray())
            {
                var instanceKey = attempt.GetProperty("instance_key").GetString() ?? "";
                if (!baseline.TryGetValue(instanceKey, out var original))
                    throw new InvalidOperationException($"baseline row not found: {instanceKey}");

                var artifactPath = attempt.GetProperty("materialized_source_ref").GetString() ?? "";
                using var artifactDoc = JsonDocument.Parse(
                    await File.ReadAllTextAsync(artifactPath, ct));
                var source = artifactDoc.RootElement.GetProperty("final_source").GetString() ?? "";

                string primaryMetric;
                string secondaryMetric;
                double before;
                double threshold;
                double beforeSecondary;
                double after;
                double afterSecondary;
                bool found;
                bool syntaxErrors;

                if (original.Type.Equals("long_method", StringComparison.OrdinalIgnoreCase))
                {
                    var measured = MethodMetricProbe.Measure(source, original.Symbol);
                    primaryMetric = "CyclomaticComplexity";
                    secondaryMetric = "LinesOfCode";
                    before = Number(original.Metrics, primaryMetric);
                    threshold = Number(original.Metrics, "MaxCyclomaticComplexity");
                    beforeSecondary = Number(original.Metrics, secondaryMetric);
                    after = measured.Cc;
                    afterSecondary = measured.Loc;
                    found = measured.Found;
                    syntaxErrors = measured.HasSyntaxErrors;
                }
                else
                {
                    var measured = MethodMetricProbe.MeasureWmc(source, original.Symbol);
                    primaryMetric = "WMC";
                    secondaryMetric = "DeclaredMethodCount";
                    before = Number(original.Metrics, primaryMetric);
                    threshold = Number(original.Metrics, "WmcVeryHigh");
                    beforeSecondary = Number(original.Metrics, "PublicMethods");
                    after = measured.Wmc;
                    afterSecondary = measured.MethodCount;
                    found = measured.Found;
                    syntaxErrors = measured.HasSyntaxErrors;
                }

                rows.Add(string.Join(",",
                    Csv(attempt.GetProperty("run_id").GetString()),
                    Csv(instanceKey),
                    Csv(original.Type),
                    Bool(attempt, "grounding_enabled"),
                    Csv(attempt.GetProperty("control_structure").GetString()),
                    Bool(attempt, "visible_tests_enabled"),
                    Bool(attempt, "metric_resolved"),
                    Csv(primaryMetric),
                    F(threshold),
                    F(before),
                    F(after),
                    Csv(secondaryMetric),
                    F(beforeSecondary),
                    F(afterSecondary),
                    found ? "true" : "false",
                    syntaxErrors ? "true" : "false",
                    Csv(artifactPath)));
            }

            outFile.Directory?.Create();
            await File.WriteAllTextAsync(
                outFile.FullName, string.Join("\n", rows) + "\n",
                new UTF8Encoding(false), ct);
            Console.WriteLine($"wrote {rows.Count - 1} metric rows to {outFile.FullName}");
            return 0;
        });

        return command;
    }

    private sealed record BaselineRow(string Type, string Symbol, JsonElement Metrics);

    private static string Key(string file, string symbol, int line)
        => $"{file}::{symbol}::{line}";

    private static double Number(JsonElement metrics, string key)
        => metrics.TryGetProperty(key, out var value) ? value.GetDouble() : 0;

    private static string Bool(JsonElement row, string key)
        => row.GetProperty(key).GetBoolean() ? "true" : "false";

    private static string F(double value)
        => value.ToString("0.####", CultureInfo.InvariantCulture);

    private static string Csv(string? value)
        => $"\"{(value ?? "").Replace("\"", "\"\"")}\"";
}
