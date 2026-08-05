using System.CommandLine;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.Core.Abstractions;
using HybridLens.Pipeline;
using Microsoft.Extensions.DependencyInjection;

namespace HybridLens.CLI.Commands;

/// <summary>
/// Whole-solution quality impact (Layer 2) for sealed final-source artefacts of any C# solution.
/// The corpus equivalents are <c>quality-scan</c> and <c>quality-rescore</c>, which assume the corpus
/// layout; this command takes the solution, the build arguments and the working-copy skip list as
/// arguments so a transfer probe reports the same three layers the confirmatory experiment does.
/// </summary>
public static class ExternalQualityCommand
{
    public static Command Build(IServiceProvider services)
    {
        var artifactsOption = new Option<DirectoryInfo>("--artifacts")
        {
            Required = true,
            Description = "Directory of frozen materialized final-source JSON artefacts (the campaign's final-sources)."
        };
        var targetOption = new Option<FileInfo>("--target")
        {
            Required = true,
            Description = "Pristine solution (.sln). Scanned once as the shared baseline, then per artefact."
        };
        var buildArgOption = new Option<string[]>("--build-arg")
        {
            Description = "Extra argument for the analyser build, repeatable (for example --no-restore).",
            AllowMultipleArgumentsPerToken = false
        };
        var skipDirOption = new Option<string[]>("--working-copy-skip")
        {
            Description = "Directory omitted from each working copy, repeatable (default: bin obj .git .vs .idea). "
                        + "A solution built with --no-restore must retain obj.",
            AllowMultipleArgumentsPerToken = false
        };
        var outOption = new Option<FileInfo?>("--out")
        {
            Description = "Result JSONL (default: runs/<timestamp>-external-quality.jsonl). Existing files are never overwritten."
        };
        var timeoutOption = new Option<int>("--timeout")
        {
            Description = "Per-artefact analyser build timeout in seconds (default: 900)."
        };

        var command = new Command("external-quality",
            "Score whole-solution quality impact (Layer 2) for sealed final-source artefacts of an arbitrary solution.")
        {
            artifactsOption, targetOption, buildArgOption, skipDirOption, outOption, timeoutOption
        };

        command.SetAction(async (parseResult, cancellationToken) =>
        {
            var artifacts = parseResult.GetValue(artifactsOption)!;
            var target = parseResult.GetValue(targetOption)!;
            var buildArgs = parseResult.GetValue(buildArgOption) ?? [];
            var skipDirs = parseResult.GetValue(skipDirOption) ?? [];
            var timeout = parseResult.GetValue(timeoutOption);
            if (timeout <= 0) timeout = 900;
            var output = parseResult.GetValue(outOption)?.FullName
                         ?? Path.GetFullPath(Path.Combine(
                             "runs", $"{DateTimeOffset.UtcNow:yyyyMMdd-HHmmss}-external-quality.jsonl"));

            if (!artifacts.Exists)
            {
                await Console.Error.WriteLineAsync($"error: --artifacts directory not found: {artifacts.FullName}");
                return 2;
            }
            if (!target.Exists || !target.Extension.Equals(".sln", StringComparison.OrdinalIgnoreCase))
            {
                await Console.Error.WriteLineAsync($"error: --target must be an existing .sln: {target.FullName}");
                return 2;
            }
            if (File.Exists(output))
            {
                await Console.Error.WriteLineAsync($"error: refusing to overwrite an existing quality result: {output}");
                return 2;
            }

            try
            {
                WorkingCopy.GuardRestoreArguments(buildArgs, skipDirs, "the analyser build");
            }
            catch (InvalidDataException ex)
            {
                await Console.Error.WriteLineAsync($"error: {ex.Message}");
                return 2;
            }

            var scanner = services.GetRequiredService<ISolutionQualityScanner>();
            var evaluator = new ExternalQualityEvaluator(
                scanner, target.FullName, buildArgs, timeout, skipDirs);

            var results = await evaluator.EvaluateDirectoryAsync(
                artifacts.FullName, Console.Error, cancellationToken);

            Directory.CreateDirectory(Path.GetDirectoryName(output)!);
            var jsonOptions = new JsonSerializerOptions
            {
                PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
                Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) }
            };
            await using (var stream = new FileStream(output, FileMode.CreateNew, FileAccess.Write, FileShare.Read))
            await using (var writer = new StreamWriter(stream, new UTF8Encoding(false)))
                foreach (var result in results)
                    await writer.WriteLineAsync(JsonSerializer.Serialize(result, jsonOptions));

            Console.Error.WriteLine($"External quality result: {output}");
            foreach (var group in results.GroupBy(r => r.Outcome).OrderBy(g => g.Key, StringComparer.Ordinal))
                Console.Error.WriteLine($"  {group.Key,-30} {group.Count()}");
            return 0;
        });

        return command;
    }
}
