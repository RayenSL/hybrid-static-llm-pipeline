using System.CommandLine;
using HybridLens.CLI.Output;
using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
using HybridLens.Pipeline;
using HybridLens.StaticAnalysis.Abstractions;
using HybridLens.StaticAnalysis.Detectors;
using HybridLens.StaticAnalysis.Workspace;
using Microsoft.Extensions.DependencyInjection;

namespace HybridLens.CLI.Commands;

public static class AnalyseCommand
{
    /// <summary>Exit code returned when at least one finding at or above the severity threshold is found.</summary>
    public const int ExitFindingsFound = 1;

    public static Command Build(IServiceProvider services)
    {
        var targetOption = new Option<FileInfo?>("--target")
        {
            Description = "Path to the .sln or .csproj to analyse (prompted if omitted)"
        };

        var configOption = new Option<FileInfo?>("--config")
        {
            Description = "Path to a hybridlens.json config file (optional)"
        };

        var formatOption = new Option<OutputFormat>("--format")
        {
            Description = "Output format: console (default), json, sarif"
            // OutputFormat.Console == 0, so it is the implicit default
        };

        var outputOption = new Option<FileInfo?>("--output")
        {
            Description = "Write output to file instead of stdout (useful with --format json|sarif)"
        };

        var severityOption = new Option<Severity>("--severity")
        {
            Description = "Minimum severity sent to LLM and used for the exit-code gate (default: Critical)"
            // Severity.Info == 0, so we need a different default — handled below via explicit check
        };
        // Severity enum: Info=0, Warning=1, Critical=2.  We want Critical as the default.
        // System.CommandLine v3 doesn't have SetDefaultValue; we detect the zero-value below.

        var dryRunOption = new Option<bool>("--dry-run")
        {
            Description = "Run static analysis only; skip the LLM pipeline"
        };

        var command = new Command("analyse", "Run the HybridLens analysis pipeline on a .NET codebase")
        {
            targetOption,
            configOption,
            formatOption,
            outputOption,
            severityOption,
            dryRunOption
        };

        command.SetAction(async (parseResult, cancellationToken) =>
        {
            var target = parseResult.GetValue(targetOption) ?? PromptForTarget();
            if (target is null) return ExitFindingsFound;

            var format      = parseResult.GetValue(formatOption);
            var outputFile  = parseResult.GetValue(outputOption);
            var dryRun      = parseResult.GetValue(dryRunOption);

            // Severity.Info is the enum zero-value; treat it as "not supplied" and default to Critical.
            var rawSeverity = parseResult.GetValue(severityOption);
            var minSeverity = rawSeverity == Severity.Info ? Severity.Critical : rawSeverity;

            // For structured formats progress goes to stderr so it doesn't pollute the output stream.
            var progress = format == OutputFormat.Console ? Console.Out : Console.Error;

            var loader         = services.GetRequiredService<WorkspaceLoader>();
            var detectorConfig = services.GetRequiredService<DetectorConfig>();
            var pipeline       = services.GetRequiredService<AnalysisPipeline>();

            // ── 1. Load workspace ────────────────────────────────────────────
            progress.WriteLine($"Loading: {target.FullName}");
            var compilations = await loader.LoadAsync(target.FullName, cancellationToken);

            foreach (var warning in loader.Warnings)
                progress.WriteLine($"  [warn] {warning}");

            progress.WriteLine($"Loaded {compilations.Count} project(s).{Environment.NewLine}");

            // ── 2. Run detectors ─────────────────────────────────────────────
            var detectors = new IDetector[]
            {
                new LongMethodDetector(detectorConfig.LongMethod),
                new GodClassDetector(detectorConfig.GodClass),
                new ObsoleteApiDetector(detectorConfig.ObsoleteApi)
            };

            var findings = compilations
                .SelectMany(c => detectors.SelectMany(d => d.Detect(c)))
                .ToList();

            if (format == OutputFormat.Console)
                PrintStaticFindings(findings, target, Console.Out);
            else
                PrintStaticFindingsSummary(findings, progress);

            if (findings.Count == 0)
                return 0;

            // ── 3. Run LLM pipeline (skipped on --dry-run) ───────────────────
            IReadOnlyList<LlmFinding> llmFindings = [];

            if (!dryRun)
            {
                var eligible = findings.Count(f => f.Severity >= minSeverity);
                progress.WriteLine($"Sending {eligible} finding(s) to LLM...{Environment.NewLine}");
                llmFindings = await pipeline.RunAsync(findings, minSeverity, cancellationToken);
            }
            else
            {
                progress.WriteLine("Dry run — LLM pipeline skipped.");
            }

            // ── 4. Write output ──────────────────────────────────────────────
            IOutputFormatter formatter = format switch
            {
                OutputFormat.Json  => new JsonOutputFormatter(),
                OutputFormat.Sarif => new SarifOutputFormatter(),
                OutputFormat.Html  => new HtmlOutputFormatter(),
                _                  => new ConsoleOutputFormatter()
            };

            await using var writer = OpenWriter(outputFile);
            await formatter.WriteAsync(findings, llmFindings, target, writer, cancellationToken);

            // ── 5. Exit code ─────────────────────────────────────────────────
            return findings.Any(f => f.Severity >= minSeverity) ? ExitFindingsFound : 0;
        });

        return command;
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private static TextWriter OpenWriter(FileInfo? outputFile)
    {
        if (outputFile is null)
            return new StreamWriter(Console.OpenStandardOutput(), leaveOpen: true);

        outputFile.Directory?.Create();
        return new StreamWriter(outputFile.FullName, append: false, System.Text.Encoding.UTF8);
    }

    private static FileInfo? PromptForTarget()
    {
        while (true)
        {
            Console.Write("Target (.sln or .csproj): ");
            var input = Console.ReadLine()?.Trim();

            if (string.IsNullOrEmpty(input))
            {
                Console.Error.WriteLine("No path entered. Exiting.");
                return null;
            }

            var file = new FileInfo(input);
            if (!file.Exists)
            {
                Console.Error.WriteLine($"  Path not found: {input}");
                continue;
            }

            var ext = file.Extension.ToLowerInvariant();
            if (ext is not ".sln" and not ".csproj")
            {
                Console.Error.WriteLine($"  Expected a .sln or .csproj file, got '{ext}'");
                continue;
            }

            return file;
        }
    }

    /// <summary>Full table — used for console format (printed before LLM runs).</summary>
    private static void PrintStaticFindings(List<Finding> findings, FileInfo target, TextWriter writer)
    {
        if (findings.Count == 0)
        {
            writer.WriteLine("No findings.");
            return;
        }

        var baseDir = Path.GetDirectoryName(target.FullName)!;

        foreach (var group in findings.GroupBy(f => f.Type))
        {
            var sorted = group.OrderByDescending(f => f.Severity).ThenBy(f => f.SymbolName).ToList();
            writer.WriteLine($"── {group.Key} ({sorted.Count} finding(s)) ──");
            writer.WriteLine($"  {"Severity",-10}  {"Symbol",-60}  File");
            writer.WriteLine(new string('-', 120));

            foreach (var f in sorted)
            {
                var path = Path.GetRelativePath(baseDir, f.FilePath);
                writer.WriteLine($"  {f.Severity,-10}  {f.SymbolName,-60}  {path}:{f.Line}");
            }

            writer.WriteLine();
        }

        writer.WriteLine($"Total: {findings.Count} finding(s) " +
            $"({findings.Count(f => f.Severity == Severity.Critical)} critical, " +
            $"{findings.Count(f => f.Severity == Severity.Warning)} warnings){Environment.NewLine}");
    }

    /// <summary>One-line summary — used for json/sarif format progress (written to stderr).</summary>
    private static void PrintStaticFindingsSummary(List<Finding> findings, TextWriter progress)
    {
        if (findings.Count == 0)
        {
            progress.WriteLine("No findings.");
            return;
        }

        progress.WriteLine(
            $"Found {findings.Count} finding(s): " +
            $"{findings.Count(f => f.Severity == Severity.Critical)} critical, " +
            $"{findings.Count(f => f.Severity == Severity.Warning)} warnings.{Environment.NewLine}");
    }
}
