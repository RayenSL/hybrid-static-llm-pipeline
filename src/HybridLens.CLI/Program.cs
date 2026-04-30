using System.CommandLine;
using HybridLens.CLI.Commands;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Configuration;
using HybridLens.LLM;
using HybridLens.Pipeline;
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
    .AddSingleton<IContextBuilder, HybridLens.ContextBuilder.ContextBuilder>()
    .AddSingleton<ILlmAdapterFactory, LlmAdapterFactory>()
    .AddSingleton<IReadOnlyDictionary<string, ILlmAdapter>>(sp =>
        sp.GetRequiredService<ILlmAdapterFactory>()
          .CreateAll(sp.GetRequiredService<LlmConfig>()))
    .AddSingleton<AnalysisPipeline>()
    .BuildServiceProvider();

var root = new RootCommand("HybridLens — hybrid static + LLM .NET code analyser")
{
    AnalyseCommand.Build(services)
};

return await root.Parse(args).InvokeAsync();
