using System.CommandLine;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.Pipeline;

namespace HybridLens.CLI.Commands;

/// <summary>Runs the frozen private behavioural oracle once per opaque final-source artefact.</summary>
public static class PrivateLayer3Command
{
    public static Command Build()
    {
        var artifactsOption = new Option<DirectoryInfo>("--artifacts")
        {
            Description = "Directory containing common materialized final-source JSON artefacts.",
            Required = true
        };
        var targetOption = new Option<FileInfo>("--target")
        {
            Description = "Pristine corpus solution (.sln) used to reconstruct each isolated final state.",
            Required = true
        };
        var manifestOption = new Option<FileInfo?>("--oracle-manifest")
        {
            Description = "Frozen private-oracle manifest (default: layer3/PRIVATE_ORACLE_MANIFEST.md)."
        };
        var outOption = new Option<FileInfo?>("--out")
        {
            Description = "New blinded result JSONL (default: runs/<timestamp>-private-layer3.jsonl). Existing files are never overwritten."
        };
        var timeoutOption = new Option<int>("--timeout")
        {
            Description = "Per-artefact private-suite timeout in seconds (default: 180)."
        };

        var command = new Command("private-layer3",
            "Evaluate frozen final-source artefacts with the private Layer-3 oracle after all repair conditions terminate.")
        {
            artifactsOption, targetOption, manifestOption, outOption, timeoutOption
        };

        command.SetAction(async (parseResult, cancellationToken) =>
        {
            var artifacts = parseResult.GetValue(artifactsOption)!;
            var target = parseResult.GetValue(targetOption)!;
            var manifest = parseResult.GetValue(manifestOption)?.FullName
                           ?? Path.GetFullPath(Path.Combine("layer3", "PRIVATE_ORACLE_MANIFEST.md"));
            var output = parseResult.GetValue(outOption)?.FullName
                         ?? Path.GetFullPath(Path.Combine(
                             "runs", $"{DateTimeOffset.UtcNow:yyyyMMdd-HHmmss}-private-layer3.jsonl"));
            var timeout = parseResult.GetValue(timeoutOption);
            if (timeout <= 0) timeout = 180;

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
            if (!File.Exists(manifest))
            {
                await Console.Error.WriteLineAsync($"error: private-oracle manifest not found: {manifest}");
                return 2;
            }
            if (File.Exists(output))
            {
                await Console.Error.WriteLineAsync($"error: refusing to overwrite private Layer-3 result: {output}");
                return 2;
            }

            string manifestVersion;
            try
            {
                manifestVersion = PrivateOracleManifestVerifier.Verify(manifest);
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                await Console.Error.WriteLineAsync($"error: private-oracle freeze verification failed: {ex.Message}");
                return 2;
            }

            var oracleRoot = Path.GetDirectoryName(Path.GetFullPath(manifest))!;
            var evaluator = new PrivateLayer3Evaluator(
                target.FullName, oracleRoot, manifestVersion, timeout);
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

            Console.Error.WriteLine($"Private Layer-3 result: {output}");
            Console.Error.WriteLine(
                $"evaluated={results.Count(r => r.Evaluated)}, pass={results.Count(r => r.Passed == true)}, " +
                $"regression={results.Count(r => r.Passed == false)}, not-run={results.Count(r => !r.Evaluated)}");
            return 0;
        });

        return command;
    }
}
