using System.CommandLine;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;
using HybridLens.Pipeline;
using Microsoft.Extensions.DependencyInjection;

namespace HybridLens.CLI.Commands;

/// <summary>Generates and baseline-admits one immutable pre-repair characterization-test artefact.</summary>
public static class GenerateCharacterizationTestCommand
{
    public static Command Build(IServiceProvider services)
    {
        var fromOption = new Option<FileInfo>("--from")
        {
            Description = "Frozen analyzer baseline used only to resolve the neutral target symbol and line range.",
            Required = true
        };
        var targetOption = new Option<FileInfo>("--target")
        {
            Description = "Pristine corpus solution (.sln).",
            Required = true
        };
        var sourceOption = new Option<FileInfo>("--source")
        {
            Description = "One pristine C# source file containing exactly one included Long Method/God Class target.",
            Required = true
        };
        var modelOption = new Option<string>("--model")
        {
            Description = "Configured model key used for the separate test-authoring call (default: gpt-5.4)."
        };
        var outOption = new Option<DirectoryInfo?>("--out")
        {
            Description = "Artefact directory (default: runs/<timestamp>-generated-tests)."
        };
        var baselineRunsOption = new Option<int>("--baseline-runs")
        {
            Description = "Pristine executions required by admission (minimum/default: 2)."
        };
        var timeoutOption = new Option<int>("--timeout")
        {
            Description = "Per build or execution timeout in seconds (default: 180)."
        };

        var command = new Command("generate-characterization-test",
            "Generate, baseline-check, and freeze one visible pre-repair characterization test.")
        {
            fromOption, targetOption, sourceOption, modelOption, outOption, baselineRunsOption, timeoutOption
        };

        command.SetAction(async (parseResult, cancellationToken) =>
        {
            var from = parseResult.GetValue(fromOption)!;
            var target = parseResult.GetValue(targetOption)!;
            var source = parseResult.GetValue(sourceOption)!;
            var model = parseResult.GetValue(modelOption) is { Length: > 0 } m ? m : "gpt-5.4";
            var baselineRuns = Math.Max(2, parseResult.GetValue(baselineRunsOption));
            var timeout = parseResult.GetValue(timeoutOption);
            if (timeout <= 0) timeout = 180;
            var output = parseResult.GetValue(outOption)?.FullName
                         ?? Path.Combine("runs", $"{DateTimeOffset.UtcNow:yyyyMMdd-HHmmss}-generated-tests");

            if (!from.Exists)
            {
                await Console.Error.WriteLineAsync($"error: --from baseline not found: {from.FullName}");
                return 2;
            }
            if (!target.Exists || !target.Extension.Equals(".sln", StringComparison.OrdinalIgnoreCase))
            {
                await Console.Error.WriteLineAsync($"error: --target must be an existing .sln: {target.FullName}");
                return 2;
            }
            if (!source.Exists || !source.Extension.Equals(".cs", StringComparison.OrdinalIgnoreCase))
            {
                await Console.Error.WriteLineAsync($"error: --source must be an existing .cs file: {source.FullName}");
                return 2;
            }

            var matchingTargets = FactorialCampaignInputLoader.Load(from.FullName)
                .Where(seed => Path.GetFullPath(seed.Known.FilePath)
                    .Equals(Path.GetFullPath(source.FullName), StringComparison.OrdinalIgnoreCase))
                .ToList();
            if (matchingTargets.Count != 1)
            {
                await Console.Error.WriteLineAsync(
                    $"error: --source must map to exactly one Long Method/God Class target in --from; found {matchingTargets.Count}");
                return 2;
            }
            var known = matchingTargets[0].Known;
            var targetDescriptor = BlindedTargetDescriptor.Create(
                known.SymbolName, known.Line, known.EndLine);

            var adapters = services.GetRequiredService<IReadOnlyDictionary<string, ILlmAdapter>>();
            if (!adapters.TryGetValue(model, out var adapter))
            {
                await Console.Error.WriteLineAsync(
                    $"error: model '{model}' not configured. Available: {string.Join(", ", adapters.Keys)}");
                return 2;
            }

            var generator = new CharacterizationTestGenerator(adapter, model);
            var result = await generator.GenerateAsync(
                source.FullName,
                target.FullName,
                output,
                targetDescriptor,
                baselineRuns,
                timeout,
                cancellationToken);

            Console.WriteLine($"target: {targetDescriptor.SymbolName}:{targetDescriptor.StartLine}-{targetDescriptor.EndLine}");
            Console.WriteLine($"status: {result.Artifact.AdmissionStatus}");
            Console.WriteLine($"admitted: {result.Artifact.Admitted}");
            Console.WriteLine($"artifact: {result.ArtifactPath}");
            if (!string.IsNullOrWhiteSpace(result.Artifact.AdmissionReason))
                Console.WriteLine($"reason: {result.Artifact.AdmissionReason}");

            // A rejected test is an expected persisted experimental outcome, not a campaign crash.
            return 0;
        });

        return command;
    }
}
