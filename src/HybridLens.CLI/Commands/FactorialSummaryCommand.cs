using System.CommandLine;
using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.Core.Models;
using HybridLens.Pipeline;

namespace HybridLens.CLI.Commands;

/// <summary>Builds the prespecified ITT attempt table and arm-level effectiveness/cost summary.</summary>
public static class FactorialSummaryCommand
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) },
        WriteIndented = true
    };

    public static Command Build()
    {
        var runsOption = new Option<DirectoryInfo>("--runs-dir")
        {
            Description = "Directory containing factorial repair run JSONL files.",
            Required = true
        };
        var privateOption = new Option<DirectoryInfo>("--private-dir")
        {
            Description = "Directory containing blinded private Layer-3 result JSONL files.",
            Required = true
        };
        var outOption = new Option<DirectoryInfo?>("--out")
        {
            Description = "New analysis output directory (default: results/<timestamp>-factorial-summary)."
        };

        var command = new Command("factorial-summary",
            "Create the Long Method/God Class ITT strict-success table and token/call/build/test tracker by factorial arm.")
        {
            runsOption, privateOption, outOption
        };
        command.SetAction(async (parseResult, cancellationToken) =>
        {
            var runsDirectory = parseResult.GetValue(runsOption)!;
            var privateDirectory = parseResult.GetValue(privateOption)!;
            var output = parseResult.GetValue(outOption)?.FullName
                         ?? Path.GetFullPath(Path.Combine(
                             "results", $"{DateTimeOffset.UtcNow:yyyyMMdd-HHmmss}-factorial-summary"));
            if (!runsDirectory.Exists || !privateDirectory.Exists)
            {
                await Console.Error.WriteLineAsync("error: --runs-dir and --private-dir must both exist.");
                return 2;
            }
            if (Directory.Exists(output) && Directory.EnumerateFileSystemEntries(output).Any())
            {
                await Console.Error.WriteLineAsync($"error: refusing to overwrite non-empty analysis directory: {output}");
                return 2;
            }

            var runs = LoadJsonLines<RunRecord>(runsDirectory.FullName, "grounding_enabled");
            var privateResults = LoadJsonLines<PrivateLayer3Result>(privateDirectory.FullName, "oracle_manifest_version");
            FactorialAnalysisResult result;
            try
            {
                result = FactorialResultAnalyzer.Analyze(runs, privateResults);
            }
            catch (InvalidDataException ex)
            {
                await Console.Error.WriteLineAsync($"error: factorial analysis integrity check failed: {ex.Message}");
                return 2;
            }

            Directory.CreateDirectory(output);
            await File.WriteAllTextAsync(
                Path.Combine(output, "attempts.json"),
                JsonSerializer.Serialize(result.Attempts, JsonOptions),
                new UTF8Encoding(false), cancellationToken);
            await File.WriteAllTextAsync(
                Path.Combine(output, "arm_summary.json"),
                JsonSerializer.Serialize(result.Arms, JsonOptions),
                new UTF8Encoding(false), cancellationToken);
            await File.WriteAllTextAsync(
                Path.Combine(output, "arm_summary.csv"),
                ArmCsv(result.Arms),
                new UTF8Encoding(false), cancellationToken);

            Console.Error.WriteLine($"Factorial summary: {output}");
            foreach (var arm in result.Arms)
                Console.WriteLine(
                    $"{arm.ControlStructure}, grounding={arm.GroundingEnabled}, tests={arm.VisibleTestsEnabled}: " +
                    $"strict={arm.StrictSuccesses}/{arm.AssignedAttempts} ({arm.StrictSuccessRate:P1}), " +
                    $"mean_tokens={Format(arm.MeanTotalTokens)}, total_tokens={arm.TotalTokensConsumed?.ToString() ?? "NA"}");
            return 0;
        });
        return command;
    }

    private static List<T> LoadJsonLines<T>(string directory, string discriminator)
    {
        var result = new List<T>();
        foreach (var path in Directory.EnumerateFiles(directory, "*.jsonl", SearchOption.AllDirectories).Order(StringComparer.Ordinal))
            foreach (var raw in File.ReadLines(path))
            {
                if (!raw.Contains($"\"{discriminator}\"", StringComparison.Ordinal)) continue;
                try
                {
                    var value = JsonSerializer.Deserialize<T>(raw, JsonOptions);
                    if (value is not null) result.Add(value);
                }
                catch (JsonException ex)
                {
                    throw new InvalidDataException($"invalid JSONL record in {path}: {ex.Message}", ex);
                }
            }
        return result;
    }

    private static string ArmCsv(IReadOnlyList<FactorialArmSummary> arms)
    {
        var rows = new List<string>
        {
            "control_structure,grounding_enabled,visible_tests_enabled,assigned_attempts,materialized_attempts," +
            "build_passed_attempts,metric_resolved_attempts,private_passed_attempts,strict_successes," +
            "strict_success_rate,visible_test_availability_rate,token_observed_attempts,mean_input_tokens," +
            "mean_output_tokens,mean_total_tokens,total_tokens_consumed,mean_llm_calls,mean_build_attempts," +
            "mean_test_attempts,mean_test_duration_ms,mean_repair_duration_ms"
        };
        rows.AddRange(arms.Select(a => string.Join(',',
            a.ControlStructure,
            a.GroundingEnabled.ToString().ToLowerInvariant(),
            a.VisibleTestsEnabled.ToString().ToLowerInvariant(),
            a.AssignedAttempts,
            a.MaterializedAttempts,
            a.BuildPassedAttempts,
            a.MetricResolvedAttempts,
            a.PrivatePassedAttempts,
            a.StrictSuccesses,
            Format(a.StrictSuccessRate),
            Format(a.VisibleTestAvailabilityRate),
            a.TokenObservedAttempts,
            Format(a.MeanInputTokens),
            Format(a.MeanOutputTokens),
            Format(a.MeanTotalTokens),
            a.TotalTokensConsumed?.ToString(CultureInfo.InvariantCulture) ?? string.Empty,
            Format(a.MeanLlmCalls),
            Format(a.MeanBuildAttempts),
            Format(a.MeanTestAttempts),
            Format(a.MeanTestDurationMs),
            Format(a.MeanRepairDurationMs))));
        return string.Join(Environment.NewLine, rows) + Environment.NewLine;
    }

    private static string Format(double? value) => value?.ToString("0.####", CultureInfo.InvariantCulture) ?? string.Empty;
}
