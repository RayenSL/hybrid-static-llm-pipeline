using System.CommandLine;
using HybridLens.Pipeline;

namespace HybridLens.CLI.Commands;

/// <summary>Freezes the complete randomized assignment schedule before any repair call is made.</summary>
public static class FactorialManifestCommand
{
    public static Command Build()
    {
        var fromOption = new Option<FileInfo>("--from") { Required = true, Description = "Frozen analyzer JSONL." };
        var targetOption = new Option<FileInfo>("--target") { Required = true, Description = "Pristine corpus solution." };
        var visibleOption = new Option<DirectoryInfo>("--visible-tests")
        {
            Required = true,
            Description = "Directory containing all generated-test artifacts, including rejected artifacts."
        };
        var modelOption = new Option<string>("--model") { Required = true, Description = "Frozen evaluated-model key." };
        var revisionOption = new Option<string>("--code-revision")
        {
            Required = true,
            Description = "Frozen VCS commit/revision identifying the implementation used for the campaign."
        };
        var runsOption = new Option<int>("--runs") { Description = "Repetitions per instance (default: 3)." };
        var budgetOption = new Option<int>("--budget") { Description = "Iterative build-attempt budget (default: 6)." };
        var timeoutOption = new Option<int>("--build-timeout") { Description = "Build/test timeout seconds (default: 180)." };
        var tokenOption = new Option<int>("--max-input-tokens") { Description = "Input-token guard (default: 120000)." };
        var seedOption = new Option<int>("--seed") { Required = true, Description = "Fixed randomization seed." };
        var outOption = new Option<FileInfo>("--out") { Required = true, Description = "Output manifest JSON path." };

        var command = new Command("factorial-manifest",
            "Create and validate a frozen randomized-block 2 x 2 x 2 campaign manifest.")
        {
            fromOption, targetOption, visibleOption, modelOption, revisionOption, runsOption,
            budgetOption, timeoutOption, tokenOption, seedOption, outOption
        };
        command.SetAction(async (parseResult, cancellationToken) =>
        {
            var from = parseResult.GetValue(fromOption)!;
            var target = parseResult.GetValue(targetOption)!;
            var visibleDirectory = parseResult.GetValue(visibleOption)!;
            var model = parseResult.GetValue(modelOption)!;
            var revision = parseResult.GetValue(revisionOption)!;
            var runs = parseResult.GetValue(runsOption);
            var budget = parseResult.GetValue(budgetOption);
            var timeout = parseResult.GetValue(timeoutOption);
            var tokenGuard = parseResult.GetValue(tokenOption);
            var seed = parseResult.GetValue(seedOption);
            var output = parseResult.GetValue(outOption)!;
            if (runs < 1) runs = 3;
            if (budget < 1) budget = 6;
            if (timeout < 1) timeout = 180;
            if (tokenGuard < 1) tokenGuard = 120_000;

            if (!from.Exists || !target.Exists || !visibleDirectory.Exists)
            {
                await Console.Error.WriteLineAsync("error: --from, --target, and --visible-tests must exist");
                return 2;
            }

            try
            {
                var seeds = FactorialCampaignInputLoader.Load(from.FullName);
                if (seeds.Count == 0) throw new InvalidDataException("baseline contains no Long Method/God Class instances");
                var visible = await VisibleTestDirectoryLoader.LoadAsync(visibleDirectory.FullName, cancellationToken);
                var manifest = FactorialCampaignPlanner.Create(
                    seeds, visible, target.FullName, from.FullName, model, revision,
                    runs, budget, timeout, tokenGuard, seed);
                await FactorialCampaignManifestStore.SaveAsync(output.FullName, manifest, cancellationToken);
                Console.Error.WriteLine($"Manifest: {Path.GetFullPath(output.FullName)}");
                Console.Error.WriteLine($"Campaign: {manifest.CampaignId}");
                Console.Error.WriteLine($"Assignments: {manifest.Assignments.Count} " +
                                        $"({seeds.Count} instances x {runs} repetitions x 8 conditions)");
                Console.Error.WriteLine($"Admitted visible tests: {visible.Count}/{seeds.Count}");
                return 0;
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                await Console.Error.WriteLineAsync($"error: {ex.Message}");
                return 2;
            }
        });
        return command;
    }
}
