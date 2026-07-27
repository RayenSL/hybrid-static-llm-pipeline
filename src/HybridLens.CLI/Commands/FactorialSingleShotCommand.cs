using System.CommandLine;
using System.Text.Json;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
using HybridLens.Pipeline;
using Microsoft.Extensions.DependencyInjection;

namespace HybridLens.CLI.Commands;

/// <summary>Runs an independently executed grounded or ungrounded one-call direct-edit condition.</summary>
public static class FactorialSingleShotCommand
{
    public static Command Build(IServiceProvider services)
    {
        var fromOption = new Option<FileInfo>("--from")
        {
            Description = "Analyzer JSONL supplying Long Method and God Class instances and metrics.",
            Required = true
        };
        var targetOption = new Option<FileInfo>("--target")
        {
            Description = "Pristine corpus solution (.sln).",
            Required = true
        };
        var modelOption = new Option<string>("--model")
        {
            Description = "Configured evaluated-model key (default: gpt-5.4)."
        };
        var runsOption = new Option<int>("--runs")
        {
            Description = "Independent attempts per instance (default: 3)."
        };
        var groundedOption = new Option<bool>("--grounded")
        {
            Description = "Supply the Structural finding. Omit for the target-only diagnosis-and-repair cell."
        };
        var visibleTestsOption = new Option<DirectoryInfo?>("--visible-tests")
        {
            Description = "Generated-test artefact directory. Supplying it assigns the test-enabled condition; rejected/missing tests remain unavailable under ITT."
        };
        var timeoutOption = new Option<int>("--build-timeout")
        {
            Description = "Build and visible-test timeout in seconds (default: 180)."
        };

        var command = new Command("factorial-single-shot",
            "Run one independent single-shot factorial cell (grounding on/off, visible test on/off).")
        {
            fromOption, targetOption, modelOption, runsOption, groundedOption, visibleTestsOption, timeoutOption
        };

        command.SetAction(async (parseResult, cancellationToken) =>
        {
            var from = parseResult.GetValue(fromOption)!;
            var target = parseResult.GetValue(targetOption)!;
            var model = parseResult.GetValue(modelOption) is { Length: > 0 } m ? m : "gpt-5.4";
            var runs = parseResult.GetValue(runsOption);
            if (runs < 1) runs = 3;
            var grounded = parseResult.GetValue(groundedOption);
            var visibleDirectory = parseResult.GetValue(visibleTestsOption);
            var visibleEnabled = visibleDirectory is not null;
            var timeout = parseResult.GetValue(timeoutOption);
            if (timeout <= 0) timeout = 180;

            if (!from.Exists)
            {
                await Console.Error.WriteLineAsync($"error: --from not found: {from.FullName}");
                return 2;
            }
            if (!target.Exists || !target.Extension.Equals(".sln", StringComparison.OrdinalIgnoreCase))
            {
                await Console.Error.WriteLineAsync($"error: --target must be an existing .sln: {target.FullName}");
                return 2;
            }
            if (visibleDirectory is not null && !visibleDirectory.Exists)
            {
                await Console.Error.WriteLineAsync($"error: --visible-tests directory not found: {visibleDirectory.FullName}");
                return 2;
            }

            var adapters = services.GetRequiredService<IReadOnlyDictionary<string, ILlmAdapter>>();
            if (!adapters.TryGetValue(model, out var adapter))
            {
                await Console.Error.WriteLineAsync(
                    $"error: model '{model}' not configured. Available: {string.Join(", ", adapters.Keys)}");
                return 2;
            }

            var inputs = LoadInputs(from.FullName);
            if (inputs.Count == 0)
            {
                await Console.Error.WriteLineAsync("error: no Long Method or God Class instances found in --from.");
                return 2;
            }

            var visibleBySource = visibleDirectory is null
                ? new Dictionary<string, LoadedGeneratedTest>(StringComparer.OrdinalIgnoreCase)
                : await VisibleTestDirectoryLoader.LoadAsync(visibleDirectory.FullName, cancellationToken);
            var contextBuilder = services.GetRequiredService<IContextBuilder>();
            var structural = new ContextConfig { Level = ContextLevel.Structural };
            var stamp = DateTimeOffset.UtcNow.ToString("yyyyMMdd-HHmmss");
            var arm = grounded ? "grounded-single-shot" : "ungrounded-single-shot";
            var testTag = visibleEnabled ? "tests" : "no-tests";
            var tracePath = Path.Combine("runs", $"{stamp}-{arm}-{testTag}.jsonl");
            var artifactDirectory = Path.Combine("runs", $"{stamp}-{arm}-{testTag}-final-sources");
            Console.Error.WriteLine($"Run trace: {Path.GetFullPath(tracePath)}");
            Console.Error.WriteLine($"Final sources: {Path.GetFullPath(artifactDirectory)}");
            Console.Error.WriteLine($"Cell: grounding={grounded}, visible_tests={visibleEnabled}, instances={inputs.Count}, runs={runs}");

            var runner = new FactorialSingleShotRunner(
                adapter,
                model,
                services.GetRequiredService<IRepairMeasurer>(),
                target.FullName,
                timeout);
            await using IRunStore store = new JsonlRunStore(tracePath);
            var index = 0;
            foreach (var input in inputs)
            {
                index++;
                var groundingBlock = grounded
                    ? contextBuilder.Build(input.Finding, [input.Finding], structural).UserPrompt
                    : null;
                visibleBySource.TryGetValue(Path.GetFullPath(input.Known.FilePath), out var visible);
                for (var run = 1; run <= runs; run++)
                {
                    var record = await runner.RunAttemptAsync(
                        input.Known,
                        run,
                        grounded,
                        groundingBlock,
                        visibleEnabled,
                        visible,
                        artifactDirectory,
                        cancellationToken);
                    await store.AppendAsync(record, cancellationToken);
                    Console.Error.WriteLine(
                        $"[{index}/{inputs.Count}] {input.Known.Type} {input.Known.SymbolName} run{run}: " +
                        $"build={record.BuildPassed}, visible={record.VisibleTestPassed}, resolved={record.VerifiedRepairSuccess}");
                }
            }

            return 0;
        });
        return command;
    }

