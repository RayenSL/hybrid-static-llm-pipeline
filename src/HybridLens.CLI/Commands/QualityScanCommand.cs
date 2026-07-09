using System.CommandLine;
using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.Core.Abstractions;
using HybridLens.Pipeline;
using HybridLens.StaticAnalysis;
using Microsoft.Extensions.DependencyInjection;

namespace HybridLens.CLI.Commands;

/// <summary>
/// Standalone whole-solution quality scan (the quality-impact instrument, run once for a single state).
/// Layer 1 = the study's detectors over the whole solution; Layer 2 = CA analyzer diagnostics parsed from
/// the per-project SARIF a <c>8.0-all</c> build emits. Primarily a validation/inspection tool: it lets the
/// baseline scan be eyeballed before the scanner is wired into the repair runners. Never mutates the frozen
/// corpus itself — <c>--build</c> injects the analyzer props into whatever working copy <c>--target</c> points at.
/// </summary>
public static class QualityScanCommand
{
    public static Command Build(IServiceProvider services)
    {
        var targetOption = new Option<FileInfo>("--target")
        {
            Description = "Path to the .sln (or .csproj) working copy to scan",
            Required = true
        };
        var sarifRootOption = new Option<DirectoryInfo?>("--sarif-root")
        {
            Description = "Directory tree holding the build's per-project *.sarif logs (default: the solution's directory)"
        };
        var buildOption = new Option<bool>("--build")
        {
            Description = "Inject the CA analyzer Directory.Build.props at the sarif root and run `dotnet build` before scanning"
        };
        var timeoutOption = new Option<int>("--build-timeout")
        {
            Description = "Build timeout in seconds when --build is set (default: 300)"
        };
        var outputOption = new Option<FileInfo?>("--output")
        {
            Description = "Write the full scan as JSON to this file (in addition to the console summary)"
        };

        var command = new Command("quality-scan",
            "Measure whole-solution code quality (Layer 1 detectors + Layer 2 CA analyzers) for one state")
        {
            targetOption, sarifRootOption, buildOption, timeoutOption, outputOption
        };

        command.SetAction(async (parseResult, cancellationToken) =>
        {
            var target     = parseResult.GetValue(targetOption)!;
            var sarifRoot   = parseResult.GetValue(sarifRootOption)?.FullName
                              ?? Path.GetDirectoryName(target.FullName)!;
            var doBuild     = parseResult.GetValue(buildOption);
            var timeout     = parseResult.GetValue(timeoutOption);
            if (timeout <= 0) timeout = 300;
            var outputFile  = parseResult.GetValue(outputOption);

            if (!target.Exists)
            {
                await Console.Error.WriteLineAsync($"error: target not found: {target.FullName}");
                return 2;
            }

            var scanner = services.GetRequiredService<ISolutionQualityScanner>();

            Console.Error.WriteLine(doBuild
                ? $"Building {target.Name} (dedicated 8.0-all analyzer build) then scanning…"
                : $"Scanning {target.Name} (sarif root: {sarifRoot})…");

            // --build exercises the exact path the repair runners use (inject props → analyzer build →
            // scan → remove props); without it, scan whatever SARIF a prior build already emitted.
            var scan = doBuild
                ? await scanner.BuildAndScanAsync(target.FullName, sarifRoot, DotnetBuilder.BuildAsync, timeout, cancellationToken)
                : await scanner.ScanAsync(target.FullName, sarifRoot, cancellationToken);

            PrintSummary(scan);

            if (outputFile is not null)
            {
                var opts = new JsonSerializerOptions
                {
                    WriteIndented = true,
                    PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
                    DefaultIgnoreCondition = JsonIgnoreCondition.Never
                };
                outputFile.Directory?.Create();
                await File.WriteAllTextAsync(outputFile.FullName, JsonSerializer.Serialize(scan, opts), cancellationToken);
                Console.Error.WriteLine($"Wrote {outputFile.FullName}");
            }

            return 0;
        });

        return command;
    }

    private static void PrintSummary(HybridLens.Core.Models.SolutionQualityScan s)
    {
        Console.WriteLine();
        Console.WriteLine("── Layer 1: whole-solution detector (self-scored) ──");
        Console.WriteLine($"  total smells: {s.SmellTotal}");
        foreach (var (type, n) in s.SmellCountsByType.OrderBy(kv => kv.Key, StringComparer.Ordinal))
            Console.WriteLine($"    {type,-20} {n}");

        Console.WriteLine();
        Console.WriteLine("── Layer 2: CA analyzers (independent instrument) ──");
        Console.WriteLine($"  CA available: {s.CaAvailable}");
        Console.WriteLine($"  headline (enabled-by-default): {s.CaHeadlineTotal}   |   all (incl. opt-in): {s.CaAllTotal}   |   compiler obsolete (CS0618/9): {s.CompilerObsoleteCount}");
        Console.WriteLine("  headline by category:");
        foreach (var (cat, n) in s.CaHeadlineByCategory.OrderByDescending(kv => kv.Value))
            Console.WriteLine($"    {cat,-18} {n}");
        Console.WriteLine("  headline by rule:");
        foreach (var (rule, n) in s.CaHeadlineByRule.OrderByDescending(kv => kv.Value))
            Console.WriteLine($"    {rule,-10} {n}");
        var optIn = s.CaAllByRule.Where(kv => !s.CaHeadlineByRule.ContainsKey(kv.Key)).OrderByDescending(kv => kv.Value).ToList();
        if (optIn.Count > 0)
        {
            Console.WriteLine("  opt-in / all-only rules (sensitivity tier):");
            foreach (var (rule, n) in optIn)
                Console.WriteLine($"    {rule,-10} {n}");
        }
        if (!string.IsNullOrEmpty(s.Note))
            Console.WriteLine($"  note: {s.Note}");
        Console.WriteLine();
    }
}
