using System.CommandLine;
using HybridLens.ContextBuilder;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;
using HybridLens.Pipeline;
using Microsoft.Extensions.DependencyInjection;

namespace HybridLens.CLI.Commands;

/// <summary>
/// Executes a frozen Minimal/Structural/Relational/Full context ladder on the direct-editing
/// architecture (§4.4.3).
///
/// The sealed four-level supplement ran through suggestion-plus-applier, and 66% of its assignments
/// never reached a build: a non-evaluated strict-literal applier refused every God Class
/// recommendation and almost every Obsolete API one, so the outcome measured that applier's
/// contract rather than the context dose. This command removes the applier entirely. One evaluated
/// call per assignment returns the complete edited file, exactly as the confirmatory factorial
/// does, which is what makes an RQ3 answer transfer to the architecture the thesis recommends.
///
/// The manifest carries the ladder version and its hash. The campaign refuses to start if the
/// compiled ladder differs, so a definition edited after freezing cannot silently produce
/// assignments attributed to the old definition.
/// </summary>
public static class ContextLadderCampaignCommand
{
    public static Command Build(IServiceProvider services)
    {
        var manifestOption = new Option<FileInfo?>("--manifest")
        {
            Description = "Frozen direct-edit context ladder manifest. Required unless --print-ladder is used."
        };
        var printLadderOption = new Option<string?>("--print-ladder")
        {
            Description = "Print a ladder definition and its hash, then exit. "
                        + $"One of {ContextLadder.V1Version}, {ContextLadder.V2Version}. "
                        + "The hash is what a manifest must carry as ladder_sha256."
        };
        var outOption = new Option<DirectoryInfo?>("--out")
        {
            Description = "New or resumable campaign output directory. Required unless --print-ladder is used."
        };
        var preflightOption = new Option<bool>("--preflight-only")
        {
            Description = "Validate the manifest, ladder hash and configured model without making a model call."
        };
        var stopAfterOption = new Option<int>("--stop-after")
        {
            Description = "Stop successfully after N new assignments (0 = run all remaining)."
        };

        var command = new Command(
            "context-ladder-campaign",
            "Execute or resume a frozen four-level context ladder under direct editing (no applier).")
        {
            manifestOption, outOption, preflightOption, stopAfterOption, printLadderOption
        };

        command.SetAction(async (parseResult, cancellationToken) =>
        {
            var printLadder = parseResult.GetValue(printLadderOption);
            if (!string.IsNullOrWhiteSpace(printLadder))
                return PrintLadder(printLadder);

            var manifestFile = parseResult.GetValue(manifestOption);
            var outputDirectory = parseResult.GetValue(outOption);
            var preflightOnly = parseResult.GetValue(preflightOption);
            var stopAfter = Math.Max(0, parseResult.GetValue(stopAfterOption));

            if (manifestFile is null || outputDirectory is null)
            {
                await Console.Error.WriteLineAsync("error: --manifest and --out are required");
                return 2;
            }

            ContextLadderManifest manifest;
            try
            {
                manifest = ContextLadderManifestStore.LoadAndValidate(manifestFile.FullName);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                await Console.Error.WriteLineAsync($"error: context ladder manifest preflight failed: {ex.Message}");
                return 2;
            }

            var adapters = services.GetRequiredService<IReadOnlyDictionary<string, ILlmAdapter>>();
            if (!adapters.TryGetValue(manifest.ModelName, out var adapter))
            {
                await Console.Error.WriteLineAsync($"error: evaluated model '{manifest.ModelName}' is not configured");
                return 2;
            }
            if (manifest.PromptVersion != ContextLadderPrompt.Version)
            {
                await Console.Error.WriteLineAsync(
                    $"error: prompt version drift (manifest {manifest.PromptVersion}; runtime {ContextLadderPrompt.Version})");
                return 2;
            }

            Console.Error.WriteLine($"Campaign: {manifest.CampaignId}");
            Console.Error.WriteLine($"Manifest SHA-256: {FactorialCampaignPlanner.Sha256File(manifestFile.FullName)}");
            Console.Error.WriteLine($"Ladder: {manifest.LadderVersion} ({manifest.LadderSha256})");
            Console.Error.WriteLine(
                $"Assignments: {manifest.Assignments.Count}; model={manifest.ModelName}; " +
                $"repetitions={manifest.Repetitions}; applier=none (direct edit)");
            if (preflightOnly)
            {
                Console.Error.WriteLine("Context ladder preflight passed; no model call made.");
                return 0;
            }

            var runner = new ContextLadderCampaignRunner(adapter,
                services.GetRequiredService<IContextBuilder>(),
                services.GetRequiredService<IRepairMeasurer>());
            var outcome = await runner.RunAsync(manifest, outputDirectory.FullName, stopAfter,
                Console.Error, cancellationToken);
            return CampaignExitStatus.From(outcome);
        });

        return command;
    }

    /// <summary>
    /// Prints a ladder definition and its hash. The protocol section and the manifest's
    /// <c>ladder_sha256</c> are both derived from this rather than written by hand, which is what
    /// stops the prose and the executed definition drifting apart.
    /// </summary>
    private static int PrintLadder(string version)
    {
        IReadOnlyList<ContextLevelSpec> ladder;
        try { ladder = ContextLadder.ForVersion(version); }
        catch (ArgumentOutOfRangeException)
        {
            Console.Error.WriteLine(
                $"error: unknown ladder '{version}'; expected {ContextLadder.V1Version} or {ContextLadder.V2Version}");
            return 2;
        }

        Console.WriteLine($"ladder_version: {version}");
        Console.WriteLine($"ladder_sha256:  {ContextLadder.Sha256(ladder)}");
        Console.WriteLine();
        Console.WriteLine("| level | metrics | members | window | metadata | co-located | cross-file | caps |");
        Console.WriteLine("|---|---|---|---|---|---|---|---|");
        foreach (var spec in ladder)
        {
            var caps = spec.CrossFile == CrossFileScope.None
                ? "-"
                : $"{spec.MaxCrossFileFiles} files / {spec.MaxCrossFileChars} chars";
            Console.WriteLine(
                $"| {spec.Level} | {Mark(spec.IncludeMetrics)} | {Mark(spec.IncludeMemberSummary)} | "
                + $"{Mark(spec.IncludeSurroundingWindow)} | {Mark(spec.IncludeProjectMetadata)} | "
                + $"{Mark(spec.IncludeCoLocatedFindings)} | {spec.CrossFile} | {caps} |");
        }
        return 0;

        static string Mark(bool value) => value ? "yes" : "no";
    }

}
