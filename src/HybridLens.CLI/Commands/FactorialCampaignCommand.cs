using System.CommandLine;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;
using HybridLens.Pipeline;
using Microsoft.Extensions.DependencyInjection;

namespace HybridLens.CLI.Commands;

/// <summary>Executes one frozen assignment at a time in manifest order, with crash-safe per-assignment traces.</summary>
public static class FactorialCampaignCommand
{
    public static Command Build(IServiceProvider services)
    {
        var manifestOption = new Option<FileInfo>("--manifest") { Required = true, Description = "Frozen campaign manifest." };
        var outOption = new Option<DirectoryInfo>("--out") { Required = true, Description = "Campaign output directory." };
        var dryRunOption = new Option<bool>("--dry-run")
        {
            Description = "Validate the manifest, resolve every target and print the plan. No model call is made."
        };
        var command = new Command("factorial-campaign",
            "Execute or safely resume a frozen randomized-block factorial campaign.")
        {
            manifestOption, outOption, dryRunOption
        };
        command.SetAction(async (parseResult, cancellationToken) =>
        {
            var manifestFile = parseResult.GetValue(manifestOption)!;
            var outputDirectory = parseResult.GetValue(outOption)!;
            var dryRun = parseResult.GetValue(dryRunOption);
            if (!manifestFile.Exists)
            {
                await Console.Error.WriteLineAsync($"error: manifest not found: {manifestFile.FullName}");
                return 2;
            }

            FactorialCampaignManifest manifest;
            Dictionary<string, LoadedGeneratedTest> visibleByArtifact;
            try
            {
                manifest = await FactorialCampaignManifestStore.LoadAsync(
                    manifestFile.FullName, verifyFiles: true, cancellationToken);
                visibleByArtifact = await FactorialCampaignPreflight.LoadVisibleTestsAsync(manifest, cancellationToken);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                await Console.Error.WriteLineAsync($"error: preflight failed before any model call: {ex.Message}");
                return 2;
            }

            if (dryRun)
            {
                // Preflight already validated the manifest, the target solution, the frozen baseline
                // hash and every pristine source hash. Report the plan and stop before any model call.
                Console.WriteLine($"manifest      : {manifestFile.FullName}");
                Console.WriteLine($"sha256        : {FactorialCampaignPlanner.Sha256File(manifestFile.FullName)}");
                Console.WriteLine($"campaign      : {manifest.CampaignId}"
                    + (manifest.Kind is null ? "" : $"  kind: {manifest.Kind}"));
                Console.WriteLine($"solution      : {manifest.TargetSolution}");
                Console.WriteLine($"model         : {manifest.ModelName}");
                Console.WriteLine($"design        : {string.Join(", ", FactorialCampaignPlanner.ExpectedSignatures(manifest))}");
                Console.WriteLine($"build args    : {(manifest.BuildArguments is { Count: > 0 } b ? string.Join(' ', b) : "(default)")}");
                Console.WriteLine($"assignments   : {manifest.Assignments.Count}"
                    + $" over {manifest.Assignments.Select(a => a.SymbolName).Distinct(StringComparer.Ordinal).Count()} target(s)"
                    + $" x {manifest.Repetitions} repetition(s)");
                Console.WriteLine($"visible tests : {manifest.Assignments.Count(a => a.VisibleTestsEnabled)} assignment(s)");
                foreach (var target in manifest.Assignments
                             .GroupBy(a => a.SymbolName, StringComparer.Ordinal)
                             .OrderBy(g => g.Key, StringComparer.Ordinal))
                {
                    var first = target.First();
                    Console.WriteLine($"  {target.Key,-56} {first.AntiPatternType,-12}"
                        + $" lines {first.Line}-{first.TargetEndLine}  {target.Count()} assignment(s)");
                }
                Console.WriteLine("dry run: manifest, solution, baseline and all pristine sources verified");
                return 0;
            }

            var adapters = services.GetRequiredService<IReadOnlyDictionary<string, ILlmAdapter>>();
            if (!adapters.TryGetValue(manifest.ModelName, out var adapter))
            {
                await Console.Error.WriteLineAsync($"error: frozen model '{manifest.ModelName}' is not configured");
                return 2;
            }

            Console.Error.WriteLine($"Manifest SHA-256: {FactorialCampaignPlanner.Sha256File(manifestFile.FullName)}");
            var runner = new FactorialCampaignRunner(adapter,
                services.GetRequiredService<IContextBuilder>(),
                services.GetRequiredService<IRepairMeasurer>());
            var outcome = await runner.RunAsync(manifest, outputDirectory.FullName,
                visibleByArtifact, Console.Error, cancellationToken);
            return CampaignExitStatus.From(outcome);
        });
        return command;
    }

}
