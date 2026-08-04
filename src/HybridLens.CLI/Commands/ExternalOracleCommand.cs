using System.CommandLine;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.Pipeline;

namespace HybridLens.CLI.Commands;

/// <summary>
/// Post-seal behavioural measurement with an external golden-master harness, for any C# solution.
/// The corpus equivalent is <c>private-layer3</c>, which assumes the corpus layout; this command
/// takes the harness project, the golden directory and the MSBuild properties as arguments so an
/// arbitrary solution can be measured with the same instrument.
/// </summary>
public static class ExternalOracleCommand
{
    public static Command Build()
    {
        var artifactsOption = new Option<DirectoryInfo>("--artifacts")
        {
            Required = true,
            Description = "Directory of frozen materialized final-source JSON artefacts (the campaign's final-sources)."
        };
        var targetOption = new Option<FileInfo>("--target")
        {
            Required = true,
            Description = "Pristine solution (.sln) from which each isolated working copy is reconstructed."
        };
        var harnessOption = new Option<FileInfo>("--harness")
        {
            Required = true,
            Description = "Harness project (.csproj). Must exit zero when recorded behaviour is unchanged."
        };
        var goldenOption = new Option<DirectoryInfo>("--golden")
        {
            Required = true,
            Description = "Frozen golden directory passed to the harness in check mode."
        };
        var propertyOption = new Option<string[]>("--harness-prop")
        {
            Description = "MSBuild property for the harness build, repeatable. "
                        + ExternalOracleEvaluator.WorkingRootToken
                        + " is replaced with the isolated working-copy root, e.g. "
                        + "-p:ProductRoot=" + ExternalOracleEvaluator.WorkingRootToken,
            AllowMultipleArgumentsPerToken = false
        };
        var buildArgOption = new Option<string[]>("--build-arg")
        {
            Description = "Extra argument for the harness build, repeatable (for example --no-restore).",
            AllowMultipleArgumentsPerToken = false
        };
        var outOption = new Option<FileInfo?>("--out")
        {
            Description = "Result JSONL (default: runs/<timestamp>-external-oracle.jsonl). Existing files are never overwritten."
        };
        var timeoutOption = new Option<int>("--timeout")
        {
            Description = "Per-artefact build and check timeout in seconds (default: 600)."
        };

        var command = new Command("external-oracle",
            "Evaluate sealed final-source artefacts with an external golden-master harness, after all repair conditions terminate.")
        {
            artifactsOption, targetOption, harnessOption, goldenOption,
            propertyOption, buildArgOption, outOption, timeoutOption
        };

        command.SetAction(async (parseResult, cancellationToken) =>
        {
            var artifacts = parseResult.GetValue(artifactsOption)!;
            var target = parseResult.GetValue(targetOption)!;
            var harness = parseResult.GetValue(harnessOption)!;
            var golden = parseResult.GetValue(goldenOption)!;
            var properties = parseResult.GetValue(propertyOption) ?? [];
            var buildArgs = parseResult.GetValue(buildArgOption) ?? [];
            var timeout = parseResult.GetValue(timeoutOption);
            if (timeout <= 0) timeout = 600;
            var output = parseResult.GetValue(outOption)?.FullName
                         ?? Path.GetFullPath(Path.Combine(
                             "runs", $"{DateTimeOffset.UtcNow:yyyyMMdd-HHmmss}-external-oracle.jsonl"));

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
            if (!harness.Exists || !harness.Extension.Equals(".csproj", StringComparison.OrdinalIgnoreCase))
            {
                await Console.Error.WriteLineAsync($"error: --harness must be an existing .csproj: {harness.FullName}");
                return 2;
            }
            if (!golden.Exists)
            {
                await Console.Error.WriteLineAsync($"error: --golden directory not found: {golden.FullName}");
                return 2;
            }
            if (File.Exists(output))
            {
                await Console.Error.WriteLineAsync($"error: refusing to overwrite an existing oracle result: {output}");
                return 2;
            }

            var evaluator = new ExternalOracleEvaluator(
                target.FullName, harness.FullName, golden.FullName, properties, buildArgs, timeout);
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

            Console.Error.WriteLine($"External oracle result: {output}");
            foreach (var group in results.GroupBy(r => r.Outcome).OrderBy(g => g.Key, StringComparer.Ordinal))
                Console.Error.WriteLine($"  {group.Key,-30} {group.Count()}");
            return 0;
        });

        return command;
    }
}