    private sealed record Input(KnownInstance Known, Finding Finding);

    private static IReadOnlyList<Input> LoadInputs(string path)
    {
        var result = new List<Input>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var raw in File.ReadLines(path))
        {
            try
            {
                using var document = JsonDocument.Parse(raw);
                var root = document.RootElement;
                var typeText = String(root, "anti_pattern_type");
                var type = NormaliseType(typeText);
                if (type is not (AntiPatternType.GodClass or AntiPatternType.LongMethod)) continue;
                var file = String(root, "file_path");
                var symbol = String(root, "symbol_name");
                if (file is null || symbol is null) continue;
                var line = Int(root, "line") ?? 0;
                var key = $"{file}::{symbol}::{line}";
                if (!seen.Add(key)) continue;
                var severity = String(root, "severity")?.ToLowerInvariant() switch
                {
                    "critical" => Severity.Critical,
                    "warning" => Severity.Warning,
                    _ => Severity.Info
                };
                var snippet = String(root, "snippet");
                var metrics = new Dictionary<string, double>(StringComparer.Ordinal);
                if (root.TryGetProperty("metrics", out var metricObject) && metricObject.ValueKind == JsonValueKind.Object)
                    foreach (var property in metricObject.EnumerateObject())
                        if (property.Value.TryGetDouble(out var value)) metrics[property.Name] = value;
                var known = KnownInstance.Create(type.Value, file, symbol, line, severity, snippet);
                result.Add(new Input(known, new Finding
                {
                    Type = type.Value,
                    Severity = severity,
                    FilePath = file,
                    SymbolName = symbol,
                    Line = line,
                    Snippet = snippet,
                    Metrics = metrics
                }));
            }
            catch (JsonException) { }
        }
        return result;
    }

    private static string? String(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
    private static int? Int(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value) && value.TryGetInt32(out var number) ? number : null;
    private static AntiPatternType? NormaliseType(string? raw)
    {
        var value = raw?.Replace(" ", "").Replace("_", "").Replace("-", "").ToLowerInvariant();
        return value switch
        {
            "godclass" => AntiPatternType.GodClass,
            "longmethod" => AntiPatternType.LongMethod,
            _ => null
        };
    }
}
