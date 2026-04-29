using System.CommandLine;
using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
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
        var targetOption = new Option<FileInfo>("--target")
        {
            Description = "Path to the .sln or .csproj to analyse",
            Required = true
        };
        targetOption.AcceptExistingOnly();

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
            var target = parseResult.GetValue(targetOption)!;
            var loader = services.GetRequiredService<WorkspaceLoader>();
            var detectorConfig = services.GetRequiredService<DetectorConfig>();

            Console.WriteLine($"Loading: {target.FullName}");

            var compilations = await loader.LoadAsync(target.FullName, cancellationToken);

            foreach (var warning in loader.Warnings)
                Console.WriteLine($"  [warn] {warning}");

            Console.WriteLine($"Loaded {compilations.Count} project(s).{Environment.NewLine}");

            var detectors = new IDetector[]
            {
                new LongMethodDetector(detectorConfig.LongMethod),
                new GodClassDetector(detectorConfig.GodClass),
                new ObsoleteApiDetector(detectorConfig.ObsoleteApi)
            };

            var findings = compilations
                .SelectMany(c => detectors.SelectMany(d => d.Detect(c)))
                .ToList();

            if (findings.Count == 0)
            {
                Console.WriteLine("No findings.");
                return;
            }

            foreach (var group in findings.GroupBy(f => f.Type))
            {
                var sorted = group
                    .OrderByDescending(f => f.Severity)
                    .ThenBy(f => f.SymbolName)
                    .ToList();

                Console.WriteLine($"── {group.Key} ({sorted.Count} finding(s)) ──");
                Console.WriteLine($"  {"Severity",-10}  {"Symbol",-60}  {"File"}");
                Console.WriteLine(new string('-', 120));

                foreach (var f in sorted)
                {
                    var relativePath = Path.GetRelativePath(
                        Path.GetDirectoryName(target.FullName)!, f.FilePath);
                    Console.WriteLine($"  {f.Severity,-10}  {f.SymbolName,-60}  {relativePath}:{f.Line}");
                }

                Console.WriteLine();
            }

            Console.WriteLine($"Total: {findings.Count} finding(s) " +
                $"({findings.Count(f => f.Severity == Severity.Critical)} critical, " +
                $"{findings.Count(f => f.Severity == Severity.Warning)} warnings)");

            // TODO: hand findings to ContextBuilder + LLM pipeline
        });

        return command;
    }
}
