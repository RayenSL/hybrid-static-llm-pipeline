using System.CommandLine;
using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
using HybridLens.Pipeline;
using HybridLens.StaticAnalysis.Abstractions;
using HybridLens.StaticAnalysis.Detectors;
using HybridLens.StaticAnalysis.Workspace;
using Microsoft.CodeAnalysis;
using Microsoft.Extensions.DependencyInjection;

namespace HybridLens.CLI.Commands;

public static class AnalyseCommand
{
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

        var command = new Command("analyse", "Run the HybridLens analysis pipeline on a .NET codebase")
        {
            targetOption,
            configOption
        };

        command.SetAction(async (parseResult, cancellationToken) =>
        {
            var target = parseResult.GetValue(targetOption) ?? PromptForTarget();
            if (target is null) return;

            var loader         = services.GetRequiredService<WorkspaceLoader>();
            var detectorConfig = services.GetRequiredService<DetectorConfig>();
            var pipelineConfig = services.GetRequiredService<PipelineConfig>();
            var pipeline       = services.GetRequiredService<AnalysisPipeline>();

            // ── 1. Load workspace ────────────────────────────────────────────
            Console.WriteLine($"Loading: {target.FullName}");
            var compilations = await loader.LoadAsync(target.FullName, cancellationToken);

            foreach (var warning in loader.Warnings)
                Console.WriteLine($"  [warn] {warning}");

            Console.WriteLine($"Loaded {compilations.Count} project(s).{Environment.NewLine}");

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

            PrintFindings(findings, target);

            if (findings.Count == 0)
                return;

            // ── 3. Run LLM pipeline ──────────────────────────────────────────
            var eligible = pipelineConfig.ProcessWarnings
                ? findings.Count
                : findings.Count(f => f.Severity == Severity.Critical);

            Console.WriteLine($"Sending {eligible} finding(s) to LLM...{Environment.NewLine}");

            var llmFindings = await pipeline.RunAsync(findings, cancellationToken);

            PrintLlmFindings(llmFindings, target);
        });

        return command;
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

    private static void PrintFindings(List<Finding> findings, FileInfo target)
    {
        if (findings.Count == 0)
        {
            Console.WriteLine("No findings.");
            return;
        }

        foreach (var group in findings.GroupBy(f => f.Type))
        {
            var sorted = group.OrderByDescending(f => f.Severity).ThenBy(f => f.SymbolName).ToList();
            Console.WriteLine($"── {group.Key} ({sorted.Count} finding(s)) ──");
            Console.WriteLine($"  {"Severity",-10}  {"Symbol",-60}  File");
            Console.WriteLine(new string('-', 120));

            foreach (var f in sorted)
            {
                var path = Path.GetRelativePath(Path.GetDirectoryName(target.FullName)!, f.FilePath);
                Console.WriteLine($"  {f.Severity,-10}  {f.SymbolName,-60}  {path}:{f.Line}");
            }

            Console.WriteLine();
        }

        Console.WriteLine($"Total: {findings.Count} finding(s) " +
            $"({findings.Count(f => f.Severity == Severity.Critical)} critical, " +
            $"{findings.Count(f => f.Severity == Severity.Warning)} warnings){Environment.NewLine}");
    }

    private static void PrintLlmFindings(IReadOnlyList<LlmFinding> llmFindings, FileInfo target)
    {
        foreach (var modelGroup in llmFindings.GroupBy(f => f.ModelName).OrderBy(g => g.Key))
        {
            Console.WriteLine($"{'═',1}{new string('═', 78)}");
            Console.WriteLine($"  Model: {modelGroup.Key}");
            Console.WriteLine($"{new string('═', 80)}{Environment.NewLine}");

            foreach (var lf in modelGroup.OrderByDescending(f => f.Finding.Severity))
            {
                var path = Path.GetRelativePath(Path.GetDirectoryName(target.FullName)!, lf.Finding.FilePath);

                Console.WriteLine($"┌─ [{lf.Finding.Severity}] {lf.Finding.Type} — {lf.Finding.SymbolName}");
                Console.WriteLine($"│  {path}:{lf.Finding.Line}");
                Console.WriteLine($"│");
                Console.WriteLine($"│  Explanation");
                foreach (var line in lf.Explanation.Split('\n'))
                    Console.WriteLine($"│    {line}");
                Console.WriteLine($"│");
                Console.WriteLine($"│  Remediation");
                foreach (var line in lf.Remediation.Split('\n'))
                    Console.WriteLine($"│    {line}");
                Console.WriteLine($"└{new string('─', 80)}{Environment.NewLine}");
            }
        }
    }
}
