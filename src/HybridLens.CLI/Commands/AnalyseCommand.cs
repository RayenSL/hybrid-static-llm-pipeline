using System.CommandLine;
using HybridLens.Core.Configuration;
using HybridLens.StaticAnalysis.Workspace;
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

            Console.WriteLine($"Loading: {target.FullName}");

            var compilations = await loader.LoadAsync(target.FullName, cancellationToken);

            foreach (var warning in loader.Warnings)
                Console.WriteLine($"  [warn] {warning}");

            Console.WriteLine($"Loaded {compilations.Count} project(s).");
            foreach (var compilation in compilations)
                Console.WriteLine($"  - {compilation.AssemblyName} ({compilation.SyntaxTrees.Count()} syntax trees)");

            // TODO: hand compilations to the Pipeline once detectors are implemented
        });

        return command;
    }
}
