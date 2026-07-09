using System.CommandLine;
using HybridLens.CLI.Commands;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Configuration;
using HybridLens.LLM;
using HybridLens.Pipeline;
using HybridLens.StaticAnalysis;
using HybridLens.StaticAnalysis.Workspace;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

// Pre-scan argv for --config so the file is available before DI is built.
// System.CommandLine does the real validation later; this is just a path grab.
var earlyConfigPath = args
    .SkipWhile(a => !string.Equals(a, "--config", StringComparison.OrdinalIgnoreCase))
    .Skip(1)
    .FirstOrDefault();

var configBuilder = new ConfigurationBuilder()
    .SetBasePath(AppContext.BaseDirectory)
    .AddJsonFile("appsettings.json",       optional: false)
    .AddJsonFile("appsettings.local.json", optional: true);

if (earlyConfigPath is not null)
    configBuilder.AddJsonFile(earlyConfigPath, optional: false, reloadOnChange: false);

var configuration = configBuilder.Build();

var services = new ServiceCollection()
    .AddSingleton(configuration.GetSection("Workspace").Get<WorkspaceConfig>()   ?? new WorkspaceConfig())
    .AddSingleton(configuration.GetSection("Detectors").Get<DetectorConfig>()    ?? new DetectorConfig())
    .AddSingleton(configuration.GetSection("Context").Get<ContextConfig>()       ?? new ContextConfig())
    .AddSingleton(configuration.GetSection("Llm").Get<LlmConfig>()               ?? new LlmConfig())
    .AddSingleton(configuration.GetSection("Pipeline").Get<PipelineConfig>()     ?? new PipelineConfig())
    .AddSingleton<WorkspaceLoader>()
    .AddSingleton<SolutionQualityScanner>()
    .AddSingleton<ISolutionQualityScanner>(sp => sp.GetRequiredService<SolutionQualityScanner>())
    .AddSingleton<IRepairMeasurer, RoslynRepairMeasurer>()
    .AddSingleton<IContextBuilder, HybridLens.ContextBuilder.ContextBuilder>()
    .AddSingleton<ILlmAdapterFactory, LlmAdapterFactory>()
    .AddSingleton<IReadOnlyDictionary<string, ILlmAdapter>>(sp =>
        sp.GetRequiredService<ILlmAdapterFactory>()
          .CreateAll(sp.GetRequiredService<LlmConfig>()))
    .AddSingleton<AnalysisPipeline>()
    .BuildServiceProvider();

// If invoked with no arguments at all, route to the `analyse` command so its
// SetAction fires. Whether that run is "interactive" is decided inside the
// command itself by inspecting which options the user actually supplied —
// that check is more robust than relying on args.Length here.
if (args.Length == 0)
    args = ["analyse"];

var root = new RootCommand("HybridLens — hybrid static + LLM .NET code analyser")
{
    AnalyseCommand.Build(services),
    AgenticCommand.Build(services),
    GroundedIterativeCommand.Build(services),
    VerifyRepairCommand.Build(services),
    QualityScanCommand.Build(services)
};

return await root.Parse(args).InvokeAsync();
